from flask import Blueprint, render_template, request
from flask_login import login_required
from datetime import datetime, timedelta, timezone
from itertools import groupby
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
from services.versao_service import VersaoService
from utils.decorators import acesso_premium_required
from utils.date_utils import data_para_periodo, data_para_semana
import logging

stats_bp = Blueprint('stats', __name__)
logger = logging.getLogger(__name__)

# Tabela de Progresso: antes trazia TODO o histórico de registros/séries
# do usuário (podendo passar de milhares de linhas com o tempo). A tela
# abre já mostrando as últimas 3 semanas, mas permite rolar para o lado
# e ver semanas mais antigas -- por isso a janela buscada é maior que
# 3 semanas (12 semanas de histórico navegável).
NUM_SEMANAS_HISTORICO = 12
DIAS_HISTORICO_TABELA_PROGRESSO = NUM_SEMANAS_HISTORICO * 7 + 7  # folga de 1 semana


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


def _get_versao_id(exercicio):
    """Retorna o id da versão (VersaoGlobal) do treino atual do exercício.

    Usa o mesmo `treino_ref` já anexado em lote por
    ExercicioService.get_exercicios_dos_treinos() -- sem query extra por
    exercício. Um exercício sem treino associado (não deveria acontecer
    aqui, já que a função só traz exercícios de algum treino) retorna None.
    """
    treino_ref = getattr(exercicio, 'treino_ref', None)
    return treino_ref.versao_id if treino_ref else None


def _gerar_semanas_calendario(hoje, quantidade):
    """Gera as últimas `quantidade` semanas por CALENDÁRIO (mais antiga ->
    mais recente), e não a partir de quais semanas têm registro salvo.

    Antes, a lista de colunas da tabela vinha só das semanas que tinham
    pelo menos um registro -- se o usuário só tivesse treinado numa
    semana recente, só uma coluna aparecia (em vez de mostrar as 3
    últimas semanas com as mais antigas em branco). Isso também causava
    um bug visual: a largura das colunas era calculada supondo 3 semanas,
    então com menos colunas reais sobrava/vazava layout.

    A chave de cada semana usa `data_para_periodo`/`data_para_semana`,
    as MESMAS funções usadas em routes/register_routes.py ao salvar um
    registro -- então bate exatamente com a chave gravada no banco
    (`f"{periodo}_{semana}"`, ver EstatisticaService.preparar_dados_tabela).
    `semana_do_mes` (1ª, 2ª, 3ª... para exibição) é calculada direto do
    dia do mês, não depende de existir registro naquela semana.
    """
    semanas = []
    for i in range(quantidade - 1, -1, -1):
        data_semana = (hoje - timedelta(weeks=i)).date()
        periodo = data_para_periodo(data_semana)
        semana_iso = data_para_semana(data_semana)
        semana_do_mes = ((data_semana.day - 1) // 7) + 1
        semanas.append({
            'periodo': periodo,
            'semana': semana_iso,
            'semana_do_mes': semana_do_mes,
            'key': f"{periodo}_{semana_iso}",
        })
    return semanas


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
    """Tabela de progresso no layout de planilha, com filtro por versão.

    Único filtro disponível é por versão do plano de treino do usuário
    (`versao_id` na querystring) -- os demais (treino/músculo/ordenar/
    semanas) continuam removidos. As colunas de semana são geradas por
    CALENDÁRIO (as últimas NUM_SEMANAS_HISTORICO semanas a partir de
    hoje, sempre as mesmas independente de haver registro ou não -- ver
    `_gerar_semanas_calendario`), preenchidas com os dados que existirem;
    o template usa JS só para posicionar a rolagem inicial nas 3 últimas
    semanas (mais recentes = colunas mais à direita).

    Não existe coluna "Treino" (bloco A/B/C/D/E) -- os exercícios
    continuam agrupados por treino apenas para alternar a cor de fundo do
    bloco (zebra por bloco inteiro, não por linha) e para inserir uma
    linha espaçadora em branco entre um treino e outro, replicando o
    layout de referência. O cabeçalho mostra "Nª Semana / Mês" acima de
    cada par Carga/Rep.
    """
    versao_id = request.args.get('versao_id', '').strip()
    versoes = VersaoService.get_all()

    data_inicio = datetime.now(timezone.utc) - timedelta(days=DIAS_HISTORICO_TABELA_PROGRESSO)
    registros = RegistroService.get_all(load_series=True, data_inicio=data_inicio)
    exercicios = ExercicioService.get_exercicios_dos_treinos()

    if versao_id:
        exercicios = [ex for ex in exercicios if str(_get_versao_id(ex)) == versao_id]

    # Ordena por código do treino (para poder agrupar em blocos consecutivos)
    # e, dentro do treino, por nome.
    exercicios.sort(key=lambda x: (_get_treino_codigo(x), x.nome))

    dados_tabela = EstatisticaService.preparar_dados_tabela(
        exercicios, registros, "todas", {}
    )

    # Colunas de semana fixas por calendário -- não dependem de existir
    # registro (ver docstring de _gerar_semanas_calendario). É essa lista
    # que decide quantas/quais colunas a tabela mostra, não mais
    # `dados_tabela['semanas']` (que só tinha semanas com registro).
    semanas = _gerar_semanas_calendario(datetime.now(timezone.utc), NUM_SEMANAS_HISTORICO)

    # Agrupa os exercícios em blocos por treino -- cada bloco vira um grupo
    # de linhas com a mesma cor (zebra por bloco) e, entre um bloco e o
    # próximo, o template insere uma linha espaçadora. Já resolve, para
    # cada exercício, a carga/repetições da primeira série em cada semana
    # (em branco quando não há registro naquela semana).
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

        grupos_treino.append({'exercicios': exercicios_grupo})

    return render_template("stats/visualizar_tabela.html",
                         semanas=semanas,
                         grupos_treino=grupos_treino,
                         semanas_visiveis_padrao=3,
                         versoes=versoes,
                         versao_selecionada=versao_id)