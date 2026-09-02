from flask import Blueprint, render_template
from flask_login import login_required
from datetime import datetime, timedelta, timezone
from itertools import groupby
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
from utils.decorators import acesso_premium_required
from utils.date_utils import MESES
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
@acesso_premium_required('estatisticas')
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
@acesso_premium_required('tabela_progresso')
def visualizar_tabela():
    """Tabela de progresso: sempre as últimas 3 semanas registradas, sem filtros.

    Tela reformulada para reproduzir o layout de planilha (Treino / Exercício
    fixos + colunas Carga/Rep. por semana) pedido pelo usuário -- não recebe
    mais parâmetros de filtro (treino/músculo/ordenar/semanas) da querystring,
    então `preparar_dados_tabela` é chamado sempre com "ultimas3" e sem
    request_args (o modo "personalizado" dele nunca é acionado aqui).
    """
    data_inicio = datetime.now(timezone.utc) - timedelta(days=DIAS_HISTORICO_TABELA_PROGRESSO)
    registros = RegistroService.get_all(load_series=True, data_inicio=data_inicio)
    exercicios = ExercicioService.get_exercicios_dos_treinos()

    # Ordena por código do treino (para poder agrupar em blocos consecutivos
    # com rowspan na coluna "Treino") e, dentro do treino, por nome.
    exercicios.sort(key=lambda x: (_get_treino_codigo(x), x.nome))

    dados_tabela = EstatisticaService.preparar_dados_tabela(
        exercicios, registros, "ultimas3", {}
    )

    # `preparar_dados_tabela` ordena semanas usando só o nome do mês (sem
    # ano), então períodos de anos diferentes com o mesmo mês colidiriam na
    # ordenação. Reordena aqui por (ano, mês, semana) usando o mapeamento de
    # meses já existente em date_utils, sem tocar na função compartilhada
    # (que tem teste unitário próprio).
    def _chave_semana(s):
        mes_nome, _, ano = s['periodo'].partition('/')
        ano_num = int(ano) if ano.isdigit() else 0
        return (ano_num, MESES.get(mes_nome.strip().lower(), 0), s['semana'])

    semanas = sorted(dados_tabela['semanas'], key=_chave_semana)

    # Agrupa os exercícios em blocos por treino (para a célula "Treino" com
    # rowspan) e já resolve, para cada exercício, a carga/repetições da
    # primeira série em cada uma das semanas exibidas.
    grupos_treino = []
    for codigo, exs in groupby(exercicios, key=_get_treino_codigo):
        exercicios_grupo = []
        for ex in exs:
            chave_exercicio = f"{ex.tipo}_{ex.id}"
            registros_ex = dados_tabela['registros_por_exercicio'].get(chave_exercicio, {})

            semanas_ex = []
            for semana in semanas:
                registro = registros_ex.get(semana['key'])
                if registro and registro.get('series'):
                    primeira_serie = registro['series'][0]
                    semanas_ex.append({
                        'carga': primeira_serie['carga'],
                        'repeticoes': primeira_serie['repeticoes'],
                    })
                else:
                    semanas_ex.append({'carga': None, 'repeticoes': None})

            exercicios_grupo.append({'nome': ex.nome, 'semanas': semanas_ex})

        grupos_treino.append({'codigo': codigo or '—', 'exercicios': exercicios_grupo})

    return render_template("stats/visualizar_tabela.html",
                         semanas=semanas,
                         grupos_treino=grupos_treino)