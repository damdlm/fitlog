"""Agrega o uso técnico das IAs do FitBot (Groq/Gemini/reserva OpenAI)
a partir de FitBotChamada -- ver models.py -- para o card "FitBot (uso
de IA)" do painel de monitoramento do admin.

O registro de cada chamada (FitBotUsoService.registrar) é feito direto
em services/fitbot_service.py, logo após cada chamada HTTP a um
provedor. É sempre best-effort: uma falha ao gravar aqui nunca pode
quebrar a resposta do FitBot para o usuário.
"""

import logging
from datetime import datetime, timedelta, timezone

from models import db, FitBotChamada

logger = logging.getLogger(__name__)


class FitBotUsoService:

    @staticmethod
    def registrar(provedor, sucesso, duracao_ms, tokens_entrada=None, tokens_saida=None, motivo_falha=None):
        """Grava uma chamada a um provedor de IA. Best-effort: nunca
        propaga exceção -- se o INSERT falhar (ex: banco momentaneamente
        indisponível), só loga e segue, sem afetar a resposta do FitBot."""
        try:
            chamada = FitBotChamada(
                provedor=provedor,
                sucesso=bool(sucesso),
                duracao_ms=int(duracao_ms),
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
                motivo_falha=(motivo_falha or "")[:120] or None,
            )
            db.session.add(chamada)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("FitBotUso: falha ao registrar chamada (provedor=%s)", provedor)

    @staticmethod
    def get_metricas(horas=24):
        """Resumo por provedor nas últimas `horas`: total de chamadas,
        taxa de sucesso, duração média e tokens consumidos -- usado
        pelo painel de monitoramento e pelo histórico."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(hours=horas)
            linhas = (
                FitBotChamada.query
                .filter(FitBotChamada.criado_em >= desde)
                .all()
            )

            por_provedor = {}
            for c in linhas:
                agregado = por_provedor.setdefault(c.provedor, {
                    "chamadas": 0, "sucessos": 0, "soma_duracao_ms": 0,
                    "tokens_entrada": 0, "tokens_saida": 0,
                })
                agregado["chamadas"] += 1
                agregado["sucessos"] += 1 if c.sucesso else 0
                agregado["soma_duracao_ms"] += c.duracao_ms or 0
                agregado["tokens_entrada"] += c.tokens_entrada or 0
                agregado["tokens_saida"] += c.tokens_saida or 0

            provedores = []
            for provedor, agregado in por_provedor.items():
                chamadas = agregado["chamadas"]
                provedores.append({
                    "provedor": provedor,
                    "chamadas": chamadas,
                    "sucessos": agregado["sucessos"],
                    "falhas": chamadas - agregado["sucessos"],
                    "taxa_sucesso_pct": round(100 * agregado["sucessos"] / chamadas, 1) if chamadas else None,
                    "duracao_media_ms": round(agregado["soma_duracao_ms"] / chamadas) if chamadas else None,
                    "tokens_entrada": agregado["tokens_entrada"],
                    "tokens_saida": agregado["tokens_saida"],
                })
            provedores.sort(key=lambda p: p["chamadas"], reverse=True)

            return {
                "disponivel": True,
                "janela_horas": horas,
                "total_chamadas": len(linhas),
                "provedores": provedores,
            }
        except Exception:
            logger.exception("FitBotUso: falha ao agregar métricas")
            return {"disponivel": False, "erro": "falha ao consultar uso do FitBot"}
