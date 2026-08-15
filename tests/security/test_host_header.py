"""Testes de segurança contra Host Header Injection.

CORREÇÃO seção 12 (prompt de hardening): o link de reset de senha
enviado por e-mail não pode depender do header Host da requisição --
um atacante poderia forjar esse header pra fazer o link apontar pro
domínio dele e capturar o token de reset de outra pessoa.
"""
from models import db, User


def _cria_usuario(db, username='hostuser'):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaOriginal123')
    db.session.add(user)
    db.session.commit()
    return user


def test_link_de_reset_ignora_host_header_forjado_quando_app_base_url_configurada(
    client, db, app, monkeypatch,
):
    user = _cria_usuario(db)
    monkeypatch.setitem(app.config, 'APP_BASE_URL', 'https://fitlog.oficial.com')

    capturado = {}

    def _fake_enviar_email(destinatario, assunto, corpo_texto, corpo_html=None):
        capturado['corpo_texto'] = corpo_texto
        capturado['corpo_html'] = corpo_html
        return True

    monkeypatch.setattr('routes.auth_routes.enviar_email', _fake_enviar_email)

    resp = client.post(
        '/auth/reset-password-request',
        data={'email': user.email},
        headers={'Host': 'evil.example.com'},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # O link enviado deve usar o domínio oficial configurado, nunca o
    # Host forjado pela requisição.
    assert 'evil.example.com' not in capturado.get('corpo_texto', '')
    assert 'fitlog.oficial.com' in capturado.get('corpo_texto', '')
