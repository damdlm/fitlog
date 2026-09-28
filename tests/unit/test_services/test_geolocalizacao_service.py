"""Testes de GeolocalizacaoService -- normalização de CEP e leitura da
BrasilAPI (mockada, sem rede). Segue o padrão de tests/unit/test_services/
e o fixture `app` de tests/conftest.py."""
import pytest

from services.geolocalizacao_service import GeolocalizacaoService


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("89251-000", "89251000"),
        (" 89251000 ", "89251000"),
        ("8925100", None),   # curto demais
        ("abc", None),
        ("", None),
        (None, None),
    ],
)
def test_normalizar_cep(entrada, esperado):
    assert GeolocalizacaoService.normalizar_cep(entrada) == esperado


class _RespostaFalsa:
    def __init__(self, status_code, corpo):
        self.status_code = status_code
        self._corpo = corpo

    def json(self):
        return self._corpo


class TestBrasilApi:

    def test_com_coordenadas(self, monkeypatch):
        corpo = {"location": {"coordinates": {"latitude": "-26.48", "longitude": "-49.07"}}}
        monkeypatch.setattr(
            "services.geolocalizacao_service.requests.get",
            lambda *a, **k: _RespostaFalsa(200, corpo),
        )

        coords, _ = GeolocalizacaoService._brasilapi("89251000")

        assert coords == (-26.48, -49.07)

    def test_sem_coordenadas_devolve_endereco_para_fallback(self, monkeypatch):
        corpo = {"street": "Rua X", "city": "Jaraguá do Sul", "state": "SC", "location": {}}
        monkeypatch.setattr(
            "services.geolocalizacao_service.requests.get",
            lambda *a, **k: _RespostaFalsa(200, corpo),
        )

        coords, endereco = GeolocalizacaoService._brasilapi("89251000")

        assert coords is None
        assert endereco["city"] == "Jaraguá do Sul"

    def test_cep_inexistente(self, monkeypatch):
        monkeypatch.setattr(
            "services.geolocalizacao_service.requests.get",
            lambda *a, **k: _RespostaFalsa(404, {}),
        )

        assert GeolocalizacaoService._brasilapi("00000000") == (None, None)


class TestGeocodificarCep:

    def test_usa_cache_em_chamadas_repetidas(self, app, monkeypatch):
        """A segunda chamada não deve bater na API -- vem do CacheService."""
        chamadas = {"total": 0}

        def get_falso(*a, **k):
            chamadas["total"] += 1
            corpo = {"location": {"coordinates": {"latitude": "-26.48", "longitude": "-49.07"}}}
            return _RespostaFalsa(200, corpo)

        monkeypatch.setattr("services.geolocalizacao_service.requests.get", get_falso)

        with app.app_context():
            primeira = GeolocalizacaoService.geocodificar_cep("89251-000")
            segunda = GeolocalizacaoService.geocodificar_cep("89251-000")

        assert primeira == (-26.48, -49.07)
        assert segunda == (-26.48, -49.07)
        assert chamadas["total"] == 1
