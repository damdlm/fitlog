from flask import Blueprint, render_template, request
from flask_login import login_required
from datetime import datetime, timedelta, timezone
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
import logging

stats_bp = Blueprint('stats', __name__)
logger = logging.getLogger(__name__)

# Tabela de Progresso: antes trazia TODO o histórico de registros/séries
# do usuário (podendo passar de milhares de linhas com o tempo), mesmo
# que o filtro de "semanas" aplicado depois mostrasse só uma fração
# disso. Restringir para os últimos 30 dias na própria query reduz o
# volume de dados trafegado do banco e processado em Python nesta rota
# -- mesma janela já usada em EstatisticaService.get_progresso_ultimos_30_dias
# (gráfico "Evolução do Volume" da tela de estatísticas), então o app já
# tinha esse mesmo horizonte de tempo em outro lugar.
#
# Trade-off consciente: quem quiser comparar cargas de mais de 30 dias
# atrás nesta tabela específica não vai mais conseguir -- o filtro
# "Todas as semanas" do dropdown passa a significar "todas dentro dos
# últimos 30 dias", não mais o histórico completo.
DIAS_HISTORICO_TABELA_PROGRESSO = 30


def _get_treino_id(exercicio):
    """Retorna o ID do treino associado a um exercício (base ou usuário)"""
    # Exercício base não tem treino_id, retorna vazio
    if hasattr(exercicio, 'treino_id'):
        return exercicio.treino_id or ""
    # Se for ExercicioUsuario e tiver referência ao treino
    if hasattr(exercicio, 'treino_ref') and exercicio.treino_ref:
        return exercicio.treino_ref.id
    return ""


def _get_treino_codigo(exercicio):
    """Retorna o código do treino para ordenação (fallback para string vazia)

    IMPORTANTE: não usa TreinoService.get_by_id() aqui. Os exercícios
    passados a esta função vêm de ExercicioService.get_exercicios_dos_treinos(),
    que já anexa `treino_ref` a cada exercício num único batch (query com
    IN, feita uma vez para todos os treinos envolvidos). Buscar o treino
    de novo por id, um a um, transformava esta função -- usada como chave
    de ordenação, ou seja, chamada uma vez por exercício -- numa query SQL
    extra por exercício (N+1) toda vez que a Tabela de Progresso carregava.
    """
    treino_ref = getattr(exercicio, 'treino_ref', None)
    return treino_ref.codigo if treino_ref else ""


@stats_bp.route("/estatisticas")
@login_required
def estatisticas():
    """Página de estatísticas"""
    # `registros` e `exercicios` eram buscados aqui (histórico inteiro +
    # séries, e o catálogo completo de exercícios) mas nenhum dos dois era
    # usado nesta função nem passado ao template —
    # calcular_por_musculo()/calcular_por_treino() buscam seus próprios
    # dados internamente. Eram duas queries completas descartadas em toda
    # visita à página.
    # Usado só nos pills de filtro da seção "Evolução do Volume" -- restrito
    # à versão ativa (não TreinoService.get_all(), que traria também
    # treinos de versões antigas/encerradas do usuário).
    treinos = TreinoService.get_da_versao_ativa()
    
    musculos_obj = MusculoService.get_all()
    musculos = [m.nome_exibicao for m in musculos_obj]
    
    musculo_stats = EstatisticaService.calcular_por_musculo()
    treino_stats = EstatisticaService.calcular_por_treino()

    musculo_destaque = None
    if musculo_stats:
        musculos_com_volume = {k: v for k, v in musculo_stats.items() if v['volume_total'] > 0}
        if musculos_com_volume:
            musculo_destaque = max(musculos_com_volume, key=lambda k: musculos_com_volume[k]['volume_total'])

    volume_maximo_musculo = max((v['volume_total'] for v in musculo_stats.values()), default=0)
    
    return render_template("stats/estatisticas.html",
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats,
                         treinos=treinos,
                         musculos=musculos,
                         musculo_destaque=musculo_destaque,
                         volume_maximo_musculo=volume_maximo_musculo)


@stats_bp.route("/visualizar/tabela")
@login_required
def visualizar_tabela():
    """Tabela de progresso"""
    treino_selecionado = request.args.get("treino", "")
    musculo_selecionado = request.args.get("musculo", "")
    ordenar = request.args.get("ordenar", "exercicio")
    semanas_filtro = request.args.get("semanas", "todas")
    
    data_inicio = datetime.now(timezone.utc) - timedelta(days=DIAS_HISTORICO_TABELA_PROGRESSO)
    registros = RegistroService.get_all(load_series=True, data_inicio=data_inicio)
    exercicios = ExercicioService.get_exercicios_dos_treinos()
    treinos = TreinoService.get_all()
    musculos_obj = MusculoService.get_all()
    musculos = [m.nome_exibicao for m in musculos_obj]

    # Filtrar exercícios
    exercicios_filtrados = []
    for ex in exercicios:
        # Filtro por treino (apenas se o exercício tiver treino associado)
        if treino_selecionado:
            treino_id = _get_treino_id(ex)
            if str(treino_id) != str(treino_selecionado):
                continue
        
        # Filtro por músculo
        if musculo_selecionado:
            musculo_nome = ex.musculo_nome or ""
            if musculo_nome != musculo_selecionado:
                continue
        
        exercicios_filtrados.append(ex)
    
    # Ordenar
    if ordenar == "musculo":
        exercicios_filtrados.sort(key=lambda x: (x.musculo_ref.nome_exibicao if x.musculo_ref else "", x.nome))
    else:
        # Ordenar por código do treino (se existir) ou string vazia, depois por nome
        exercicios_filtrados.sort(key=lambda x: (_get_treino_codigo(x), x.nome))
    
    # Organizar dados para a tabela
    dados_tabela = EstatisticaService.preparar_dados_tabela(
        exercicios_filtrados, registros, semanas_filtro, request.args
    )

    # Dados 100% serializáveis (dicts/listas/primitivos) para a visão em
    # cards do mobile: a tabela pivotada acima exige rolagem lateral, que
    # funciona mal em telas pequenas -- no mobile trocamos por um card por
    # exercício, com a evolução semana a semana em lista vertical. Reaproveita
    # a mesma matriz `registros_por_exercicio`/`semanas` já calculada acima,
    # sem nenhuma query extra.
    dados_mobile = []
    for ex in exercicios_filtrados:
        chave_exercicio = f"{ex.tipo}_{ex.id}"
        registros_ex = dados_tabela['registros_por_exercicio'].get(chave_exercicio, {})

        semanas_ex = []
        for semana in dados_tabela['semanas']:
            registro = registros_ex.get(semana['key'])
            if registro and registro.get('series'):
                primeira_serie = registro['series'][0]
                semanas_ex.append({
                    'periodo': semana['periodo'],
                    'semana': semana['semana'],
                    'carga': primeira_serie['carga'],
                    'repeticoes': primeira_serie['repeticoes'],
                    'num_series': len(registro['series']),
                })
            else:
                semanas_ex.append({
                    'periodo': semana['periodo'],
                    'semana': semana['semana'],
                    'carga': None,
                    'repeticoes': None,
                    'num_series': 0,
                })

        dados_mobile.append({
            'nome': ex.nome,
            'treino_codigo': _get_treino_codigo(ex) or 'N/A',
            'musculo': ex.musculo_nome or 'N/A',
            'semanas': semanas_ex,
        })

    return render_template("stats/visualizar_tabela.html",
                         treinos=treinos,
                         treino_selecionado=treino_selecionado,
                         musculos=musculos,
                         musculo_selecionado=musculo_selecionado,
                         ordenar=ordenar,
                         exercicios=exercicios_filtrados,
                         semanas=dados_tabela['semanas'],
                         registros_por_exercicio=dados_tabela['registros_por_exercicio'],
                         dados_mobile=dados_mobile,
                         semanas_selecionadas=semanas_filtro,
                         semanas_selecionadas_lista=dados_tabela['semanas_selecionadas_lista'],
                         periodos_disponiveis=dados_tabela['periodos_disponiveis'])