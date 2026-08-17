"""Serviço da tela "Melhores Alunos" (ranking geral entre alunos).

Regras de negócio (ver conversa com o usuário para o contexto completo):

1. Janela de 30 dias corridos (hoje - 29 até hoje, inclusive).
2. Critério 1 (principal): dias distintos com pelo menos um registro de
   treino no período.
3. Critério 2 (desempate): soma da duração das sessões válidas -- quando
   há mais de uma sessão no mesmo dia, usa só a MAIOR duração do dia
   (mesma lógica já usada no dashboard individual, em
   routes/aluno/main.py) em vez de somar todas, para não permitir inflar
   o tempo total criando várias sessões picadas no mesmo dia.
4. Critério 3 (desempate final): nome em ordem alfabética -- só para dar
   um resultado determinístico, nunca "aleatório" por causa da ordem do
   banco.
5. Sessões com duração > 2h30 (9000s) são tratadas como esquecimento de
   finalizar o treino: a duração É DESCARTADA do critério de tempo, mas
   o dia continua contando normalmente no critério de dias treinados --
   o treino em si aconteceu, só o cronômetro ficou rodando sem querer.
6. Registros com data no futuro são ignorados (o campo de data é
   preenchido manualmente pelo usuário no formulário de registro).
7. Só entram usuários com tipo_usuario == 'aluno', ativo == True e
   aparecer_no_ranking == True (opt-out configurável em Meu Perfil).
"""

from datetime import datetime, timezone, timedelta
from models import db, User, RegistroTreino, HistoricoTreino
from sqlalchemy import func
from .base_service import BaseService, CacheService
import logging

logger = logging.getLogger(__name__)

# Janela do ranking. Fixo em 30 dias por ora -- se um dia isso precisar
# virar parâmetro (ex: "últimos 7 dias"), a query já está isolada aqui.
JANELA_DIAS = 30

# Sessão mais longa que isso é tratada como esquecimento de finalizar o
# treino (cronômetro ficou rodando) -- ver regra 5 no docstring do módulo.
DURACAO_MAXIMA_VALIDA_SEGUNDOS = 2 * 3600 + 30 * 60  # 2h30

# Top N exibido no ranking.
TOP_N = 5

RANKING_CACHE_TTL_SEGUNDOS = 300  # 5 min -- é uma agregação cross-user,
# mais cara que as estatísticas individuais; um atraso de alguns minutos
# pra refletir um treino nov é aceitável aqui.


class RankingService:
    """Calcula o ranking geral de alunos por constância de treino."""

    @staticmethod
    def _janela_datas():
        hoje = datetime.now(timezone.utc).date()
        inicio = hoje - timedelta(days=JANELA_DIAS - 1)
        # Limite superior EXCLUSIVO (amanhã à meia-noite): data_registro é
        # DateTime, não Date -- comparar direto com "<= hoje" cortaria
        # registros de hoje que tenham qualquer horário depois da meia-
        # noite (a maioria, na prática), então filtra tudo abaixo de
        # amanhã em vez de "até hoje" literal.
        fim_exclusivo = hoje + timedelta(days=1)
        return inicio, hoje, fim_exclusivo

    @staticmethod
    def calcular_ranking_geral():
        """
        Retorna a lista completa de alunos elegíveis, já ordenada pelos
        critérios de desempate (dias treinados desc, tempo válido desc,
        nome asc). O chamador decide quantos exibir (top 5, "sua posição"
        etc.) -- calcular tudo de uma vez é mais simples e barato que
        paginar aqui, dado o volume esperado de usuários do app.

        Cada item: {
            'user_id', 'nome', 'dias_treinados', 'tempo_total_segundos',
            'tempo_total_formatado'
        }
        """
        cache_key = "ranking:geral:30d"
        cache_hit = CacheService.get(cache_key)
        if cache_hit is not None:
            return cache_hit

        try:
            inicio, hoje, fim_exclusivo = RankingService._janela_datas()

            alunos_elegiveis = User.query.filter(
                User.tipo_usuario == 'aluno',
                User.ativo == True,  # noqa: E712
                User.aparecer_no_ranking == True,  # noqa: E712
            ).all()

            if not alunos_elegiveis:
                CacheService.set(cache_key, [], ttl_seconds=RANKING_CACHE_TTL_SEGUNDOS)
                return []

            ids_elegiveis = [u.id for u in alunos_elegiveis]
            nomes_por_id = {
                u.id: (u.nome_completo or u.username) for u in alunos_elegiveis
            }

            # Uma linha por (usuário, dia, maior tempo_treino do dia).
            # func.max(HistoricoTreino.tempo_treino) já implementa a regra
            # 3 (maior sessão do dia, não soma) -- e como tempo_treino é
            # gravado igual em todas as séries de uma mesma sessão, pegar
            # o máximo por dia equivale a pegar o valor de qualquer sessão
            # daquele dia, só que sem precisar identificar sessões
            # explicitamente aqui.
            linhas = db.session.query(
                RegistroTreino.user_id,
                func.date(RegistroTreino.data_registro).label('dia'),
                func.max(HistoricoTreino.tempo_treino).label('tempo_do_dia'),
            ).outerjoin(
                HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id
            ).filter(
                RegistroTreino.user_id.in_(ids_elegiveis),
                RegistroTreino.data_registro >= inicio,
                RegistroTreino.data_registro < fim_exclusivo,  # regra 6: nunca no futuro (exclui só o que é de amanhã em diante)
            ).group_by(
                RegistroTreino.user_id, func.date(RegistroTreino.data_registro)
            ).all()

            agregados = {}
            for user_id, _dia, tempo_do_dia in linhas:
                agregado = agregados.setdefault(user_id, {'dias_treinados': 0, 'tempo_total_segundos': 0})
                agregado['dias_treinados'] += 1
                # Regra 5: duração > 2h30 descartada do tempo, mas o dia
                # (incrementado acima) continua contando.
                if tempo_do_dia and tempo_do_dia <= DURACAO_MAXIMA_VALIDA_SEGUNDOS:
                    agregado['tempo_total_segundos'] += tempo_do_dia

            ranking = []
            for user_id, agregado in agregados.items():
                if agregado['dias_treinados'] == 0:
                    continue
                tempo_total = agregado['tempo_total_segundos']
                ranking.append({
                    'user_id': user_id,
                    'nome': nomes_por_id.get(user_id, '—'),
                    'dias_treinados': agregado['dias_treinados'],
                    'tempo_total_segundos': tempo_total,
                    'tempo_total_formatado': RankingService._formatar_duracao(tempo_total),
                })

            ranking.sort(key=lambda r: (-r['dias_treinados'], -r['tempo_total_segundos'], r['nome'].lower()))

            for posicao, item in enumerate(ranking, start=1):
                item['posicao'] = posicao

            CacheService.set(cache_key, ranking, ttl_seconds=RANKING_CACHE_TTL_SEGUNDOS)
            return ranking
        except Exception:
            logger.exception("Erro ao calcular ranking geral de alunos")
            return []

    @staticmethod
    def top_n(n=TOP_N):
        return RankingService.calcular_ranking_geral()[:n]

    @staticmethod
    def posicao_do_usuario(user_id):
        """Retorna o item do ranking do usuário (com sua posição), ou
        None se ele não tem nenhum registro elegível no período (não
        apareceria no ranking de forma alguma) -- diferente de "existe
        mas está fora do top N", que é tratado pelo chamador comparando
        posicao > TOP_N."""
        for item in RankingService.calcular_ranking_geral():
            if item['user_id'] == user_id:
                return item
        return None

    @staticmethod
    def _formatar_duracao(segundos):
        segundos = segundos or 0
        horas = segundos // 3600
        minutos = (segundos % 3600) // 60
        if horas:
            return f"{horas}h{minutos:02d}min"
        return f"{minutos}min"
