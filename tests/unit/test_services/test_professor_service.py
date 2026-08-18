"""Testes unitários para services/professor_service.py"""
from flask_login import login_user

from models import db, User, AlunoProfessor
from services.professor_service import ProfessorService


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False, ativo=True):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario=tipo_usuario, is_admin=is_admin, ativo=ativo,
              nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _associar(aluno_id, professor_id, ativo=True):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo)
    db.session.add(assoc)
    db.session.commit()
    return assoc


class TestGetProfessores:
    def test_vazio_sem_usuario_logado(self, app):
        with app.app_context():
            assert ProfessorService.get_professores() == []

    def test_vazio_se_nao_admin(self, app):
        with app.app_context():
            prof_id = _criar_usuario('ps_getprofs_1', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            assert ProfessorService.get_professores() == []

    def test_admin_ve_professores_ativos(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_getprofs_2', is_admin=True).id
            _criar_usuario('ps_getprofs_p1', tipo_usuario='professor')
            _criar_usuario('ps_getprofs_p2', tipo_usuario='professor')
            _criar_usuario('ps_getprofs_p_inativo', tipo_usuario='professor', ativo=False)
            _criar_usuario('ps_getprofs_aluno', tipo_usuario='aluno')

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.get_professores()
            usernames = {u.username for u in resultado}
            assert usernames == {'ps_getprofs_p1', 'ps_getprofs_p2'}


class TestGetProfessorById:
    def test_none_sem_usuario_logado(self, app):
        with app.app_context():
            prof_id = _criar_usuario('ps_getbyid_1', tipo_usuario='professor').id
            assert ProfessorService.get_professor_by_id(prof_id) is None

    def test_none_para_id_inexistente(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('ps_getbyid_2').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            assert ProfessorService.get_professor_by_id(99999) is None

    def test_none_se_nao_e_professor(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('ps_getbyid_3').id
            outro_aluno_id = _criar_usuario('ps_getbyid_outro').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            assert ProfessorService.get_professor_by_id(outro_aluno_id) is None

    def test_none_se_professor_inativo(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('ps_getbyid_4').id
            prof_inativo_id = _criar_usuario('ps_getbyid_p_inativo', tipo_usuario='professor',
                                              ativo=False).id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            assert ProfessorService.get_professor_by_id(prof_inativo_id) is None

    def test_qualquer_usuario_logado_pode_ver_professor_ativo(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('ps_getbyid_5').id
            prof_id = _criar_usuario('ps_getbyid_p5', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            resultado = ProfessorService.get_professor_by_id(prof_id)
            assert resultado is not None
            assert resultado.id == prof_id


class TestCriarProfessor:
    def test_none_sem_usuario_logado(self, app):
        with app.app_context():
            resultado = ProfessorService.criar_professor({
                'username': 'novo_prof', 'email': 'novo@teste.com', 'password': 'senha123'
            })
            assert resultado is None

    def test_none_se_nao_e_admin(self, app):
        with app.app_context():
            prof_id = _criar_usuario('ps_criar_1', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = ProfessorService.criar_professor({
                'username': 'novo_prof2', 'email': 'novo2@teste.com', 'password': 'senha123'
            })
            assert resultado is None

    def test_admin_cria_professor_com_sucesso(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_criar_2', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.criar_professor({
                'username': 'novo_prof3', 'email': 'novo3@teste.com',
                'password': 'senha123', 'nome_completo': 'Novo Professor',
                'telefone': '11999999999'
            })
            assert resultado is not None
            assert resultado.tipo_usuario == 'professor'
            assert resultado.nome_completo == 'Novo Professor'
            assert resultado.check_password('senha123')


class TestGetAlunosDoProfessor:
    def test_vazio_sem_usuario_logado(self, app):
        with app.app_context():
            assert ProfessorService.get_alunos_do_professor() == []

    def test_vazio_se_aluno_sem_id_explicito(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('ps_alunos_1').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            assert ProfessorService.get_alunos_do_professor() == []

    def test_professor_ve_proprios_alunos_sem_id_explicito(self, app):
        with app.app_context():
            prof = _criar_usuario('ps_alunos_2', tipo_usuario='professor')
            aluno = _criar_usuario('ps_alunos_aluno2')
            _associar(aluno.id, prof.id)
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = ProfessorService.get_alunos_do_professor()
            assert len(resultado) == 1

    def test_professor_nao_ve_alunos_de_outro_professor(self, app):
        with app.app_context():
            prof1 = _criar_usuario('ps_alunos_3', tipo_usuario='professor')
            prof2 = _criar_usuario('ps_alunos_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('ps_alunos_aluno3')
            _associar(aluno.id, prof2.id)
            prof1_id, prof2_id = prof1.id, prof2.id

        with app.test_request_context():
            login_user(db.session.get(User, prof1_id))
            resultado = ProfessorService.get_alunos_do_professor(professor_id=prof2_id)
            assert resultado == []

    def test_admin_pode_ver_alunos_de_qualquer_professor(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_alunos_4', is_admin=True).id
            prof = _criar_usuario('ps_alunos_prof4', tipo_usuario='professor')
            aluno = _criar_usuario('ps_alunos_aluno4')
            _associar(aluno.id, prof.id)
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.get_alunos_do_professor(professor_id=prof_id)
            assert len(resultado) == 1

    def test_professor_pode_ver_proprios_alunos_com_id_explicito(self, app):
        with app.app_context():
            prof = _criar_usuario('ps_alunos_5', tipo_usuario='professor')
            aluno = _criar_usuario('ps_alunos_aluno5')
            _associar(aluno.id, prof.id)
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = ProfessorService.get_alunos_do_professor(professor_id=prof_id)
            assert len(resultado) == 1


class TestAtualizarProfessor:
    def test_none_sem_usuario_logado(self, app):
        with app.app_context():
            prof_id = _criar_usuario('ps_atualizar_1', tipo_usuario='professor').id
            assert ProfessorService.atualizar_professor(prof_id, {'nome_completo': 'X'}) is None

    def test_admin_pode_atualizar(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_2', is_admin=True).id
            prof_id = _criar_usuario('ps_atualizar_p2', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.atualizar_professor(prof_id, {'nome_completo': 'Atualizado'})
            assert resultado is not None
            assert resultado.nome_completo == 'Atualizado'

    def test_proprio_professor_pode_atualizar(self, app):
        with app.app_context():
            prof_id = _criar_usuario('ps_atualizar_self', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = ProfessorService.atualizar_professor(prof_id, {'telefone': '11988887777'})
            assert resultado is not None
            assert resultado.telefone == '11988887777'

    def test_outro_usuario_nao_pode_atualizar(self, app):
        with app.app_context():
            p1_id = _criar_usuario('ps_atualizar_p1', tipo_usuario='professor').id
            p2_id = _criar_usuario('ps_atualizar_p2b', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, p1_id))
            resultado = ProfessorService.atualizar_professor(p2_id, {'nome_completo': 'Hackeado'})
            assert resultado is None

    def test_none_se_alvo_nao_e_professor(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_3', is_admin=True).id
            aluno_id = _criar_usuario('ps_atualizar_aluno3').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.atualizar_professor(aluno_id, {'nome_completo': 'X'})
            assert resultado is None

    def test_none_se_professor_nao_existe(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_4', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert ProfessorService.atualizar_professor(99999, {'nome_completo': 'X'}) is None

    def test_falha_email_ja_em_uso(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_5', is_admin=True).id
            existente = _criar_usuario('ps_atualizar_existente', tipo_usuario='professor')
            existente.email = 'jaexiste@teste.com'
            alvo = _criar_usuario('ps_atualizar_alvo5', tipo_usuario='professor')
            db.session.commit()
            alvo_id = alvo.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.atualizar_professor(alvo_id, {'email': 'jaexiste@teste.com'})
            assert resultado is None

    def test_atualiza_email_disponivel(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_6', is_admin=True).id
            prof_id = _criar_usuario('ps_atualizar_p6', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.atualizar_professor(prof_id, {'email': 'disponivel@teste.com'})
            assert resultado is not None
            assert resultado.email == 'disponivel@teste.com'

    def test_manter_mesmo_email_nao_falha(self, app):
        with app.app_context():
            admin_id = _criar_usuario('ps_atualizar_7', is_admin=True).id
            prof = _criar_usuario('ps_atualizar_p7', tipo_usuario='professor')
            prof.email = 'mesmo@teste.com'
            db.session.commit()
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = ProfessorService.atualizar_professor(
                prof_id, {'email': 'mesmo@teste.com', 'nome_completo': 'Nome Novo'})
            assert resultado is not None
            assert resultado.nome_completo == 'Nome Novo'
