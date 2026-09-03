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
from utils.date_utils import MESES
import logging

stats_bp = Blueprint('stats', __name__)
logger = logging.getLogger(__name__)

# Tabela de Progresso: antes trazia TODO o histórico de registros/séries
# do usuário (podendo passar de milhares de linhas com o tempo). A tela
# abre já mostrando as últimas 3 semanas, mas permite rolar para o lado
# e ver semanas mais antigas -- por isso a janela buscada é maior que
# 3 semanas (90 dias cobrem ~12-13 semanas de histórico navegável),
# evitando trazer o histórico completo do banco a cada carregamento.
DIAS_HISTORICO_TABELA_PROGRESSO = 90


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
    semanas) continuam removidos. Busca todas as semanas dentro da janela
    de DIAS_HISTORICO_TABELA_PROGRESSO (`preparar_dados_tabela` é chamado
    com "todas") para permitir rolar a tabela e ver semanas mais antigas;
    o template usa JS só para posicionar a rolagem inicial nas 3 últimas
    semanas (mais recentes = colunas mais à direita).

    Não existe coluna "Treino" (bloco A/B/C/D/E) -- os exercícios
    continuam agrupados por treino apenas para alternar a cor de fundo do
    bloco (zebra por bloco inteiro, não por linha) e para inserir uma
    linha espaçadora em branco entre um treino e outro, replicando o
    layout de referência. O cabeçalho volta a mostrar "Nª Semana / Mês"
    acima de cada par Carga/Rep.
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

    # `preparar_dados_tabela` ordena semanas usando só o nome do mês (sem
    # ano), então períodos de anos diferentes com o mesmo mês colidiriam na
    # ordenação. Reordena aqui por (ano, mês, semana) usando o mapeamento de
    # meses já existente em date_utils, sem tocar na função compartilhada
    # (que tem teste unitário próprio). Semanas mais antigas ficam à
    # esquerda e as mais recentes à direita, como na planilha de referência.
    def _chave_semana(s):
        mes_nome, _, ano = s['periodo'].partition('/')
        ano_num = int(ano) if ano.isdigit() else 0
        return (ano_num, MESES.get(mes_nome.strip().lower(), 0), s['semana'])

    semanas = sorted(dados_tabela['semanas'], key=_chave_semana)

    # `RegistroTreino.semana` é preenchido em routes/register_routes.py com
    # `data_para_semana()`, que devolve a semana ISO *do ano* (1-53) -- por
    # isso a tabela mostrava números como "32ª Semana" em vez de "3ª Semana".
    # Aqui, em vez de mudar esse campo já gravado no banco (afetaria outras
    # telas e todo o histórico já salvo), recalcula-se só para exibição: como
    # `semanas` já está em ordem cronológica, dá pra numerar de novo a partir
    # de 1 sempre que o período (mês) mudar -- 1ª, 2ª, 3ª semana daquele mês,
    # na ordem em que houve treino registrado.
    contador_por_periodo = {}
    for s in semanas:
        contador_por_periodo[s['periodo']] = contador_por_periodo.get(s['periodo'], 0) + 1
        s['semana_do_mes'] = contador_por_periodo[s['periodo']]

    # Agrupa os exercícios em blocos por treino -- cada bloco vira um grupo
    # de linhas com a mesma cor (zebra por bloco) e, entre um bloco e o
    # próximo, o template insere uma linha espaçadora. Já resolve, para
    # cada exercício, a carga/repetições da primeira série em cada semana.
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