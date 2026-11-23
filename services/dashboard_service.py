"""Serviço de agregações do dashboard operacional do professor.

Todas as queries aqui são SEMPRE escopadas a um professor_id explícito
(nunca a partir de um ID vindo do frontend) e SEMPRE consideram apenas
vínculos AlunoProfessor.ativo=True com User.ativo=True do lado do
aluno -- mesmo filtro já usado em User.get_alunos() e em
professor_routes.listar_alunos.

Números calculados aqui, nenhum mockado:
  - alunos_ativos / alunos_novos_mes: contagem de AlunoProfessor
  - treinaram_hoje: COUNT(DISTINCT user_id) em registros_treino na
    data de hoje (fuso America/Sao_Paulo, mesmo fuso usado na saudação
    do dashboard do aluno)
  - aderencia_pct: ver ADERENCIA_DEFINICAO abaixo -- não existia
    nenhuma métrica de aderência no sistema antes desta feature
  - alunos_atencao: alunos com 7+ dias sem registrar treino (ou nunca
    treinaram), ordenados por tempo parado
  - treinos_revisao: alunos cuja versão ativa está há 60+ dias sem
    troca (ver REVISAO_DEFINICAO) -- não existia conceito de "versão
    aguardando revisão" no sistema; regra definida aqui e documentada
  - atividade_recente: últimos registros de treino dos alunos do
    professor, já com nome do aluno e do treino (sem N+1)
  - grafico_30_dias: contagem de treinos/dia dos alunos do professor,
    para o gráfico "Treinos realizados nos últimos 30 dias"
  - alertas: lista única para o card "O que precisa da sua atenção",
    um item por (aluno, tipo) -- ver ALERTAS_DEFINICAO

ALERTAS_DEFINICAO (lote 3):
  - sem_treinar: 7+ dias sem registrar treino (mesma regra de
    alunos_atencao). Chave: data do último treino ("nunca" se nunca
    treinou) -- marcar como visto esconde até o aluno treinar e parar
    de novo.
  - ritmo: "treinando abaixo do ritmo habitual". Dias com treino nos
    últimos 14 dias comparados com a média por quinzena das 6 semanas
    anteriores. Só entra quem costuma treinar (média >= 3 dias por
    quinzena) e caiu para a metade ou menos; quem já está "sem treinar"
    fica só naquele alerta. Não existe meta semanal por aluno no
    sistema, então o "habitual" é o próprio histórico dele. Chave: a
    semana (ISO) -- visto esconde até a semana seguinte.
  - revisao: versão ativa há 60+ dias (REVISAO_DEFINICAO). Chave: id
    da versão -- volta quando houver outra versão parada.
  - sugestao: ficha enviada como sugestão (lote 4) sem resposta do
    aluno há 3+ dias. Chave: id do envio.
  - recorde: exercício em que a maior carga dos últimos 7 dias passou
    a maior carga de antes (precisa ter histórico anterior; cardio fica
    de fora). Alerta positivo, para o professor parabenizar. Chave: a
    semana (ISO).

ADERENCIA_DEFINICAO: o documento de especificação sugere "dias com
treino / dias esperados de treino", mas o sistema não tem (e esta
tarefa não pediu para criar) um campo de meta semanal de treino por
aluno -- não dá para calcular "dias esperados" sem inventar um dado
que não existe. Definição adotada, na ausência de meta individual:
    aderência = (Σ dias distintos com treino de cada aluno no período)
                / (30 × número de alunos ativos) × 100
ou seja, "em média, em quantos dos últimos 30 dias os alunos
treinaram". É uma simplificação: um aluno que entrou no meio do
período conta os 30 dias no denominador mesmo assim (leve
subestimação para alunos novos). Documentado aqui e no e-mail de
entrega -- se o usuário vier a criar uma meta semanal por aluno no
futuro, esta é a função a ajustar (um único lugar).

REVISAO_DEFINICAO: não existe no sistema um conceito de "versão
aguardando publicação" (não há rascunho/publicado -- toda versão
criada já vale imediatamente) nem um campo de "treino vencido". A
única informação real disponível é há quanto tempo a versão ativa do
aluno está no ar (versoes_globais.data_inicio, com data_fim IS NULL).
Regra adotada: versão ativa há 60+ dias sem ter sido trocada (nova
versão criada) conta como "aguardando revisão".
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, case

from models import (db, AlunoProfessor, User, RegistroTreino, TreinoVersao, VersaoGlobal,
                    HistoricoTreino, ExercicioUsuario, ExercicioSistema, AlertaVistoProfessor)
from .base_service import BaseService, CacheService

import logging

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_TTL_SEGUNDOS = 60

DIAS_SEM_TREINAR_ATENCAO = 7
LIMITE_ALUNOS_ATENCAO_EXIBIDOS = 5

DIAS_VERSAO_SEM_REVISAO = 60
LIMITE_ALUNOS_REVISAO_EXIBIDOS = 5

LIMITE_ATIVIDADE_RECENTE = 8

# Alertas (lote 3) -- ver ALERTAS_DEFINICAO no docstring do módulo.
TIPOS_ALERTA = ('sem_treinar', 'ritmo', 'revisao', 'sugestao', 'recorde')
DIAS_RITMO_RECENTE = 14
SEMANAS_RITMO_BASE = 6
MIN_DIAS_BASE_POR_QUINZENA = 3
FRACAO_RITMO_BAIXO = 0.5
DIAS_RECORDE = 7
LIMITE_ALERTAS = 60

FUSO_BR = ZoneInfo('America/Sao_Paulo')


def _hoje_br():
    """Data de 'hoje' no fuso America/Sao_Paulo, como datetime naive à
    meia-noite -- mesma convenção de RegistroTreino.data_registro (ver
    services/registro_service.py: 'data_meia_noite')."""
    hoje = datetime.now(FUSO_BR).date()
    return datetime(hoje.year, hoje.month, hoje.day)


class DashboardService(BaseService):
    """Agregações do painel operacional do professor."""

    @staticmethod
    def dados_professor(professor_id):
        """Monta todos os dados do dashboard de um professor em uma
        única chamada. Cacheado por professor_id (TTL curto) -- só
        agregados/contagens, nada de autorização ou billing."""
        try:
            cache_key = f"dashboard_professor:{professor_id}"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            hoje = _hoje_br()

            alunos = (User.query
                      .join(AlunoProfessor, AlunoProfessor.aluno_id == User.id)
                      .filter(AlunoProfessor.professor_id == professor_id,
                              AlunoProfessor.ativo == True,
                              User.ativo == True)
                      .order_by(User.nome_completo)
                      .all())
            aluno_ids = [a.id for a in alunos]
            alunos_por_id = {a.id: a for a in alunos}

            parados = DashboardService._alunos_parados(alunos_por_id, aluno_ids, hoje)
            revisao = DashboardService._versoes_paradas(alunos_por_id, aluno_ids, hoje)
            dados = {
                'total_alunos': len(alunos),
                'alunos_novos_mes': DashboardService._alunos_novos_mes(professor_id, hoje),
                'treinaram_hoje': DashboardService._treinaram_hoje(aluno_ids, hoje),
                'aderencia': DashboardService._aderencia(aluno_ids, hoje),
                'alunos_atencao': {'total': len(parados), 'itens': parados[:LIMITE_ALUNOS_ATENCAO_EXIBIDOS]},
                'treinos_revisao': {'total': len(revisao), 'itens': revisao[:LIMITE_ALUNOS_REVISAO_EXIBIDOS]},
                'alertas': DashboardService._alertas(alunos_por_id, aluno_ids, hoje, parados, revisao,
                                                     professor_id=professor_id),
                'atividade_recente': DashboardService._atividade_recente(aluno_ids),
                'grafico_30_dias': DashboardService._grafico_30_dias(aluno_ids, hoje),
            }

            CacheService.set(cache_key, dados, ttl_seconds=DASHBOARD_CACHE_TTL_SEGUNDOS)
            return dados
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao montar dashboard do professor {professor_id}")
            return DashboardService._dados_vazios()

    @staticmethod
    def _dados_vazios():
        return {
            'total_alunos': 0, 'alunos_novos_mes': 0, 'treinaram_hoje': 0,
            'aderencia': {'pct': None, 'pct_anterior': None},
            'alunos_atencao': {'total': 0, 'itens': []},
            'treinos_revisao': {'total': 0, 'itens': []},
            'alertas': [],
            'atividade_recente': [], 'grafico_30_dias': {'labels': [], 'valores': []},
        }

    @staticmethod
    def _alunos_novos_mes(professor_id, hoje):
        # data_associacao é DateTime(timezone=True), guardada sempre em
        # UTC (datetime.now(timezone.utc), ver professor_routes.py e
        # auth_routes.py) -- por isso o limite aqui usa UTC (mesmo
        # padrão já usado em EstatisticaService.get_progresso_ultimos_30_dias
        # para filtrar RegistroTreino), em vez do fuso local usado só
        # para decidir o que é "hoje" nas métricas baseadas em
        # data_registro (que é naive de propósito).
        inicio_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (AlunoProfessor.query
                .filter(AlunoProfessor.professor_id == professor_id,
                        AlunoProfessor.ativo == True,
                        AlunoProfessor.data_associacao >= inicio_mes)
                .count())

    @staticmethod
    def _treinaram_hoje(aluno_ids, hoje):
        if not aluno_ids:
            return 0
        return (db.session.query(func.count(func.distinct(RegistroTreino.user_id)))
                .filter(RegistroTreino.user_id.in_(aluno_ids),
                        RegistroTreino.data_registro == hoje)
                .scalar()) or 0

    @staticmethod
    def _dias_distintos_com_treino(aluno_ids, inicio, fim):
        """Conta pares distintos (user_id, data_registro) no intervalo
        [inicio, fim) -- ou seja, quantos "aluno-dias" tiveram pelo
        menos um treino registrado. Usado pela aderência.

        Implementado como COUNT(*) sobre um SELECT DISTINCT (via
        .distinct().count(), que o SQLAlchemy traduz para uma subquery
        -- portável entre SQLite (testes) e Postgres (produção), ao
        contrário de um COUNT(DISTINCT (a, b)) direto, que o SQLite
        não suporta em sintaxe de tupla."""
        if not aluno_ids:
            return 0
        return (db.session.query(RegistroTreino.user_id, RegistroTreino.data_registro)
                .filter(RegistroTreino.user_id.in_(aluno_ids),
                        RegistroTreino.data_registro >= inicio,
                        RegistroTreino.data_registro < fim)
                .distinct()
                .count())

    @staticmethod
    def _aderencia(aluno_ids, hoje):
        """Ver ADERENCIA_DEFINICAO no docstring do módulo."""
        n_alunos = len(aluno_ids)
        if n_alunos == 0:
            return {'pct': None, 'pct_anterior': None}

        inicio_periodo_atual = hoje - timedelta(days=30)
        dias_periodo_atual = DashboardService._dias_distintos_com_treino(
            aluno_ids, inicio_periodo_atual, hoje + timedelta(days=1))
        pct = round(100 * dias_periodo_atual / (30 * n_alunos), 0)

        inicio_periodo_anterior = hoje - timedelta(days=60)
        dias_periodo_anterior = DashboardService._dias_distintos_com_treino(
            aluno_ids, inicio_periodo_anterior, inicio_periodo_atual)
        pct_anterior = round(100 * dias_periodo_anterior / (30 * n_alunos), 0)

        return {'pct': pct, 'pct_anterior': pct_anterior}

    @staticmethod
    def _alunos_atencao(alunos_por_id, aluno_ids, hoje):
        """Alunos com 7+ dias sem treinar, já cortado para o card."""
        itens = DashboardService._alunos_parados(alunos_por_id, aluno_ids, hoje)
        return {'total': len(itens), 'itens': itens[:LIMITE_ALUNOS_ATENCAO_EXIBIDOS]}

    @staticmethod
    def _alunos_parados(alunos_por_id, aluno_ids, hoje):
        """Alunos com 7+ dias sem treinar (ou que nunca treinaram),
        ordenados pelo maior tempo parado, lista completa. Uma única
        query agregada (MAX(data_registro) por aluno) -- sem N+1."""
        if not aluno_ids:
            return []

        ultimo_por_aluno = dict(
            db.session.query(RegistroTreino.user_id, func.max(RegistroTreino.data_registro))
            .filter(RegistroTreino.user_id.in_(aluno_ids))
            .group_by(RegistroTreino.user_id)
            .all()
        )

        itens = []
        for aluno_id in aluno_ids:
            aluno = alunos_por_id[aluno_id]
            ultimo = ultimo_por_aluno.get(aluno_id)
            if ultimo is not None:
                dias_parado = (hoje.date() - ultimo.date()).days
                nunca_treinou = False
            else:
                # Nunca treinou -- usa a data de vínculo como referência
                # de "tempo parado" (não há outro dado disponível).
                vinculo = next((v for v in aluno.professor_associado if v.professor_id and v.ativo), None)
                data_referencia = vinculo.data_associacao.date() if vinculo and vinculo.data_associacao else hoje.date()
                dias_parado = (hoje.date() - data_referencia).days
                nunca_treinou = True

            if dias_parado >= DIAS_SEM_TREINAR_ATENCAO:
                itens.append({
                    'aluno_id': aluno_id,
                    'nome': aluno.nome_completo or aluno.username,
                    'dias_parado': dias_parado,
                    'nunca_treinou': nunca_treinou,
                    'ultimo': ultimo.date().isoformat() if ultimo is not None else None,
                })

        itens.sort(key=lambda i: i['dias_parado'], reverse=True)
        return itens

    @staticmethod
    def _treinos_revisao(alunos_por_id, aluno_ids, hoje):
        """Versões paradas há 60+ dias, já cortado para o card."""
        itens = DashboardService._versoes_paradas(alunos_por_id, aluno_ids, hoje)
        return {'total': len(itens), 'itens': itens[:LIMITE_ALUNOS_REVISAO_EXIBIDOS]}

    @staticmethod
    def _versoes_paradas(alunos_por_id, aluno_ids, hoje):
        """Ver REVISAO_DEFINICAO no docstring do módulo: versão ativa
        (data_fim IS NULL) há 60+ dias no ar. Lista completa."""
        if not aluno_ids:
            return []

        limite = hoje - timedelta(days=DIAS_VERSAO_SEM_REVISAO)
        versoes_ativas = (VersaoGlobal.query
                           .filter(VersaoGlobal.user_id.in_(aluno_ids),
                                   VersaoGlobal.data_fim.is_(None),
                                   VersaoGlobal.data_inicio <= limite.date())
                           .all())

        itens = []
        for v in versoes_ativas:
            aluno = alunos_por_id.get(v.user_id)
            if not aluno:
                continue
            dias_sem_revisao = (hoje.date() - v.data_inicio).days
            itens.append({
                'aluno_id': v.user_id,
                'nome': aluno.nome_completo or aluno.username,
                'dias_sem_revisao': dias_sem_revisao,
                'numero_versao': v.numero_versao,
                'versao_id': v.id,
            })

        itens.sort(key=lambda i: i['dias_sem_revisao'], reverse=True)
        return itens

    @staticmethod
    def _atividade_recente(aluno_ids):
        """Últimos registros de treino dos alunos do professor, com
        nome do aluno e do treino -- um único JOIN, sem N+1."""
        if not aluno_ids:
            return []

        # Uma linha por SESSÃO (aluno + treino + dia): cada exercício salvo
        # é um RegistroTreino, então listar registros repetia o mesmo
        # treino uma vez por exercício. Agrupa no banco e conta os
        # exercícios de cada sessão.
        dia = func.date(RegistroTreino.data_registro)
        linhas = (db.session.query(RegistroTreino.user_id, RegistroTreino.treino_versao_id, dia.label('dia'),
                                   func.max(RegistroTreino.data_registro).label('quando'),
                                   func.count(RegistroTreino.id).label('exercicios'))
                  .filter(RegistroTreino.user_id.in_(aluno_ids))
                  .group_by(RegistroTreino.user_id, RegistroTreino.treino_versao_id, dia)
                  .order_by(dia.desc(), func.max(RegistroTreino.created_at).desc().nullslast())
                  .limit(LIMITE_ATIVIDADE_RECENTE)
                  .all())
        if not linhas:
            return []
        usuarios = {u.id: u for u in User.query.filter(User.id.in_({l.user_id for l in linhas})).all()}
        treinos = {t.id: t for t in TreinoVersao.query.filter(TreinoVersao.id.in_({l.treino_versao_id for l in linhas})).all()}

        itens = []
        for l in linhas:
            u, t = usuarios.get(l.user_id), treinos.get(l.treino_versao_id)
            if not u or not t:
                continue
            itens.append({
                'aluno_nome': u.nome_completo or u.username,
                'treino_nome': t.nome_treino,
                'treino_codigo': t.codigo,
                'quando': l.quando,
                'exercicios': l.exercicios,
            })
        return itens

    @staticmethod
    def _grafico_30_dias(aluno_ids, hoje):
        """Treinos (sessões: aluno + treino + dia) por dia dos alunos do
        professor, últimos 30 dias -- para o gráfico "Treinos nos últimos
        30 dias". Contava registros (um por exercício), o que multiplicava
        cada treino pelo número de exercícios."""
        labels = []
        valores_por_dia = {}
        inicio = hoje - timedelta(days=29)

        if aluno_ids:
            sessoes = (db.session.query(RegistroTreino.data_registro, RegistroTreino.user_id,
                                        RegistroTreino.treino_versao_id)
                       .filter(RegistroTreino.user_id.in_(aluno_ids),
                               RegistroTreino.data_registro >= inicio)
                       .distinct()
                       .all())
            for d, user_id, treino_id in {(d.date(), u, t) for d, u, t in sessoes}:
                valores_por_dia[d] = valores_por_dia.get(d, 0) + 1

        valores = []
        for i in range(30):
            dia = (inicio + timedelta(days=i)).date()
            labels.append(dia.strftime('%d/%m'))
            valores.append(valores_por_dia.get(dia, 0))

        return {'labels': labels, 'valores': valores}

    # ------------------------------------------------------------------
    # Alertas (lote 3) -- ver ALERTAS_DEFINICAO no docstring do módulo
    # ------------------------------------------------------------------

    @staticmethod
    def _alertas(alunos_por_id, aluno_ids, hoje, parados, revisao, professor_id=None):
        """Lista única de alertas, um item por (aluno, tipo). Ordem: os
        que pedem ação primeiro (sem treinar, ritmo, revisão), recordes
        por último; dentro de cada tipo, o caso mais forte primeiro."""
        if not aluno_ids:
            return []
        ano, semana, _ = hoje.isocalendar()
        chave_semana = f'{ano}-W{semana:02d}'

        def base(aluno_id, tipo, chave):
            aluno = alunos_por_id[aluno_id]
            return {
                'tipo': tipo,
                'aluno_id': aluno_id,
                'nome': aluno.nome_completo or aluno.username,
                'primeiro_nome': (aluno.nome_completo or aluno.username).split()[0],
                'telefone': _telefone_whatsapp(aluno.telefone),
                'chave': chave,
            }

        alertas = []
        for p in parados:
            a = base(p['aluno_id'], 'sem_treinar', p['ultimo'] or 'nunca')
            a['detalhe'] = ('nunca registrou treino' if p['nunca_treinou']
                            else f"{p['dias_parado']} dias sem treinar")
            a['peso'] = p['dias_parado']
            alertas.append(a)

        ids_parados = {p['aluno_id'] for p in parados}
        for r in DashboardService._abaixo_do_ritmo(aluno_ids, hoje, ids_parados):
            a = base(r['aluno_id'], 'ritmo', chave_semana)
            vezes = 'vez' if r['recente'] == 1 else 'vezes'
            a['detalhe'] = (f"treinou {r['recente']} {vezes} em 2 semanas"
                            f" · costuma {r['habitual']}")
            a['peso'] = r['habitual'] - r['recente']
            alertas.append(a)

        for v in revisao:
            a = base(v['aluno_id'], 'revisao', f"v{v['versao_id']}")
            a['detalhe'] = f"ficha v{v['numero_versao']} há {v['dias_sem_revisao']} dias sem troca"
            a['peso'] = v['dias_sem_revisao']
            alertas.append(a)

        if professor_id:
            from services.ficha_lote_service import FichaLoteService
            for e in FichaLoteService.sugestoes_sem_resposta(professor_id, aluno_ids):
                if e.aluno_id not in alunos_por_id:
                    continue
                criada = e.criada_em if e.criada_em.tzinfo else e.criada_em.replace(tzinfo=timezone.utc)
                dias = (datetime.now(timezone.utc) - criada).days
                a = base(e.aluno_id, 'sugestao', f's{e.id}')
                a['detalhe'] = f'"{e.descricao}" sem resposta há {dias} dias'
                a['peso'] = dias
                alertas.append(a)

        for r in DashboardService._recordes_da_semana(aluno_ids, hoje):
            a = base(r['aluno_id'], 'recorde', chave_semana)
            n = r['total']
            texto = f"{n} recorde{'s' if n != 1 else ''} na semana"
            if r['exercicio']:
                texto += f" · {r['exercicio']}: {_kg(r['carga'])} (antes {_kg(r['anterior'])})"
            a['detalhe'] = texto
            a['peso'] = n
            alertas.append(a)

        ordem = {t: i for i, t in enumerate(TIPOS_ALERTA)}
        alertas.sort(key=lambda a: (ordem[a['tipo']], -a['peso'], a['nome'].lower()))
        return alertas[:LIMITE_ALERTAS]

    @staticmethod
    def _abaixo_do_ritmo(aluno_ids, hoje, ignorar):
        """Quem costuma treinar e caiu para a metade (ou menos) nas
        últimas 2 semanas. Uma query: dias distintos com treino por aluno
        nas últimas 8 semanas, separados em "recente" e "base"."""
        dias_base = SEMANAS_RITMO_BASE * 7
        inicio_recente = hoje - timedelta(days=DIAS_RITMO_RECENTE - 1)
        inicio_base = inicio_recente - timedelta(days=dias_base)
        linhas = (db.session.query(RegistroTreino.user_id, RegistroTreino.data_registro)
                  .filter(RegistroTreino.user_id.in_(aluno_ids),
                          RegistroTreino.data_registro >= inicio_base,
                          RegistroTreino.data_registro < hoje + timedelta(days=1))
                  .distinct()
                  .all())
        recente, antes = {}, {}
        for user_id, d in {(u, d.date()) for u, d in linhas}:
            alvo = recente if d >= inicio_recente.date() else antes
            alvo[user_id] = alvo.get(user_id, 0) + 1

        quinzenas_base = dias_base / DIAS_RITMO_RECENTE
        itens = []
        for aluno_id in aluno_ids:
            if aluno_id in ignorar:
                continue
            habitual = antes.get(aluno_id, 0) / quinzenas_base
            atual = recente.get(aluno_id, 0)
            if habitual >= MIN_DIAS_BASE_POR_QUINZENA and atual <= habitual * FRACAO_RITMO_BAIXO:
                itens.append({'aluno_id': aluno_id, 'recente': atual, 'habitual': round(habitual)})
        return itens

    @staticmethod
    def _recordes_da_semana(aluno_ids, hoje):
        """Exercícios em que a maior carga dos últimos 7 dias passou a
        maior carga de antes. Uma query agregada (MAX(carga) por aluno,
        exercício e "é desta semana"); cardio (duracao_segundos) fora."""
        limite = hoje - timedelta(days=DIAS_RECORDE - 1)
        recente = case((RegistroTreino.data_registro >= limite, 1), else_=0)
        linhas = (db.session.query(RegistroTreino.user_id, RegistroTreino.exercicio_usuario_id,
                                   RegistroTreino.exercicio_base_id, recente.label('recente'),
                                   func.max(HistoricoTreino.carga).label('carga'))
                  .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)
                  .filter(RegistroTreino.user_id.in_(aluno_ids),
                          RegistroTreino.data_registro < hoje + timedelta(days=1),
                          HistoricoTreino.duracao_segundos.is_(None),
                          HistoricoTreino.carga.isnot(None))
                  .group_by(RegistroTreino.user_id, RegistroTreino.exercicio_usuario_id,
                            RegistroTreino.exercicio_base_id, recente)
                  .all())
        por_ex = {}
        for user_id, eu_id, eb_id, eh_recente, carga in linhas:
            chave = (user_id, eu_id, eb_id)
            por_ex.setdefault(chave, {})[int(eh_recente)] = float(carga or 0)

        por_aluno = {}
        for (user_id, eu_id, eb_id), cargas in por_ex.items():
            nova, antiga = cargas.get(1), cargas.get(0)
            if not nova or not antiga or nova <= antiga:
                continue
            r = por_aluno.setdefault(user_id, {'aluno_id': user_id, 'total': 0, 'melhor': None})
            r['total'] += 1
            ganho = nova - antiga
            if r['melhor'] is None or ganho > r['melhor'][0]:
                r['melhor'] = (ganho, eu_id, eb_id, nova, antiga)

        ids_u = {r['melhor'][1] for r in por_aluno.values() if r['melhor'][1]}
        ids_b = {r['melhor'][2] for r in por_aluno.values() if r['melhor'][2]}
        nomes_u = dict(db.session.query(ExercicioUsuario.id, ExercicioUsuario.nome)
                       .filter(ExercicioUsuario.id.in_(ids_u)).all()) if ids_u else {}
        nomes_b = dict(db.session.query(ExercicioSistema.id, ExercicioSistema.nome)
                       .filter(ExercicioSistema.id.in_(ids_b)).all()) if ids_b else {}

        itens = []
        for r in por_aluno.values():
            _, eu_id, eb_id, nova, antiga = r['melhor']
            itens.append({
                'aluno_id': r['aluno_id'], 'total': r['total'],
                'exercicio': nomes_u.get(eu_id) if eu_id else nomes_b.get(eb_id),
                'carga': nova, 'anterior': antiga,
            })
        return itens

    @staticmethod
    def separar_vistos(professor_id, alertas):
        """Divide os alertas em (ativos, vistos). Fica fora do cache do
        painel de propósito: marcar como visto reflete na hora."""
        if not alertas:
            return [], []
        vistos = {(v.aluno_id, v.tipo): v.chave for v in
                  AlertaVistoProfessor.query.filter_by(professor_id=professor_id).all()}
        ativos, ocultos = [], []
        for a in alertas:
            (ocultos if vistos.get((a['aluno_id'], a['tipo'])) == a['chave'] else ativos).append(a)
        return ativos, ocultos

    @staticmethod
    def marcar_visto(professor_id, aluno_id, tipo, chave, desfazer=False):
        """Marca (ou desmarca) um alerta como visto. Só para aluno com
        vínculo ativo com este professor. Retorna False se não puder."""
        if tipo not in TIPOS_ALERTA or not chave or len(chave) > 40:
            return False
        vinculo = AlunoProfessor.query.filter_by(aluno_id=aluno_id, professor_id=professor_id,
                                                 ativo=True).first()
        if not vinculo:
            return False
        registro = AlertaVistoProfessor.query.filter_by(professor_id=professor_id, aluno_id=aluno_id,
                                                        tipo=tipo).first()
        if desfazer:
            if registro and registro.chave == chave:
                db.session.delete(registro)
        elif registro:
            registro.chave = chave
            registro.visto_em = datetime.now(timezone.utc)
        else:
            db.session.add(AlertaVistoProfessor(professor_id=professor_id, aluno_id=aluno_id,
                                                tipo=tipo, chave=chave))
        db.session.commit()
        return True


def _kg(valor):
    """80.0 -> '80 kg'; 37.5 -> '37,5 kg'."""
    v = float(valor)
    texto = str(int(v)) if v.is_integer() else f'{v:.1f}'.replace('.', ',')
    return f'{texto} kg'


def _telefone_whatsapp(telefone):
    """Só dígitos, com 55 na frente para número brasileiro (10 ou 11
    dígitos). None se não der para montar um link do WhatsApp."""
    if not telefone:
        return None
    digitos = ''.join(c for c in telefone if c.isdigit())
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    return digitos if 12 <= len(digitos) <= 13 else None
