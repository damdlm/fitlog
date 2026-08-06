"""
FitBotContextService — camada de contexto do FitBot.

Responsabilidade única: dado (mensagem do usuário, user_id), decidir quais
dados reais são necessários e montar um contexto estruturado (dict, pronto
para virar JSON) para o LLM. Nunca busca "tudo" -- só o que a intenção da
pergunta exige.

REGRA DE SEGURANÇA (não negociável):
O `user_id` usado em TODAS as consultas desta camada é sempre recebido
como parâmetro, já resolvido pelo backend a partir da sessão autenticada
(ver BaseService.get_current_user_id() / get_target_user_id() e a rota
/fitbot/chat). Este módulo nunca lê um user_id do texto da mensagem, do
histórico da conversa ou de qualquer outro dado vindo do front-end --
mesmo que a mensagem do usuário peça isso explicitamente ("me mostre os
dados do usuário 15"). O isolamento é garantido aqui pela query, não pelo
prompt.
"""

import logging
import unicodedata
from datetime import datetime, timedelta, timezone

from services.base_service import BaseService, CacheService
from services.versao_service import VersaoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
from services.exercicio_service import ExercicioService

logger = logging.getLogger(__name__)

# Intenções suportadas (classificação simples por palavra-chave --
# suficiente pro caso de uso; não há necessidade de um classificador
# mais complexo aqui).
TREINO_ATUAL = "TREINO_ATUAL"
HISTORICO = "HISTORICO"
EVOLUCAO = "EVOLUCAO"
ESTATISTICAS = "ESTATISTICAS"
PERFIL = "PERFIL"
DUVIDA_GERAL = "DUVIDA_GERAL"

MAX_EXERCICIOS_POR_TREINO_CONTEXTO = 15
MAX_SESSOES_HISTORICO = 10
CONTEXTO_CACHE_TTL_SEGUNDOS = 60


def _normalizar(texto):
    """minúsculas + remove acentos, pra comparar 'Supino Reto' com 'supino'."""
    texto = (texto or "").lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return texto


def _formatar_data(dt):
    """Só a data (sem hora) -- é o que importa pro usuário e economiza
    tokens no contexto enviado ao LLM (item 15 da spec)."""
    if not dt:
        return None
    if hasattr(dt, "date"):
        return dt.date().isoformat()
    return str(dt)


class FitBotContextService:
    """Monta o contexto estruturado enviado ao FitBot, por intenção."""

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------
    @staticmethod
    def montar_contexto(mensagem, user_id):
        """
        Monta o contexto (dict) para `mensagem`, restrito exclusivamente
        aos dados de `user_id`. Retorna None se não houver dados
        relevantes (o FitBot então responde só com conhecimento geral).

        `user_id` deve ser um valor já validado pelo backend -- nunca
        repasse aqui um id vindo diretamente do front-end sem checar
        permissão antes (ver BaseService.get_target_user_id).
        """
        if not user_id:
            return None

        intencao = FitBotContextService.identificar_intencao(mensagem)

        try:
            if intencao == TREINO_ATUAL:
                dados = FitBotContextService._contexto_treino_atual(user_id)
            elif intencao == HISTORICO:
                dados = FitBotContextService._contexto_historico(mensagem, user_id)
            elif intencao == EVOLUCAO:
                dados = FitBotContextService._contexto_evolucao(mensagem, user_id)
            elif intencao == ESTATISTICAS:
                dados = FitBotContextService._contexto_estatisticas(user_id)
            elif intencao == PERFIL:
                dados = FitBotContextService._contexto_perfil(user_id)
            else:
                dados = None
        except Exception as e:
            # Falha ao montar contexto nunca deve derrubar a conversa --
            # o FitBot simplesmente segue sem esses dados extras.
            logger.warning(
                "FitBot: falha ao montar contexto (%s) para user_id=%s: %s",
                intencao, user_id, e,
            )
            dados = None

        if not dados:
            return None

        return {"intencao": intencao, **dados}

    # ------------------------------------------------------------------
    # Classificação de intenção
    # ------------------------------------------------------------------
    @staticmethod
    def identificar_intencao(mensagem):
        texto = _normalizar(mensagem)

        if any(p in texto for p in (
            "evolu", "progred", "progressao", "progresso",
            "melhorei", "piorei", "aumentei", "diminui", "regredi",
        )):
            return EVOLUCAO

        if any(p in texto for p in (
            "quantas vezes", "frequencia", "quantos treinos",
            "qual musculo", "grupo muscular", "mais treinado",
            "estatistica", "resumo do mes", "resumo da semana",
        )):
            return ESTATISTICAS

        if any(p in texto for p in (
            "ultima vez", "ultimo treino", "historico",
            "quando foi", "semana passada", "fiz no", "fiz em",
            "fez no", "fez em", "registrei", "maior carga", "recorde",
            "quanto eu fiz", "quanto fiz", "quanto ele fez", "quanto ela fez",
            "quanto voce fez",
        )):
            return HISTORICO

        if any(p in texto for p in (
            "meu perfil", "meus dados", "meu peso", "minha altura", "meu objetivo",
        )):
            return PERFIL

        if any(p in texto for p in (
            "treino de hoje", "treino atual", "meu treino", "qual treino",
            "que treino e hoje", "o que treino hoje", "meus exercicios de hoje",
        )):
            return TREINO_ATUAL

        return DUVIDA_GERAL

    # ------------------------------------------------------------------
    # PERFIL
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto_perfil(user_id):
        from models import User

        usuario = User.query.get(user_id)
        if not usuario:
            return None
        return {"usuario": {"nome": usuario.nome_completo or usuario.username}}

    # ------------------------------------------------------------------
    # TREINO ATUAL
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto_treino_atual(user_id):
        from models import User

        usuario = User.query.get(user_id)
        if not usuario:
            return None

        versao_ativa = VersaoService.get_ativa(user_id=user_id)
        if not versao_ativa:
            return None

        treinos = VersaoService.get_treinos(versao_ativa.id, user_id=user_id)
        if not treinos:
            return None

        # Antes: 1 VersaoService.get_exercicios() por treino dentro do loop
        # (mesmo N+1 do professor/aluno — ver VersaoService.get_exercicios_
        # agrupados_por_treino). Toda mensagem do FitBot passa por aqui,
        # então isso rodava a cada mensagem enviada.
        exercicios_por_treino_id = VersaoService.get_exercicios_agrupados_por_treino(user_id=user_id)

        treinos_ctx = []
        for codigo, dados in treinos.items():
            exercicios = exercicios_por_treino_id.get(dados.get("id"), [])
            if not exercicios:
                continue
            exercicios_ctx = [
                {"nome": ex.nome, "musculo": getattr(ex, "musculo", None)}
                for ex in exercicios[:MAX_EXERCICIOS_POR_TREINO_CONTEXTO]
                if getattr(ex, "nome", None)
            ]
            if not exercicios_ctx:
                continue
            treinos_ctx.append({
                "codigo": codigo,
                "nome": dados.get("nome") or codigo,
                "exercicios": exercicios_ctx,
            })

        if not treinos_ctx:
            return None

        return {
            "usuario": {"nome": usuario.nome_completo or usuario.username},
            "versao_ativa": {
                "numero": versao_ativa.numero_versao,
                "divisao": versao_ativa.divisao,
                "data_inicio": versao_ativa.data_inicio.isoformat() if versao_ativa.data_inicio else None,
            },
            "treino_atual": treinos_ctx,
        }

    # ------------------------------------------------------------------
    # Localizar exercício citado na mensagem (entre os exercícios que
    # o próprio usuário já tem em algum treino/histórico -- nunca busca
    # no catálogo global inteiro pra isso).
    # ------------------------------------------------------------------
    @staticmethod
    def _encontrar_exercicio_pela_mensagem(mensagem, user_id):
        texto = _normalizar(mensagem)
        candidatos = ExercicioService.get_exercicios_dos_treinos(user_id=user_id)

        melhor, melhor_pontuacao = None, 0
        for ex in candidatos:
            nome_norm = _normalizar(ex.nome)
            palavras = [p for p in nome_norm.split() if len(p) > 2]
            if not palavras:
                continue
            pontuacao = sum(1 for p in palavras if p in texto)
            if pontuacao > melhor_pontuacao:
                melhor_pontuacao, melhor = pontuacao, ex

        return melhor if melhor_pontuacao > 0 else None

    # ------------------------------------------------------------------
    # HISTÓRICO
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto_historico(mensagem, user_id):
        exercicio = FitBotContextService._encontrar_exercicio_pela_mensagem(mensagem, user_id)
        if not exercicio:
            return None

        registros = RegistroService.get_por_exercicio(exercicio.id, limite=MAX_SESSOES_HISTORICO, user_id=user_id)
        if not registros:
            return {
                "exercicio": exercicio.nome,
                "sessoes": [],
                "observacao": "Nenhum registro encontrado para este exercício ainda.",
            }

        sessoes = []
        for r in registros:
            series = [{"carga": float(s.carga), "repeticoes": s.repeticoes} for s in r.series]
            if not series:
                continue
            sessoes.append({
                "data": _formatar_data(r.data_registro),
                "series": series,
            })

        return {"exercicio": exercicio.nome, "sessoes": sessoes}

    # ------------------------------------------------------------------
    # EVOLUÇÃO
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto_evolucao(mensagem, user_id):
        exercicio = FitBotContextService._encontrar_exercicio_pela_mensagem(mensagem, user_id)

        if exercicio:
            registros = RegistroService.get_por_exercicio(exercicio.id, limite=MAX_SESSOES_HISTORICO, user_id=user_id)
            if not registros:
                return {
                    "exercicio": exercicio.nome,
                    "observacao": "Ainda não há registros suficientes deste exercício para avaliar evolução.",
                }

            # get_por_exercicio vem do mais recente pro mais antigo;
            # inverte pra comparação cronológica (primeiro -> último).
            pontos = []
            for r in reversed(registros):
                cargas = [float(s.carga) for s in r.series]
                if not cargas:
                    continue
                pontos.append({
                    "data": _formatar_data(r.data_registro),
                    "carga_maxima": max(cargas),
                    "volume": sum(float(s.carga) * s.repeticoes for s in r.series),
                })

            if not pontos:
                return {
                    "exercicio": exercicio.nome,
                    "observacao": "Ainda não há registros suficientes deste exercício para avaliar evolução.",
                }

            return {
                "exercicio": exercicio.nome,
                "evolucao_por_sessao": pontos,
                "primeira_carga_maxima_registrada": pontos[0]["carga_maxima"],
                "ultima_carga_maxima_registrada": pontos[-1]["carga_maxima"],
            }

        # Sem exercício específico citado -> evolução geral de volume
        # (últimos 30 dias corridos), reaproveitando o mesmo cálculo já
        # usado na tela de estatísticas.
        progresso = EstatisticaService.get_progresso_ultimos_30_dias(user_id=user_id)
        if not progresso:
            return {"observacao": "Ainda não há registros suficientes nos últimos 30 dias para avaliar evolução."}

        dias = [
            {
                "data": str(p.dia),
                "volume_total": float(p.volume_total or 0),
                "carga_media": float(p.carga_media or 0),
            }
            for p in progresso
        ]
        return {"evolucao_volume_ultimos_30_dias": dias}

    # ------------------------------------------------------------------
    # ESTATÍSTICAS
    # ------------------------------------------------------------------
    @staticmethod
    def _contexto_estatisticas(user_id):
        cache_key = f"fitbot_context:{user_id}:estatisticas:30d"
        cache_hit = CacheService.get(cache_key)
        if cache_hit is not None:
            return cache_hit

        por_musculo = EstatisticaService.calcular_por_musculo(user_id=user_id)
        treinos_7_dias = FitBotContextService._dias_treinados_desde(user_id, dias=7)
        treinos_30_dias = FitBotContextService._dias_treinados_desde(user_id, dias=30)

        musculos_ctx = sorted(
            (
                {
                    "musculo": nome,
                    "qtd_registros": dados.get("qtd_registros", 0),
                    "volume_total": dados.get("volume_total", 0),
                }
                for nome, dados in por_musculo.items()
                if dados.get("qtd_registros", 0) > 0
            ),
            key=lambda m: m["volume_total"],
            reverse=True,
        )[:10]

        if not musculos_ctx and not treinos_7_dias and not treinos_30_dias:
            return None

        resultado = {
            "dias_treinados_ultimos_7_dias": treinos_7_dias,
            "dias_treinados_ultimos_30_dias": treinos_30_dias,
            "volume_por_musculo": musculos_ctx,
        }
        CacheService.set(cache_key, resultado, ttl_seconds=CONTEXTO_CACHE_TTL_SEGUNDOS)
        return resultado

    @staticmethod
    def _dias_treinados_desde(user_id, dias):
        """Quantos dias distintos, nos últimos `dias` dias corridos, o
        usuário tem ao menos um RegistroTreino -- usado pra responder
        perguntas de frequência ("quantas vezes treinei essa semana?")."""
        from models import db, RegistroTreino
        from sqlalchemy import func

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        total = (
            db.session.query(func.count(func.distinct(func.date(RegistroTreino.data_registro))))
            .filter(RegistroTreino.user_id == user_id, RegistroTreino.data_registro >= limite)
            .scalar()
        )
        return total or 0
