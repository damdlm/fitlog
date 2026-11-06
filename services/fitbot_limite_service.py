"""Limites de uso e números do FitBot (tela Admin > FitBot).

- Cota diária por usuário e teto mensal do app inteiro, editáveis pelo
  admin (models.py:ConfiguracaoApp.fitbot_limite_*). Admin não tem limite.
- Conta mensagens respondidas com sucesso (models.py:FitBotMensagem) --
  falha do provedor de IA não gasta a cota de ninguém.
- "Hoje" e "este mês" seguem o horário de Brasília, que é como o usuário
  enxerga o dia.
- Custo estimado: tokens já registrados por chamada (FitBotChamada)
  multiplicados pelo preço de cada provedor.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from models import db, FitBotChamada, FitBotMensagem, User
from .base_service import CacheService
from .configuracao_service import ConfiguracaoService

logger = logging.getLogger(__name__)

FUSO = ZoneInfo('America/Sao_Paulo')
_CACHE_KEY_LIMITES = 'configuracao_app:fitbot_limites'
_CACHE_TTL_SEGUNDOS = 300

# Preço em US$ por milhão de tokens (entrada, saída), por provedor -- só
# para a estimativa da tela do admin. Os valores padrão são os de 11/2026
# para os modelos configurados (Groq gpt-oss-120b, Gemini flash-lite,
# OpenAI gpt-4o-mini); confira na tabela de cada provedor e, se mudarem,
# ajuste pela variável de ambiente FITBOT_PRECOS_JSON, ex.:
#   {"groq": [0.15, 0.60], "gemini": [0.10, 0.40], "openai_reserva": [0.15, 0.60]}
PRECOS_PADRAO_USD_POR_MILHAO = {
    'groq': (0.15, 0.60),
    'gemini': (0.10, 0.40),
    'openai_reserva': (0.15, 0.60),
}

LIMITE_MAXIMO_CONFIGURAVEL = 1_000_000


def _precos():
    precos = dict(PRECOS_PADRAO_USD_POR_MILHAO)
    bruto = os.getenv('FITBOT_PRECOS_JSON', '').strip()
    if bruto:
        try:
            for provedor, valores in json.loads(bruto).items():
                entrada, saida = float(valores[0]), float(valores[1])
                precos[str(provedor)] = (entrada, saida)
        except (ValueError, TypeError, IndexError, AttributeError):
            logger.warning('FITBOT_PRECOS_JSON inválida; usando os preços padrão.')
    return precos


def _inicio_do_dia_utc(agora=None):
    agora = (agora or datetime.now(timezone.utc)).astimezone(FUSO)
    return agora.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _inicio_do_mes_utc(agora=None):
    agora = (agora or datetime.now(timezone.utc)).astimezone(FUSO)
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _normalizar_limite(valor):
    """'' / None / 0 = sem limite. Número inteiro positivo = limite.
    Levanta ValueError para texto inválido ou negativo."""
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError('Use um número inteiro (ou deixe em branco para sem limite).')
    if numero < 0 or numero > LIMITE_MAXIMO_CONFIGURAVEL:
        raise ValueError(f'O limite precisa estar entre 0 e {LIMITE_MAXIMO_CONFIGURAVEL}.')
    return numero or None


class FitBotLimiteService:

    # ------------------------------------------------------------------
    # Limites (configuração)
    # ------------------------------------------------------------------
    @staticmethod
    def get_limites():
        """{'diario': int|None, 'mensal': int|None}. Lido a cada mensagem
        do FitBot, por isso cacheado (muda só quando o admin salva)."""
        cache = CacheService.get(_CACHE_KEY_LIMITES)
        if isinstance(cache, dict):
            return cache
        config = ConfiguracaoService._obter_ou_criar()
        limites = {
            'diario': config.fitbot_limite_diario_usuario,
            'mensal': config.fitbot_limite_mensal_total,
        }
        CacheService.set(_CACHE_KEY_LIMITES, limites, ttl_seconds=_CACHE_TTL_SEGUNDOS)
        return limites

    @staticmethod
    def set_limites(diario, mensal):
        """Salva os limites vindos do formulário do admin. Levanta
        ValueError com mensagem pronta para o usuário se algum for
        inválido (nada é salvo nesse caso)."""
        diario = _normalizar_limite(diario)
        mensal = _normalizar_limite(mensal)
        config = ConfiguracaoService._obter_ou_criar()
        config.fitbot_limite_diario_usuario = diario
        config.fitbot_limite_mensal_total = mensal
        db.session.commit()
        CacheService.invalidate(_CACHE_KEY_LIMITES)
        logger.info('Limites do FitBot alterados pelo admin: diario=%s mensal=%s', diario, mensal)
        return {'diario': diario, 'mensal': mensal}

    # ------------------------------------------------------------------
    # Cota (usada pela rota /fitbot/chat)
    # ------------------------------------------------------------------
    @staticmethod
    def contar_do_usuario_hoje(user_id):
        return (
            db.session.query(func.count(FitBotMensagem.id))
            .filter(FitBotMensagem.user_id == user_id, FitBotMensagem.criado_em >= _inicio_do_dia_utc())
            .scalar()
        ) or 0

    @staticmethod
    def contar_no_mes():
        return (
            db.session.query(func.count(FitBotMensagem.id))
            .filter(FitBotMensagem.criado_em >= _inicio_do_mes_utc())
            .scalar()
        ) or 0

    @staticmethod
    def verificar(usuario):
        """None se pode mandar mensagem; senão um dict com a mensagem para
        o usuário e o motivo ('diario' | 'mensal')."""
        if usuario.is_admin:
            return None
        limites = FitBotLimiteService.get_limites()

        mensal = limites.get('mensal')
        if mensal and FitBotLimiteService.contar_no_mes() >= mensal:
            return {
                'motivo': 'mensal',
                'resposta': (
                    'O FitBot atingiu o limite de uso deste mês e volta no dia 1º. '
                    'Enquanto isso, seus treinos e estatísticas continuam funcionando normalmente. 💪'
                ),
            }

        diario = limites.get('diario')
        if diario and FitBotLimiteService.contar_do_usuario_hoje(usuario.id) >= diario:
            return {
                'motivo': 'diario',
                'resposta': (
                    f'Você usou suas {diario} mensagens de hoje com o FitBot. '
                    'Amanhã tem mais! 💪'
                ),
            }
        return None

    @staticmethod
    def registrar(user_id, modo='texto'):
        """Grava uma mensagem respondida. Best-effort: nunca derruba a
        resposta que o usuário já recebeu."""
        try:
            db.session.add(FitBotMensagem(user_id=user_id, modo='imagem' if modo == 'imagem' else 'texto'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('FitBot: falha ao registrar mensagem do usuário %s', user_id)

    # ------------------------------------------------------------------
    # Números da tela Admin > FitBot
    # ------------------------------------------------------------------
    @staticmethod
    def _custo(desde):
        precos = _precos()
        linhas = (
            db.session.query(
                FitBotChamada.provedor,
                func.coalesce(func.sum(FitBotChamada.tokens_entrada), 0),
                func.coalesce(func.sum(FitBotChamada.tokens_saida), 0),
                func.count(FitBotChamada.id),
            )
            .filter(FitBotChamada.criado_em >= desde)
            .group_by(FitBotChamada.provedor)
            .all()
        )
        por_provedor = []
        total = 0.0
        for provedor, entrada, saida, chamadas in linhas:
            preco_ent, preco_sai = precos.get(provedor, (0.0, 0.0))
            custo = (int(entrada) * preco_ent + int(saida) * preco_sai) / 1_000_000
            total += custo
            por_provedor.append({
                'provedor': provedor,
                'chamadas': chamadas,
                'tokens_entrada': int(entrada),
                'tokens_saida': int(saida),
                'custo_usd': round(custo, 4),
            })
        por_provedor.sort(key=lambda p: p['custo_usd'], reverse=True)
        return round(total, 4), por_provedor

    @staticmethod
    def estatisticas(agora=None):
        agora = agora or datetime.now(timezone.utc)
        inicio_dia = _inicio_do_dia_utc(agora)
        inicio_mes = _inicio_do_mes_utc(agora)
        limites = FitBotLimiteService.get_limites()

        def contar(desde):
            return db.session.query(func.count(FitBotMensagem.id)).filter(FitBotMensagem.criado_em >= desde).scalar() or 0

        def usuarios(desde):
            return db.session.query(func.count(func.distinct(FitBotMensagem.user_id))).filter(
                FitBotMensagem.criado_em >= desde).scalar() or 0

        mensagens_mes = contar(inicio_mes)

        top = (
            db.session.query(User.id, User.nome_completo, User.username, func.count(FitBotMensagem.id).label('qtd'))
            .join(User, User.id == FitBotMensagem.user_id)
            .filter(FitBotMensagem.criado_em >= inicio_mes)
            .group_by(User.id, User.nome_completo, User.username)
            .order_by(func.count(FitBotMensagem.id).desc())
            .limit(10)
            .all()
        )

        no_limite_hoje = 0
        if limites.get('diario'):
            no_limite_hoje = (
                db.session.query(FitBotMensagem.user_id)
                .filter(FitBotMensagem.criado_em >= inicio_dia)
                .group_by(FitBotMensagem.user_id)
                .having(func.count(FitBotMensagem.id) >= limites['diario'])
                .count()
            )

        # Mensagens por dia nos últimos 30 dias (dia de Brasília). Agrupa
        # em Python para funcionar igual no Postgres e no SQLite dos testes.
        inicio_30 = _inicio_do_dia_utc(agora - timedelta(days=29))
        por_dia = {}
        for (criado_em,) in db.session.query(FitBotMensagem.criado_em).filter(FitBotMensagem.criado_em >= inicio_30):
            if criado_em.tzinfo is None:
                criado_em = criado_em.replace(tzinfo=timezone.utc)
            dia = criado_em.astimezone(FUSO).date()
            por_dia[dia] = por_dia.get(dia, 0) + 1
        hoje_local = agora.astimezone(FUSO).date()
        serie_30_dias = [
            {'dia': (hoje_local - timedelta(days=i)).isoformat(),
             'qtd': por_dia.get(hoje_local - timedelta(days=i), 0)}
            for i in range(29, -1, -1)
        ]

        custo_mes, custo_por_provedor = FitBotLimiteService._custo(inicio_mes)
        custo_hoje, _ = FitBotLimiteService._custo(inicio_dia)

        return {
            'limites': limites,
            'mensagens_hoje': contar(inicio_dia),
            'mensagens_mes': mensagens_mes,
            'usuarios_hoje': usuarios(inicio_dia),
            'usuarios_mes': usuarios(inicio_mes),
            'usuarios_no_limite_hoje': no_limite_hoje,
            'restante_mes': (max(limites['mensal'] - mensagens_mes, 0) if limites.get('mensal') else None),
            'top_usuarios_mes': [
                {'id': uid, 'nome': nome or username, 'qtd': qtd} for uid, nome, username, qtd in top
            ],
            'serie_30_dias': serie_30_dias,
            'custo_hoje_usd': custo_hoje,
            'custo_mes_usd': custo_mes,
            'custo_por_provedor_mes': custo_por_provedor,
            'precos_usd_por_milhao': {k: list(v) for k, v in _precos().items()},
        }
