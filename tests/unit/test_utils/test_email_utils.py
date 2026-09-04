"""Testes para utils/email_utils.py -- envio de e-mail via API HTTPS
do Resend (usado em recuperação de senha e nos alertas de falha de
provedor do FitBot, já mockado nesse outro contexto em
test_fitbot_fallback.py).
"""
import requests

from utils.email_utils import enviar_email


class _RespostaFake:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} erro")


class TestEnviarEmail:

    def test_sem_api_key_apenas_loga_e_retorna_false(self, app, caplog):
        app.config['RESEND_API_KEY'] = None
        import logging

        with caplog.at_level(logging.INFO):
            resultado = enviar_email('user@teste.com', 'Assunto', 'Corpo do e-mail')

        assert resultado is False
        assert any('NAO enviado de verdade' in r.message for r in caplog.records)

    def test_sucesso_retorna_true_e_monta_payload_correto(self, app, monkeypatch):
        app.config['RESEND_API_KEY'] = 'fake-key'
        app.config['MAIL_DEFAULT_SENDER'] = 'noreply@fitlog.com'
        capturado = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            capturado.update(url=url, headers=headers, json=json, timeout=timeout)
            return _RespostaFake(200)

        monkeypatch.setattr('requests.post', fake_post)

        resultado = enviar_email('user@teste.com', 'Bem-vindo', 'Texto simples')

        assert resultado is True
        assert capturado['url'] == 'https://api.resend.com/emails'
        assert capturado['headers']['Authorization'] == 'Bearer fake-key'
        assert capturado['json']['from'] == 'noreply@fitlog.com'
        assert capturado['json']['to'] == ['user@teste.com']
        assert capturado['json']['subject'] == 'Bem-vindo'
        assert capturado['json']['text'] == 'Texto simples'
        assert 'html' not in capturado['json']
        assert capturado['timeout'] == 10

    def test_com_corpo_html_inclui_no_payload(self, app, monkeypatch):
        app.config['RESEND_API_KEY'] = 'fake-key'
        capturado = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            capturado.update(json=json)
            return _RespostaFake(200)

        monkeypatch.setattr('requests.post', fake_post)

        enviar_email('user@teste.com', 'Assunto', 'Texto', corpo_html='<p>Texto</p>')

        assert capturado['json']['html'] == '<p>Texto</p>'

    def test_erro_http_retorna_false_sem_propagar(self, app, monkeypatch):
        app.config['RESEND_API_KEY'] = 'fake-key'
        monkeypatch.setattr('requests.post', lambda *a, **kw: _RespostaFake(422))

        resultado = enviar_email('user@teste.com', 'Assunto', 'Texto')

        assert resultado is False

    def test_falha_de_rede_retorna_false_sem_propagar(self, app, monkeypatch):
        app.config['RESEND_API_KEY'] = 'fake-key'

        def fake_post(*a, **kw):
            raise requests.exceptions.ConnectionError("sem rede")

        monkeypatch.setattr('requests.post', fake_post)

        resultado = enviar_email('user@teste.com', 'Assunto', 'Texto')

        assert resultado is False
