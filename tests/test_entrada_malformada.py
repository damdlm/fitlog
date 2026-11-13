"""Requisições malformadas não podem virar erro 500.

Achados da varredura de nov/2026: corpo JSON que é uma lista (ou vazio)
estourava AttributeError ('list' object has no attribute 'get') em várias
rotas, e editar aluno sem e-mail estourava IntegrityError (users.email NOT
NULL). Também: Google Fonts bloqueado pela CSP em todas as páginas.
"""
from pathlib import Path

import pytest

from models import db, User, AlunoProfessor

RAIZ = Path(__file__).resolve().parent.parent


def _user(username, tipo='aluno', admin=False):
    u = User(username=username, email=f'{username}@t.com', tipo_usuario=tipo,
             nome_completo=username.title(), is_admin=admin)
    u.set_password('Senha#Forte9')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    client.post('/auth/login', data={'username': username, 'password': 'Senha#Forte9'})


ROTAS_JSON = [
    '/api/criar-exercicio',
    '/api/reordenar-exercicios',
    '/contato/enviar',
    '/contato/publico/enviar',
    '/privacidade/fitbot-consentimento',
]

CORPOS = [
    {'json': [1, 2]},
    {'json': 'texto'},
    {'data': 'x{', 'content_type': 'application/json'},
    {},
]


@pytest.mark.parametrize('rota', ROTAS_JSON)
@pytest.mark.parametrize('corpo', CORPOS, ids=['lista', 'string', 'json-invalido', 'vazio'])
def test_corpo_json_malformado_nao_da_500(client, app, rota, corpo):
    with app.app_context():
        _user('malformado')
    _login(client, 'malformado')
    resp = client.post(rota, **corpo)
    assert resp.status_code < 500, (rota, corpo, resp.status_code)


def test_reordenar_exercicios_do_aluno_com_lista_nao_da_500(client, app):
    with app.app_context():
        adm = _user('admreord', admin=True)
        alu = _user('alureord')
        db.session.add(AlunoProfessor(aluno_id=alu.id, professor_id=adm.id))
        db.session.commit()
        aluno_id = alu.id
    _login(client, 'admreord')
    resp = client.post(f'/professor/aluno/{aluno_id}/reordenar-exercicios', json=[1])
    assert resp.status_code < 500


def test_corpo_json_objeto_helper(app):
    from utils.validators import corpo_json_objeto
    with app.test_request_context(json=[1]):
        assert corpo_json_objeto() == {}
    with app.test_request_context(data='x{', content_type='application/json'):
        assert corpo_json_objeto() == {}
    with app.test_request_context(json={'a': 1}):
        assert corpo_json_objeto() == {'a': 1}


class TestEditarAlunoEmail:

    def _setup(self, client, app):
        with app.app_context():
            _user('admedit', admin=True)
            alu = _user('aluedit')
            aluno_id = alu.id
        _login(client, 'admedit')
        return aluno_id

    @pytest.mark.parametrize('email', [None, '', '   '])
    def test_email_vazio_nao_da_500_e_nao_salva(self, client, app, email):
        aluno_id = self._setup(client, app)
        dados = {'nome_completo': 'Novo Nome'}
        if email is not None:
            dados['email'] = email
        resp = client.post(f'/professor/aluno/editar/{aluno_id}', data=dados)
        assert resp.status_code == 302
        assert f'/professor/aluno/editar/{aluno_id}' in resp.headers['Location']
        with app.app_context():
            aluno = db.session.get(User, aluno_id)
            assert aluno.email == 'aluedit@t.com'
            assert aluno.nome_completo == 'Aluedit'

    def test_email_com_espacos_e_salvo_sem_espacos(self, client, app):
        aluno_id = self._setup(client, app)
        resp = client.post(f'/professor/aluno/editar/{aluno_id}',
                           data={'nome_completo': 'Aluno', 'email': '  novo@t.com  '})
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(User, aluno_id).email == 'novo@t.com'


def test_base_html_nao_carrega_google_fonts_bloqueado_pela_csp():
    html = (RAIZ / 'templates/base.html').read_text(encoding='utf-8')
    assert 'fonts.googleapis.com' not in html
