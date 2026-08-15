"""Testes de segurança contra Open Redirect.

CORREÇÃO seção 11 (prompt de hardening): _safe_next_url() precisa
rejeitar URLs externas, incluindo bypasses com contra-barra (`\\`),
que navegadores normalizam para `/`.
"""
from models import db, User


def _cria_usuario(db, username='redirectuser'):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaOriginal123')
    db.session.add(user)
    db.session.commit()
    return user


def _login_com_next(client, username, next_url):
    return client.post(f'/auth/login?next={next_url}', data={
        'username': username, 'password': 'SenhaOriginal123',
    }, follow_redirects=False)


def test_next_relativo_valido_e_aceito(client, db):
    _cria_usuario(db)
    resp = _login_com_next(client, 'redirectuser', '/aluno/treinos')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/aluno/treinos')


def test_next_url_absoluta_externa_e_bloqueada(client, db):
    _cria_usuario(db, 'redirectuser2')
    resp = _login_com_next(client, 'redirectuser2', 'https://evil.example.com')
    assert resp.status_code == 302
    assert 'evil.example.com' not in resp.headers['Location']


def test_next_protocol_relative_e_bloqueado(client, db):
    _cria_usuario(db, 'redirectuser3')
    resp = _login_com_next(client, 'redirectuser3', '//evil.example.com')
    assert resp.status_code == 302
    assert 'evil.example.com' not in resp.headers['Location']


def test_next_com_contrabarra_e_bloqueado(client, db):
    """Bypass conhecido: '/\\evil.example.com' passa em
    startswith('/') e not startswith('//'), mas o navegador normaliza
    a contra-barra para '/', virando um redirect protocol-relative."""
    _cria_usuario(db, 'redirectuser4')
    resp = _login_com_next(client, 'redirectuser4', '/%5Cevil.example.com')
    assert resp.status_code == 302
    assert 'evil.example.com' not in resp.headers['Location']


def test_next_ausente_cai_para_home(client, db):
    _cria_usuario(db, 'redirectuser5')
    resp = client.post('/auth/login', data={
        'username': 'redirectuser5', 'password': 'SenhaOriginal123',
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert 'evil' not in resp.headers['Location']
