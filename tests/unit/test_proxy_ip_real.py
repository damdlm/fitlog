"""P1-02: IP real do cliente atrás do proxy (TRUSTED_PROXY_COUNT)."""
from flask import request

from app import create_app
from tests.conftest import TestConfig


def _app_com_ip_route(monkeypatch, proxies):
    if proxies is None:
        monkeypatch.delenv('TRUSTED_PROXY_COUNT', raising=False)
    else:
        monkeypatch.setenv('TRUSTED_PROXY_COUNT', proxies)
    app = create_app(TestConfig)
    app.add_url_rule('/__ip_teste', 'ip_teste', lambda: request.remote_addr)
    return app


XFF = {'X-Forwarded-For': '203.0.113.9'}
PEER = {'REMOTE_ADDR': '100.64.0.7'}


def test_sem_a_variavel_o_comportamento_atual_e_mantido(monkeypatch):
    app = _app_com_ip_route(monkeypatch, None)
    assert app.test_client().get('/__ip_teste', headers=XFF, environ_base=PEER).get_data(as_text=True) == '100.64.0.7'


def test_com_um_proxy_confiavel_usa_o_ip_do_cliente(monkeypatch):
    app = _app_com_ip_route(monkeypatch, '1')
    assert app.test_client().get('/__ip_teste', headers=XFF, environ_base=PEER).get_data(as_text=True) == '203.0.113.9'


def test_valor_invalido_na_variavel_nao_derruba_o_app(monkeypatch):
    app = _app_com_ip_route(monkeypatch, 'abc')
    assert app.test_client().get('/__ip_teste', environ_base=PEER).get_data(as_text=True) == '100.64.0.7'


def test_xff_forjado_nao_e_confiado_sem_a_variavel(monkeypatch):
    app = _app_com_ip_route(monkeypatch, '0')
    forjado = {'X-Forwarded-For': '1.2.3.4, 5.6.7.8'}
    assert app.test_client().get('/__ip_teste', headers=forjado, environ_base=PEER).get_data(as_text=True) == '100.64.0.7'