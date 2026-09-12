"""Histórico das métricas do painel de monitoramento do admin --
guarda um snapshot periódico (via `flask monitoramento-capturar-snapshot`,
rodado pelo Railway Cron a cada ~10min) para dar tendência ao longo do
tempo e ajudar a identificar gargalos, além do instante atual que
MonitoringService já mostra.

Ver models.HistoricoMetricas para o porquê do formato JSON solto.
"""

import logging
from datetime import datetime, timedelta, timezone

from models import db, HistoricoMetricas

logger = logging.getLogger(__name__)

# Só o suficiente pra achar padrão de horário de pico -- não é uma
# série histórica de longo prazo (ver docstring de HistoricoMetricas).
RETENCAO_DIAS = 7


class HistoricoMetricasService:

    @staticmethod
    def _resumir(metricas_completas):
        """Reduz o retorno "cheio" de MonitoringService.get_all_metrics()
        (que inclui coisas como a lista por-worker, só úteis no instante
        atual) só aos números que interessam pra tendência histórica --
        mantém o snapshot pequeno."""
        processo = metricas_completas.get("processo") or {}
        banco = metricas_completas.get("banco") or {}
        cache = metricas_completas.get("cache") or {}
        railway = metricas_completas.get("railway") or {}
        fitbot = metricas_completas.get("fitbot") or {}

        resumo = {
            "cpu_processo_pct": processo.get("cpu_processo_pct"),
            "memoria_processo_mb": processo.get("memoria_processo_mb"),
            "memoria_sistema_usada_pct": processo.get("memoria_sistema_usada_pct"),
            "db_conexoes_ativas": banco.get("conexoes_ativas"),
            "db_cache_hit_ratio_pct": banco.get("cache_hit_ratio_pct"),
            "cache_memoria_usada_mb": cache.get("memoria_usada_mb"),
            "cache_hit_rate_pct": cache.get("hit_rate_pct"),
        }

        if railway.get("disponivel"):
            resumo["railway_servicos"] = [
                {"nome": s.get("nome"), "cpu_vcpu": s.get("cpu_vcpu"), "memoria_gb": s.get("memoria_gb")}
                for s in railway.get("servicos", []) if s.get("disponivel")
            ]

        if fitbot.get("disponivel"):
            resumo["fitbot_provedores"] = [
                {
                    "provedor": p.get("provedor"),
                    "chamadas": p.get("chamadas"),
                    "taxa_sucesso_pct": p.get("taxa_sucesso_pct"),
                    "duracao_media_ms": p.get("duracao_media_ms"),
                }
                for p in fitbot.get("provedores", [])
            ]

        return resumo

    @classmethod
    def capturar_snapshot(cls):
        """Coleta as métricas atuais e grava um snapshot resumido.
        Chamado pelo comando CLI `monitoramento-capturar-snapshot`."""
        from services.monitoring_service import MonitoringService

        try:
            metricas = MonitoringService.get_all_metrics()
            snapshot = HistoricoMetricas(dados=cls._resumir(metricas))
            db.session.add(snapshot)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            logger.exception("HistoricoMetricas: falha ao capturar snapshot")
            return False

    @staticmethod
    def obter_serie(horas=24):
        """Lista de snapshots (mais antigo primeiro) das últimas
        `horas`, para o painel montar os gráficos de tendência."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(hours=horas)
            linhas = (
                HistoricoMetricas.query
                .filter(HistoricoMetricas.coletado_em >= desde)
                .order_by(HistoricoMetricas.coletado_em.asc())
                .all()
            )
            return {
                "disponivel": True,
                "pontos": [
                    {"coletado_em": l.coletado_em.isoformat(), **(l.dados or {})}
                    for l in linhas
                ],
            }
        except Exception:
            logger.exception("HistoricoMetricas: falha ao consultar série histórica")
            return {"disponivel": False, "erro": "falha ao consultar histórico", "pontos": []}

    @staticmethod
    def limpar_antigas(dias_retencao=RETENCAO_DIAS):
        """Remove snapshots mais antigos que `dias_retencao` dias.
        Chamado ao final de capturar_snapshot -- barato o suficiente
        (DELETE indexado por coletado_em) pra rodar a cada execução."""
        try:
            limite = datetime.now(timezone.utc) - timedelta(days=dias_retencao)
            total = HistoricoMetricas.query.filter(HistoricoMetricas.coletado_em < limite).delete()
            db.session.commit()
            return total
        except Exception:
            db.session.rollback()
            logger.exception("HistoricoMetricas: falha ao limpar snapshots antigos")
            return None
