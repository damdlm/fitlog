"""Métricas de infraestrutura do Railway (CPU/memória por serviço),
para o card "Railway (infraestrutura)" do painel de monitoramento do
admin -- ver services/monitoring_service.py.

O Railway injeta automaticamente em todo serviço as variáveis
RAILWAY_PROJECT_ID, RAILWAY_ENVIRONMENT_ID, RAILWAY_SERVICE_ID e
RAILWAY_SERVICE_NAME (ver docs.railway.com/reference/variables) -- não
precisamos pedir isso ao admin, só a própria app já sabe quem ela é.

O que a app NÃO sabe sozinha é o ID dos serviços "vizinhos" (Postgres,
Redis, os crons de billing) -- para incluí-los no painel, o admin pode
opcionalmente configurar RAILWAY_SERVICOS_EXTRAS com pares
"nome:service_id" separados por vírgula (os IDs aparecem na URL de
cada serviço no dashboard do Railway). Sem isso, o card mostra métricas
só do próprio serviço web (o mais relevante no dia a dia).

Requer um RAILWAY_API_TOKEN (token de projeto ou de conta, criado em
railway.com/account/tokens) -- sem ele, o card fica marcado como
indisponível, igual ao padrão já usado para banco/cache/processo.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"
REQUEST_TIMEOUT_SECONDS = 8

# Mesmas medições usadas pelo dashboard do Railway -- CPU em fração de
# vCPU (1.0 = 1 vCPU cheia) e memória em GB.
_QUERY_METRICS = """
query Metrics(
  $serviceId: String
  $environmentId: String
  $startDate: DateTime!
  $measurements: [MetricMeasurement!]!
) {
  metrics(
    serviceId: $serviceId
    environmentId: $environmentId
    startDate: $startDate
    measurements: $measurements
  ) {
    measurement
    values { ts value }
  }
}
"""


class RailwayMetricsService:

    @staticmethod
    def _servicos_configurados():
        """Sempre inclui o próprio serviço (auto-detectado). Serviços
        extras vêm de RAILWAY_SERVICOS_EXTRAS="nome:id,nome2:id2"."""
        servicos = []

        service_id_proprio = os.getenv("RAILWAY_SERVICE_ID")
        if service_id_proprio:
            nome_proprio = os.getenv("RAILWAY_SERVICE_NAME", "fitlog")
            servicos.append((nome_proprio, service_id_proprio))

        extras = os.getenv("RAILWAY_SERVICOS_EXTRAS", "")
        for par in extras.split(","):
            par = par.strip()
            if not par or ":" not in par:
                continue
            nome, _, service_id = par.partition(":")
            nome, service_id = nome.strip(), service_id.strip()
            if nome and service_id and service_id not in {sid for _, sid in servicos}:
                servicos.append((nome, service_id))

        return servicos

    @staticmethod
    def _ultimo_valor(series, nome_medicao):
        for serie in series:
            if serie.get("measurement") == nome_medicao:
                valores = serie.get("values") or []
                if valores:
                    return valores[-1].get("value")
        return None

    # Token de conta/time vai em "Authorization: Bearer"; token de PROJETO
    # vai em "Project-Access-Token" (com Bearer a API responde
    # "Not Authorized"). Tenta os dois e lembra qual funcionou.
    _ESQUEMAS_AUTH = ("bearer", "projeto")
    _esquema_auth_ok = None

    @staticmethod
    def _headers(token, esquema):
        headers = {"Content-Type": "application/json"}
        if esquema == "projeto":
            headers["Project-Access-Token"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @classmethod
    def _metricas_de_um_servico(cls, token, environment_id, service_id, start_date_iso):
        esquemas = list(cls._ESQUEMAS_AUTH)
        if cls._esquema_auth_ok in esquemas:
            esquemas.remove(cls._esquema_auth_ok)
            esquemas.insert(0, cls._esquema_auth_ok)

        ultimo_erro = None
        for esquema in esquemas:
            try:
                metricas = cls._consultar_metricas(token, esquema, environment_id, service_id, start_date_iso)
            except RuntimeError as e:
                if "not authorized" not in str(e).lower():
                    raise
                ultimo_erro = e
                continue
            cls._esquema_auth_ok = esquema
            return metricas
        raise ultimo_erro

    @classmethod
    def _consultar_metricas(cls, token, esquema, environment_id, service_id, start_date_iso):
        resp = requests.post(
            RAILWAY_API_URL,
            headers=cls._headers(token, esquema),
            json={
                "query": _QUERY_METRICS,
                "variables": {
                    "serviceId": service_id,
                    "environmentId": environment_id,
                    "startDate": start_date_iso,
                    "measurements": ["CPU_USAGE", "MEMORY_USAGE_GB"],
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        corpo = resp.json()
        if corpo.get("errors"):
            raise RuntimeError(str(corpo["errors"])[:300])

        series = corpo.get("data", {}).get("metrics", [])
        return {
            "cpu_vcpu": cls._ultimo_valor(series, "CPU_USAGE"),
            "memoria_gb": cls._ultimo_valor(series, "MEMORY_USAGE_GB"),
        }

    @classmethod
    def get_metrics(cls):
        """Métricas atuais (últimos ~5min) de CPU/memória por serviço,
        direto da API do Railway. Isolado por serviço: se um serviço
        falhar (ex: ID inválido em RAILWAY_SERVICOS_EXTRAS), os demais
        continuam aparecendo -- mesmo padrão de tolerância a falha dos
        outros blocos do painel."""
        token = os.getenv("RAILWAY_API_TOKEN")
        if not token:
            return {
                "disponivel": False,
                "erro": "RAILWAY_API_TOKEN não configurada (ver services/railway_metrics_service.py)",
            }

        environment_id = os.getenv("RAILWAY_ENVIRONMENT_ID")
        servicos = cls._servicos_configurados()
        if not servicos:
            return {"disponivel": False, "erro": "nenhum serviço identificado (RAILWAY_SERVICE_ID ausente)"}

        start_date_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        resultado_servicos = []
        for nome, service_id in servicos:
            try:
                metricas = cls._metricas_de_um_servico(token, environment_id, service_id, start_date_iso)
                resultado_servicos.append({
                    "nome": nome,
                    "disponivel": True,
                    "cpu_vcpu": metricas["cpu_vcpu"],
                    "memoria_gb": metricas["memoria_gb"],
                })
            except Exception as e:
                logger.warning("Railway: falha ao coletar métricas do serviço %s: %s", nome, e)
                resultado_servicos.append({"nome": nome, "disponivel": False, "erro": str(e)[:200]})

        return {"disponivel": True, "servicos": resultado_servicos}