"""Testes de segurança de CSRF e de rotas GET mutáveis.

CORREÇÃO 4 (prompt de hardening): rotas que executam exclusão, clonagem
ou finalização não podem mais aceitar GET, e precisam de CSRF válido
(Flask-WTF só protege métodos não seguros, então GET mutável também
"escapava" da proteção de CSRF).

A fixture `app`/`client` padrão do projeto desliga WTF_CSRF_ENABLED para
simplificar os outros testes -- aqui usamos uma app própria com CSRF
LIGADO, exatamente como em produção.
"""
import pytest

from app import create_app
from config import Config
from models import db as _db, User, ExercicioUsuario


class CsrfOnConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True


@pytest.fixture
def csrf_app():
    app = create_app(CsrfOnConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _cria_usuario_logado(app, client, username='aluno_csrf'):
    with app.app_context():
        user = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
        user.set_password('Senha1234')
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id

    # login real, respeitando CSRF do próprio form de login
    login_page = client.get('/auth/login')
    import re
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', login_page.data)
    token = match.group(1).decode() if match else None
    client.post('/auth/login', data={
        'username': username,
        'password': 'Senha1234',
        'csrf_token': token,
    })
    return user_id


def _cria_exercicio(app, user_id):
    with app.app_context():
        ex = ExercicioUsuario(nome='Supino', usuario_id=user_id)
        _db.session.add(ex)
        _db.session.commit()
        return ex.id


def test_get_em_rota_de_exclusao_nao_e_mais_aceito(csrf_app, csrf_client):
    """A rota de excluir exercício não deve mais responder a GET (405)."""
    user_id = _cria_usuario_logado(csrf_app, csrf_client)
    ex_id = _cria_exercicio(csrf_app, user_id)

    resp = csrf_client.get(f'/aluno/exercicio/{ex_id}/excluir?confirmar=true')
    assert resp.status_code == 405


def test_post_sem_csrf_token_e_rejeitado(csrf_app, csrf_client):
    """POST para a rota de exclusão sem csrf_token deve ser rejeitado."""
    user_id = _cria_usuario_logado(csrf_app, csrf_client)
    ex_id = _cria_exercicio(csrf_app, user_id)

    resp = csrf_client.post(f'/aluno/exercicio/{ex_id}/excluir?confirmar=true')
    assert resp.status_code == 400

    with csrf_app.app_context():
        assert ExercicioUsuario.query.get(ex_id) is not None


def test_post_com_csrf_token_valido_e_aceito(csrf_app, csrf_client):
    """POST com csrf_token válido deve funcionar normalmente."""
    user_id = _cria_usuario_logado(csrf_app, csrf_client)
    ex_id = _cria_exercicio(csrf_app, user_id)

    pagina = csrf_client.get('/aluno/exercicios')
    import re
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', pagina.data)
    assert match, "página deveria conter algum form com csrf_token"
    token = match.group(1).decode()

    resp = csrf_client.post(
        f'/aluno/exercicio/{ex_id}/excluir?confirmar=true',
        data={'csrf_token': token},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with csrf_app.app_context():
        assert ExercicioUsuario.query.get(ex_id) is None
