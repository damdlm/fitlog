"""
Testes para as permissões de professor sobre dados de aluno.

Cobre a correção do bug em que editar_aluno/desativar_aluno/reativar_aluno
bloqueavam qualquer usuário que não fosse admin -- inclusive o professor
vinculado ao próprio aluno -- e a nova rota de calendário por aluno.
"""
import pytest
from models import db, User, AlunoProfessor


def _criar_usuario(username, tipo_usuario, is_admin=False):
    user = User(
        username=username,
        email=f'{username}@teste.com',
        tipo_usuario=tipo_usuario,
        is_admin=is_admin,
        nome_completo=username.title(),
    )
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={
        'username': username,
        'password': '123456'
    })


@pytest.fixture
def professor_com_aluno(app):
    """Cria um professor, um aluno vinculado a ele, e um aluno de outro professor."""
    with app.app_context():
        professor = _criar_usuario('prof1', 'professor')
        aluno = _criar_usuario('aluno1', 'aluno')
        outro_professor = _criar_usuario('prof2', 'professor')
        aluno_de_outro = _criar_usuario('aluno2', 'aluno')

        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
        db.session.add(AlunoProfessor(aluno_id=aluno_de_outro.id, professor_id=outro_professor.id, ativo=True))
        db.session.commit()

        return {
            'professor_id': professor.id,
            'aluno_id': aluno.id,
            'aluno_de_outro_id': aluno_de_outro.id,
        }


class TestEditarAluno:
    def test_professor_nao_pode_editar_proprio_aluno(self, client, professor_com_aluno):
        """Editar é restrito ao admin -- mesmo o professor vinculado não pode."""
        _login(client, 'prof1')
        resp = client.post(
            f"/professor/aluno/editar/{professor_com_aluno['aluno_id']}",
            data={'nome_completo': 'Novo Nome', 'email': 'aluno1@teste.com', 'telefone': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.nome_completo != 'Novo Nome'

    def test_professor_nao_pode_editar_aluno_de_outro_professor(self, client, professor_com_aluno):
        _login(client, 'prof1')
        resp = client.post(
            f"/professor/aluno/editar/{professor_com_aluno['aluno_de_outro_id']}",
            data={'nome_completo': 'Hackeado', 'email': 'aluno2@teste.com', 'telefone': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_de_outro_id'])
            assert aluno.nome_completo != 'Hackeado'

    def test_admin_pode_editar_qualquer_aluno(self, client, professor_com_aluno):
        with client.application.app_context():
            admin = _criar_usuario('admin_teste', 'admin', is_admin=True)
        _login(client, 'admin_teste')
        resp = client.post(
            f"/professor/aluno/editar/{professor_com_aluno['aluno_id']}",
            data={'nome_completo': 'Editado Pelo Admin', 'email': 'aluno1@teste.com', 'telefone': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.nome_completo == 'Editado Pelo Admin'

    def test_admin_nao_pode_trocar_email_para_um_ja_usado(self, client, professor_com_aluno):
        with client.application.app_context():
            admin = _criar_usuario('admin_teste_email', 'admin', is_admin=True)
            email_original = db.session.get(User, professor_com_aluno['aluno_id']).email
        _login(client, 'admin_teste_email')

        resp = client.post(
            f"/professor/aluno/editar/{professor_com_aluno['aluno_id']}",
            # e-mail do OUTRO aluno já existente, criado pela fixture
            data={'nome_completo': 'X', 'email': 'aluno2@teste.com', 'telefone': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.email == email_original


class TestDesativarReativarAluno:
    def test_professor_nao_pode_desativar_proprio_aluno(self, client, professor_com_aluno):
        """Desativar é restrito ao admin -- mesmo o professor vinculado não pode."""
        _login(client, 'prof1')
        resp = client.post(
            f"/professor/aluno/desativar/{professor_com_aluno['aluno_id']}",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.ativo is True

    def test_professor_nao_pode_desativar_aluno_de_outro_professor(self, client, professor_com_aluno):
        _login(client, 'prof1')
        client.post(f"/professor/aluno/desativar/{professor_com_aluno['aluno_de_outro_id']}")
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_de_outro_id'])
            assert aluno.ativo is True

    def test_admin_pode_desativar_aluno(self, client, professor_com_aluno):
        with client.application.app_context():
            admin = _criar_usuario('admin_teste2', 'admin', is_admin=True)
        _login(client, 'admin_teste2')
        client.post(f"/professor/aluno/desativar/{professor_com_aluno['aluno_id']}")
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.ativo is False

    def test_admin_pode_reativar_aluno(self, client, professor_com_aluno):
        with client.application.app_context():
            admin = _criar_usuario('admin_teste3', 'admin', is_admin=True)
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            aluno.ativo = False
            db.session.commit()
        _login(client, 'admin_teste3')
        resp = client.post(f"/professor/aluno/reativar/{professor_com_aluno['aluno_id']}", follow_redirects=True)
        assert resp.status_code == 200
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.ativo is True

    def test_professor_nao_pode_reativar_proprio_aluno(self, client, professor_com_aluno):
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            aluno.ativo = False
            db.session.commit()
        _login(client, 'prof1')
        client.post(f"/professor/aluno/reativar/{professor_com_aluno['aluno_id']}")
        with client.application.app_context():
            aluno = db.session.get(User, professor_com_aluno['aluno_id'])
            assert aluno.ativo is False


class TestCalendarioAluno:
    def test_professor_acessa_calendario_do_proprio_aluno(self, client, professor_com_aluno):
        _login(client, 'prof1')
        resp = client.get(f"/professor/aluno/{professor_com_aluno['aluno_id']}/calendario")
        assert resp.status_code == 200

    def test_professor_nao_acessa_calendario_de_aluno_alheio(self, client, professor_com_aluno):
        _login(client, 'prof1')
        resp = client.get(
            f"/professor/aluno/{professor_com_aluno['aluno_de_outro_id']}/calendario",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b'permiss\xc3\xa3o' in resp.data.lower() or b'permissao' in resp.data.lower()

    def test_api_eventos_com_aluno_id_de_outro_professor_nao_vaza_dados(self, client, professor_com_aluno):
        """Professor não deve conseguir ler eventos de aluno alheio via query param."""
        _login(client, 'prof1')
        resp = client.get(f"/calendar/api/eventos?aluno_id={professor_com_aluno['aluno_de_outro_id']}")
        assert resp.status_code == 200
        # get_target_user_id cai de volta pro próprio professor -- não deve
        # levantar erro, mas também não deve retornar dados do aluno alheio.
        assert resp.get_json() == []