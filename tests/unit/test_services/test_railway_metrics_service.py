"""Testes para RailwayMetricsService -- métricas de CPU/memória via API
GraphQL do Railway (ver services/railway_metrics_service.py)."""
from services.railway_metrics_service import RailwayMetricsService


class _RespostaFake:
    def __init__(self, status_code=200, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._corpo


class TestGetMetrics:

    def test_sem_token_fica_indisponivel(self, monkeypatch):
        monkeypatch.delenv('RAILWAY_API_TOKEN', raising=False)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['disponivel'] is False
        assert 'RAILWAY_API_TOKEN' in resultado['erro']

    def test_com_token_mas_sem_service_id_fica_indisponivel(self, monkeypatch):
        monkeypatch.setenv('RAILWAY_API_TOKEN', 'token-fake')
        monkeypatch.delenv('RAILWAY_SERVICE_ID', raising=False)
        monkeypatch.delenv('RAILWAY_SERVICOS_EXTRAS', raising=False)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['disponivel'] is False

    def test_com_token_e_service_id_retorna_metricas_do_proprio_servico(self, monkeypatch):
        monkeypatch.setenv('RAILWAY_API_TOKEN', 'token-fake')
        monkeypatch.setenv('RAILWAY_SERVICE_ID', 'srv-123')
        monkeypatch.setenv('RAILWAY_SERVICE_NAME', 'fitlog')
        monkeypatch.delenv('RAILWAY_SERVICOS_EXTRAS', raising=False)

        corpo = {
            "data": {
                "metrics": [
                    {"measurement": "CPU_USAGE", "values": [{"ts": 1, "value": 0.05}, {"ts": 2, "value": 0.12}]},
                    {"measurement": "MEMORY_USAGE_GB", "values": [{"ts": 1, "value": 0.2}, {"ts": 2, "value": 0.22}]},
                ]
            }
        }

        def post_fake(url, headers=None, json=None, timeout=None):
            assert headers["Authorization"] == "Bearer token-fake"
            assert json["variables"]["serviceId"] == "srv-123"
            return _RespostaFake(200, corpo)

        monkeypatch.setattr('services.railway_metrics_service.requests.post', post_fake)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['disponivel'] is True
        assert len(resultado['servicos']) == 1
        servico = resultado['servicos'][0]
        assert servico['nome'] == 'fitlog'
        assert servico['disponivel'] is True
        assert servico['cpu_vcpu'] == 0.12  # último valor da série
        assert servico['memoria_gb'] == 0.22

    def test_inclui_servicos_extras_configurados(self, monkeypatch):
        monkeypatch.setenv('RAILWAY_API_TOKEN', 'token-fake')
        monkeypatch.setenv('RAILWAY_SERVICE_ID', 'srv-web')
        monkeypatch.setenv('RAILWAY_SERVICE_NAME', 'fitlog')
        monkeypatch.setenv('RAILWAY_SERVICOS_EXTRAS', 'Postgres:srv-pg, Redis:srv-redis')

        corpo_vazio = {"data": {"metrics": []}}
        chamadas = []

        def post_fake(url, headers=None, json=None, timeout=None):
            chamadas.append(json["variables"]["serviceId"])
            return _RespostaFake(200, corpo_vazio)

        monkeypatch.setattr('services.railway_metrics_service.requests.post', post_fake)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['disponivel'] is True
        nomes = {s['nome'] for s in resultado['servicos']}
        assert nomes == {'fitlog', 'Postgres', 'Redis'}
        assert set(chamadas) == {'srv-web', 'srv-pg', 'srv-redis'}

    def test_falha_em_um_servico_nao_afeta_os_demais(self, monkeypatch):
        monkeypatch.setenv('RAILWAY_API_TOKEN', 'token-fake')
        monkeypatch.setenv('RAILWAY_SERVICE_ID', 'srv-web')
        monkeypatch.setenv('RAILWAY_SERVICE_NAME', 'fitlog')
        monkeypatch.setenv('RAILWAY_SERVICOS_EXTRAS', 'Postgres:srv-pg')

        def post_fake(url, headers=None, json=None, timeout=None):
            if json["variables"]["serviceId"] == "srv-pg":
                raise ConnectionError("timeout")
            return _RespostaFake(200, {"data": {"metrics": []}})

        monkeypatch.setattr('services.railway_metrics_service.requests.post', post_fake)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['disponivel'] is True
        por_nome = {s['nome']: s for s in resultado['servicos']}
        assert por_nome['fitlog']['disponivel'] is True
        assert por_nome['Postgres']['disponivel'] is False
        assert 'erro' in por_nome['Postgres']

    def test_erro_graphql_marca_servico_como_indisponivel(self, monkeypatch):
        monkeypatch.setenv('RAILWAY_API_TOKEN', 'token-fake')
        monkeypatch.setenv('RAILWAY_SERVICE_ID', 'srv-web')
        monkeypatch.delenv('RAILWAY_SERVICOS_EXTRAS', raising=False)

        corpo_com_erro = {"errors": [{"message": "not authorized"}]}

        def post_fake(url, headers=None, json=None, timeout=None):
            return _RespostaFake(200, corpo_com_erro)

        monkeypatch.setattr('services.railway_metrics_service.requests.post', post_fake)

        resultado = RailwayMetricsService.get_metrics()

        assert resultado['servicos'][0]['disponivel'] is False
