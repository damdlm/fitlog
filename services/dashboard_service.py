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

from sqlalchemy import func

from models import db, AlunoProfessor, User, RegistroTreino, TreinoVersao, VersaoGlobal
from .base_service import BaseService, CacheService

import logging

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_TTL_SEGUNDOS = 60

DIAS_SEM_TREINAR_ATENCAO = 7
LIMITE_ALUNOS_ATENCAO_EXIBIDOS = 5

DIAS_VERSAO_SEM_REVISAO = 60
LIMITE_ALUNOS_REVISAO_EXIBIDOS = 5

LIMITE_ATIVIDADE_RECENTE = 8

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

            dados = {
                'total_alunos': len(alunos),
                'alunos_novos_mes': DashboardService._alunos_novos_mes(professor_id, hoje),
                'treinaram_hoje': DashboardService._treinaram_hoje(aluno_ids, hoje),
                'aderencia': DashboardService._aderencia(aluno_ids, hoje),
                'alunos_atencao': DashboardService._alunos_atencao(alunos_por_id, aluno_ids, hoje),
                'treinos_revisao': DashboardService._treinos_revisao(alunos_por_id, aluno_ids, hoje),
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
        """Alunos com 7+ dias sem treinar (ou que nunca treinaram),
        ordenados pelo maior tempo parado. Uma única query agregada
        (MAX(data_registro) por aluno) -- sem N+1."""
        if not aluno_ids:
            return {'total': 0, 'itens': []}

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
                })

        itens.sort(key=lambda i: i['dias_parado'], reverse=True)
        return {'total': len(itens), 'itens': itens[:LIMITE_ALUNOS_ATENCAO_EXIBIDOS]}

    @staticmethod
    def _treinos_revisao(alunos_por_id, aluno_ids, hoje):
        """Ver REVISAO_DEFINICAO no docstring do módulo: versão ativa
        (data_fim IS NULL) há 60+ dias no ar."""
        if not aluno_ids:
            return {'total': 0, 'itens': []}

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
            })

        itens.sort(key=lambda i: i['dias_sem_revisao'], reverse=True)
        return {'total': len(itens), 'itens': itens[:LIMITE_ALUNOS_REVISAO_EXIBIDOS]}

    @staticmethod
    def _atividade_recente(aluno_ids):
        """Últimos registros de treino dos alunos do professor, com
        nome do aluno e do treino -- um único JOIN, sem N+1."""
        if not aluno_ids:
            return []

        linhas = (db.session.query(RegistroTreino, User, TreinoVersao)
                  .join(User, User.id == RegistroTreino.user_id)
                  .join(TreinoVersao, TreinoVersao.id == RegistroTreino.treino_versao_id)
                  .filter(RegistroTreino.user_id.in_(aluno_ids))
                  .order_by(RegistroTreino.data_registro.desc(), RegistroTreino.created_at.desc())
                  .limit(LIMITE_ATIVIDADE_RECENTE)
                  .all())

        return [{
            'aluno_nome': u.nome_completo or u.username,
            'treino_nome': t.nome_treino,
            'treino_codigo': t.codigo,
            'quando': r.data_registro,
        } for r, u, t in linhas]

    @staticmethod
    def _grafico_30_dias(aluno_ids, hoje):
        """Contagem de registros/dia dos alunos do professor, últimos
        30 dias -- para o gráfico opcional de evolução."""
        labels = []
        valores_por_dia = {}
        inicio = hoje - timedelta(days=29)

        if aluno_ids:
            contagem = (db.session.query(
                            RegistroTreino.data_registro,
                            func.count(func.distinct(RegistroTreino.id)))
                        .filter(RegistroTreino.user_id.in_(aluno_ids),
                                RegistroTreino.data_registro >= inicio)
                        .group_by(RegistroTreino.data_registro)
                        .all())
            valores_por_dia = {d.date(): c for d, c in contagem}

        valores = []
        for i in range(30):
            dia = (inicio + timedelta(days=i)).date()
            labels.append(dia.strftime('%d/%m'))
            valores.append(valores_por_dia.get(dia, 0))

        return {'labels': labels, 'valores': valores}
