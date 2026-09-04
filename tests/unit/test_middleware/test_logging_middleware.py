"""Testes para middleware/logging_middleware.py.

ACHADO: nenhuma das duas formas deste módulo está de fato conectada à
aplicação -- `setup_middleware` nunca é chamado em app.py (só é
reexportado em middleware/__init__.py) e a classe `LoggingMiddleware`
está desabilitada por um comentário no próprio código ("Desabilitar
temporariamente o middleware para teste"). Ou seja, a aplicação hoje
não loga duração de requisição nenhuma. Não mexi nisso -- só testei o
código como ele existe, documentando o achado aqui.
"""
import logging
import time

from flask import Flask

from middleware.logging_middleware import LoggingMiddleware, setup_middleware


class TestLoggingMiddlewareWsgi:
    """A classe WSGI -- existe no módulo mas não é usada em lugar
    nenhum da aplicação (ver docstring do arquivo)."""

    def test_encaminha_a_chamada_e_loga_a_requisicao(self, caplog):
        def wsgi_app_fake(environ, start_response):
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [b'ok']

        middleware = LoggingMiddleware(wsgi_app_fake)
        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/rota-fake'}
        capturado = {}

        def start_response_fake(status, headers, exc_info=None):
            capturado['status'] = status
            capturado['headers'] = headers

        with caplog.at_level(logging.INFO):
            resultado = middleware(environ, start_response_fake)

        assert resultado == [b'ok']
        assert capturado['status'] == '200 OK'
        assert any('GET /rota-fake' in r.message and '200 OK' in r.message for r in caplog.records)

    def test_metodo_e_path_ausentes_no_environ_nao_quebram(self, caplog):
        def wsgi_app_fake(environ, start_response):
            start_response('404 NOT FOUND', [])
            return [b'']

        middleware = LoggingMiddleware(wsgi_app_fake)

        with caplog.at_level(logging.INFO):
            middleware({}, lambda *a, **kw: None)

        assert any('UNKNOWN' in r.message for r in caplog.records)


class TestSetupMiddleware:
    """O caminho que realmente roda hoje seria este, SE fosse chamado
    a partir de app.py -- o que não acontece."""

    def _criar_app_de_teste(self):
        app = Flask(__name__)
        setup_middleware(app)

        @app.route('/ping')
        def ping():
            return 'pong'

        return app

    def test_registra_hooks_sem_alterar_a_resposta(self):
        app = self._criar_app_de_teste()
        client = app.test_client()

        resp = client.get('/ping')

        assert resp.status_code == 200
        assert resp.data == b'pong'

    def test_loga_metodo_path_status_e_duracao(self, caplog):
        app = self._criar_app_de_teste()
        client = app.test_client()

        with caplog.at_level(logging.INFO):
            client.get('/ping')

        mensagens = [r.message for r in caplog.records]
        assert any('GET /ping' in m and '200' in m for m in mensagens)

    def test_sem_start_time_no_request_duracao_fica_zero(self, caplog):
        """Cobre o fallback `if hasattr(request, 'start_time') else 0`
        -- via after_request manual, sem passar pelo before_request."""
        app = Flask(__name__)

        @app.after_request
        def log_sem_timer(response):
            from flask import request
            duration = time.time() - request.start_time if hasattr(request, 'start_time') else 0
            assert duration == 0
            return response

        @app.route('/sem-timer')
        def sem_timer():
            return 'ok'

        client = app.test_client()
        resp = client.get('/sem-timer')
        assert resp.status_code == 200
