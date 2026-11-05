"""
POST /aluno/avaliar-professor (routes/aluno/main.py) -- aluno dá 1 a 5
estrelas ao professor vinculado. A rota NUNCA aceita um professor_id vindo
do formulário: avalia sempre o professor vinculado ao usuário logado.
"""

import pytest

from models import db, User, AlunoProfessor, AvaliacaoProfessor

URL = '/aluno/avaliar-professor'


def _user(username, tipo='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo)
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u.id


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123!'})


@pytest.fixture
def aluno_com_professor(app, client):
    aluno, prof = _user('aluno_r'), _user('prof_r', 'professor')
    db.session.add(AlunoProfessor(aluno_id=aluno, professor_id=prof, ativo=True))
    db.session.commit()
    _login(client, 'aluno_r')
    return aluno, prof


def _flash(client):
    with client.session_transaction() as sess:
        return list(sess.get('_flashes', []))


class TestAvaliarProfessorRota:

    def test_registra_a_nota_e_volta_para_a_tela_do_professor(self, client, aluno_com_professor):
        aluno, prof = aluno_com_professor

        resp = client.post(URL, data={'nota': '5'})

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/aluno/meu-professor')
        assert ('success', 'Avaliação registrada -- obrigado pelo feedback!') in _flash(client)
        av = AvaliacaoProfessor.query.one()
        assert (av.aluno_id, av.professor_id, av.nota) == (aluno, prof, 5)

    def test_nova_avaliacao_atualiza_a_anterior(self, client, aluno_com_professor):
        client.post(URL, data={'nota': '2'})
        client.post(URL, data={'nota': '4'})

        assert [a.nota for a in AvaliacaoProfessor.query.all()] == [4]

    @pytest.mark.parametrize('nota', ['0', '6', 'abc', '', '4.5'])
    def test_nota_invalida_mostra_erro_e_nao_grava(self, client, aluno_com_professor, nota):
        client.post(URL, data={'nota': nota})

        assert any(cat == 'danger' for cat, _ in _flash(client))
        assert AvaliacaoProfessor.query.count() == 0

    def test_sem_campo_nota_nao_grava(self, client, aluno_com_professor):
        client.post(URL, data={})
        assert AvaliacaoProfessor.query.count() == 0

    def test_ignora_professor_id_enviado_no_formulario(self, client, aluno_com_professor):
        """IDOR: o aluno não escolhe quem avalia."""
        aluno, prof = aluno_com_professor
        estranho = _user('prof_estranho_r', 'professor')

        client.post(URL, data={'nota': '1', 'professor_id': str(estranho)})

        av = AvaliacaoProfessor.query.one()
        assert av.professor_id == prof and av.professor_id != estranho

    def test_aluno_sem_professor_recebe_aviso_e_volta_para_meu_professor(self, client, app):
        _user('aluno_solo')
        _login(client, 'aluno_solo')

        resp = client.post(URL, data={'nota': '5'})

        assert resp.headers['Location'].endswith('/aluno/meu-professor')
        assert ('warning', 'Você não está vinculado a nenhum professor.') in _flash(client)
        assert AvaliacaoProfessor.query.count() == 0

    def test_professor_nao_pode_avaliar(self, client, app):
        _user('prof_tentando', 'professor')
        _login(client, 'prof_tentando')

        resp = client.post(URL, data={'nota': '5'})

        assert resp.status_code == 302
        assert not resp.headers['Location'].endswith('/aluno/meu-professor')
        assert ('danger', 'Acesso negado.') in _flash(client)
        assert AvaliacaoProfessor.query.count() == 0

    def test_anonimo_vai_para_o_login(self, app):
        with app.app_context():
            resp = app.test_client().post(URL, data={'nota': '5'})
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers['Location']

    def test_get_nao_e_permitido(self, client, aluno_com_professor):
        assert client.get(URL).status_code == 405
