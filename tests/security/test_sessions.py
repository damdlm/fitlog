"""Testes de segurança de sessão.

CORREÇÃO 10 (prompt de hardening): troca de senha deve invalidar
sessões antigas (incluindo em outros dispositivos).

Observação técnica: estes testes usam fixtures próprias que NÃO mantêm
um app_context aberto durante as chamadas do client (diferente da
fixture `app` padrão do projeto em tests/conftest.py). Isso é
necessário porque, quando um app_context externo já está ativo, o
Flask reaproveita esse mesmo contexto (e o `flask.g` associado a ele)
para as requisições feitas pelo test client em vez de criar um novo a
cada chamada -- e o cache de current_user do Flask-Login vive em `g`.
Em produção isso não acontece (cada requisição HTTP real chega sem
nenhum app_context pré-existente), mas nos testes isso mascararia
justamente o comportamento que este arquivo verifica: que uma
requisição NOVA, após a troca de senha, tem que resolver o usuário de
novo e encontrar a sessão invalidada.
"""
import pytest

from app import create_app
from config import Config
from models import db as _db, User


class SessionsConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


@pytest.fixture
def sessions_app():
    app = create_app(SessionsConfig)
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def sessions_client(sessions_app):
    return sessions_app.test_client()


def _cria_usuario(app, username='sessuser'):
    with app.app_context():
        user = User(username=username, email=f'{username}@teste.com')
        user.set_password('SenhaOriginal123')
        _db.session.add(user)
        _db.session.commit()


def test_login_ok_estabelece_sessao_valida(sessions_app, sessions_client):
    _cria_usuario(sessions_app)
    resp = sessions_client.post('/auth/login', data={
        'username': 'sessuser', 'password': 'SenhaOriginal123',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert sessions_client.get('/auth/profile').status_code == 200


def test_troca_de_senha_invalida_a_propria_sessao_atual(sessions_app, sessions_client):
    """Login -> captura sessão -> troca senha -> a MESMA sessão que fez
    a troca também deve ficar inválida (a sessão em uso vira "antiga"
    assim que a senha muda)."""
    _cria_usuario(sessions_app)
    sessions_client.post('/auth/login', data={
        'username': 'sessuser', 'password': 'SenhaOriginal123',
    }, follow_redirects=True)
    assert sessions_client.get('/auth/profile').status_code == 200

    sessions_client.post('/auth/change-password', data={
        'current_password': 'SenhaOriginal123',
        'new_password': 'SenhaNovaForte123',
        'confirm_password': 'SenhaNovaForte123',
    }, follow_redirects=True)

    # A mesma sessão (cookie) não deve mais acessar rota autenticada --
    # o login_required deve redirecionar (302) por current_user não
    # estar mais autenticado.
    resp = sessions_client.get('/auth/profile', follow_redirects=False)
    assert resp.status_code == 302


def test_troca_de_senha_invalida_sessao_de_outro_dispositivo(sessions_app):
    """Login dispositivo A / login dispositivo B (dois clients) -> troca
    de senha via A -> ambas as sessões (A e B) ficam inválidas."""
    _cria_usuario(sessions_app, username='doisdispositivos')

    client_a = sessions_app.test_client()
    client_b = sessions_app.test_client()

    client_a.post('/auth/login', data={
        'username': 'doisdispositivos', 'password': 'SenhaOriginal123',
    }, follow_redirects=True)
    client_b.post('/auth/login', data={
        'username': 'doisdispositivos', 'password': 'SenhaOriginal123',
    }, follow_redirects=True)

    assert client_a.get('/auth/profile').status_code == 200
    assert client_b.get('/auth/profile').status_code == 200

    client_a.post('/auth/change-password', data={
        'current_password': 'SenhaOriginal123',
        'new_password': 'SenhaNovaForte123',
        'confirm_password': 'SenhaNovaForte123',
    }, follow_redirects=True)

    assert client_a.get('/auth/profile', follow_redirects=False).status_code == 302
    assert client_b.get('/auth/profile', follow_redirects=False).status_code == 302

    # A nova senha continua funcionando para um novo login
    resp_novo_login = client_b.post('/auth/login', data={
        'username': 'doisdispositivos', 'password': 'SenhaNovaForte123',
    }, follow_redirects=True)
    assert resp_novo_login.status_code == 200
    assert client_b.get('/auth/profile').status_code == 200
