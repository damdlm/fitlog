"""Testes unitários para services/aluno_service.py"""
from flask_login import login_user

from models import db, User, AlunoProfessor
from services.aluno_service import AlunoService


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


class TestGetAlunos:
    def test_retorna_vazio_sem_usuario_logado(self, app):
        with app.app_context():
            assert AlunoService.get_alunos() == []

    def test_admin_ve_todos_os_alunos_ativos(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_admin_1', is_admin=True).id
            a1 = _criar_usuario('as_admin_aluno1')
            a2 = _criar_usuario('as_admin_aluno2')
            _criar_usuario('as_admin_prof', tipo_usuario='professor')

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.get_alunos()
            usernames = {u.username for u in resultado}
            # A query filtra por tipo_usuario='aluno' -- o admin de dev
            # criado no startup da app e o próprio admin de teste também
            # têm tipo_usuario='aluno' (valor default do modelo), então
            # aparecem na lista junto dos 2 alunos criados aqui.
            assert {'as_admin_aluno1', 'as_admin_aluno2'} <= usernames
            assert 'as_admin_prof' not in usernames

    def test_admin_nao_ve_alunos_inativos(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_admin_2', is_admin=True).id
            _criar_usuario('as_admin_aluno_inativo', ativo=False)

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.get_alunos()
            usernames = {u.username for u in resultado}
            assert 'as_admin_aluno_inativo' not in usernames

    def test_professor_ve_apenas_seus_alunos(self, app):
        with app.app_context():
            prof = _criar_usuario('as_prof_1', tipo_usuario='professor')
            aluno_do_prof = _criar_usuario('as_prof_aluno1')
            outro_aluno = _criar_usuario('as_prof_aluno2')
            _associar(aluno_do_prof.id, prof.id)
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = AlunoService.get_alunos()
            assert len(resultado) == 1
            assert resultado[0].username == 'as_prof_aluno1'

    def test_professor_pode_ver_alunos_de_outro_professor_id_explicito(self, app):
        with app.app_context():
            prof1 = _criar_usuario('as_prof_x1', tipo_usuario='professor')
            prof2 = _criar_usuario('as_prof_x2', tipo_usuario='professor')
            aluno = _criar_usuario('as_prof_x_aluno')
            _associar(aluno.id, prof2.id)
            prof1_id, prof2_id = prof1.id, prof2.id

        with app.test_request_context():
            login_user(db.session.get(User, prof1_id))
            resultado = AlunoService.get_alunos(professor_id=prof2_id)
            assert len(resultado) == 1

    def test_aluno_ve_apenas_a_si_mesmo(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_aluno_self').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            resultado = AlunoService.get_alunos()
            assert len(resultado) == 1
            assert resultado[0].id == aluno_id

    def test_aluno_inativo_nao_ve_a_si_mesmo(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_aluno_inativo_self')
            aluno_id = aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            aluno_logado = db.session.get(User, aluno_id)
            aluno_logado.ativo = False
            db.session.commit()

            resultado = AlunoService.get_alunos()
            assert resultado == []


class TestGetAlunoById:
    def test_retorna_none_sem_usuario_logado(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_getbyid_1').id
            assert AlunoService.get_aluno_by_id(aluno_id) is None

    def test_retorna_none_para_id_inexistente(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_getbyid_2', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.get_aluno_by_id(99999) is None

    def test_retorna_none_se_usuario_nao_e_aluno(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_getbyid_3', is_admin=True).id
            prof = _criar_usuario('as_getbyid_prof', tipo_usuario='professor')
            prof_id = prof.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.get_aluno_by_id(prof_id) is None

    def test_retorna_none_se_aluno_inativo(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_getbyid_4', is_admin=True).id
            aluno = _criar_usuario('as_getbyid_inativo', ativo=False)
            aluno_id = aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.get_aluno_by_id(aluno_id) is None

    def test_admin_acessa_qualquer_aluno(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_getbyid_5', is_admin=True).id
            aluno = _criar_usuario('as_getbyid_aluno5')
            aluno_id = aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.get_aluno_by_id(aluno_id)
            assert resultado is not None
            assert resultado.id == aluno_id

    def test_aluno_nao_acessa_outro_aluno(self, app):
        with app.app_context():
            a1 = _criar_usuario('as_getbyid_a1')
            a2 = _criar_usuario('as_getbyid_a2')
            a1_id, a2_id = a1.id, a2.id

        with app.test_request_context():
            login_user(db.session.get(User, a1_id))
            assert AlunoService.get_aluno_by_id(a2_id) is None

    def test_aluno_acessa_a_si_mesmo(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_getbyid_self').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            resultado = AlunoService.get_aluno_by_id(aluno_id)
            assert resultado is not None

    def test_professor_acessa_seu_aluno(self, app):
        with app.app_context():
            prof = _criar_usuario('as_getbyid_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('as_getbyid_aluno_prof2')
            _associar(aluno.id, prof.id)
            prof_id, aluno_id = prof.id, aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = AlunoService.get_aluno_by_id(aluno_id)
            assert resultado is not None


class TestAssociarProfessor:
    def test_falha_sem_usuario_logado(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_assoc_1').id
            prof_id = _criar_usuario('as_assoc_prof1', tipo_usuario='professor').id
            assert AlunoService.associar_professor(aluno_id, prof_id) is False

    def test_admin_pode_associar(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_assoc_2', is_admin=True).id
            aluno = _criar_usuario('as_assoc_aluno2')
            prof = _criar_usuario('as_assoc_prof2', tipo_usuario='professor')
            aluno_id, prof_id = aluno.id, prof.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.associar_professor(aluno_id, prof_id)
            assert resultado is True

            assoc = AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first()
            assert assoc is not None
            assert assoc.professor_id == prof_id

    def test_professor_pode_associar_a_si_mesmo(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_assoc_aluno3')
            prof = _criar_usuario('as_assoc_prof3', tipo_usuario='professor')
            aluno_id, prof_id = aluno.id, prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = AlunoService.associar_professor(aluno_id, prof_id)
            assert resultado is True

    def test_professor_nao_pode_associar_a_outro_professor(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_assoc_aluno4')
            prof1 = _criar_usuario('as_assoc_prof4a', tipo_usuario='professor')
            prof2 = _criar_usuario('as_assoc_prof4b', tipo_usuario='professor')
            aluno_id, prof1_id, prof2_id = aluno.id, prof1.id, prof2.id

        with app.test_request_context():
            login_user(db.session.get(User, prof1_id))
            resultado = AlunoService.associar_professor(aluno_id, prof2_id)
            assert resultado is False

    def test_falha_se_aluno_nao_existe(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_assoc_5', is_admin=True).id
            prof_id = _criar_usuario('as_assoc_prof5', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.associar_professor(99999, prof_id) is False

    def test_falha_se_professor_nao_existe(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_assoc_6', is_admin=True).id
            aluno_id = _criar_usuario('as_assoc_aluno6').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.associar_professor(aluno_id, 99999) is False

    def test_falha_se_id_de_aluno_e_na_verdade_professor(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_assoc_7', is_admin=True).id
            falso_aluno = _criar_usuario('as_assoc_falsoaluno', tipo_usuario='professor')
            prof_id = _criar_usuario('as_assoc_prof7', tipo_usuario='professor').id
            falso_aluno_id = falso_aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.associar_professor(falso_aluno_id, prof_id) is False

    def test_ja_associado_ao_mesmo_professor_retorna_true(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_assoc_aluno8')
            prof = _criar_usuario('as_assoc_prof8', tipo_usuario='professor')
            _associar(aluno.id, prof.id)
            aluno_id, prof_id = aluno.id, prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = AlunoService.associar_professor(aluno_id, prof_id)
            assert resultado is True

    def test_troca_de_professor_falha_bug_constraint_unica(self, app):
        """
        NOTA (bug conhecido): AlunoProfessor.aluno_id tem unique=True no
        nível do banco (uma linha por aluno, no total -- não apenas por
        associação ativa). O fluxo de "troca de professor" em
        associar_professor() desativa a associação antiga (ativo=False)
        e tenta inserir uma nova linha para o mesmo aluno_id, o que
        sempre viola a constraint UNIQUE e lança IntegrityError. O
        try/except captura o erro, faz rollback e retorna False -- ou
        seja, hoje NUNCA é possível trocar o professor de um aluno já
        associado. Este teste documenta o comportamento atual.
        """
        with app.app_context():
            admin_id = _criar_usuario('as_assoc_9', is_admin=True).id
            aluno = _criar_usuario('as_assoc_aluno9')
            prof_antigo = _criar_usuario('as_assoc_prof9a', tipo_usuario='professor')
            prof_novo = _criar_usuario('as_assoc_prof9b', tipo_usuario='professor')
            assoc_antiga = _associar(aluno.id, prof_antigo.id)
            aluno_id, prof_novo_id = aluno.id, prof_novo.id
            assoc_antiga_id = assoc_antiga.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.associar_professor(aluno_id, prof_novo_id)
            assert resultado is False

            # A associação antiga permanece ativa, já que o rollback
            # desfaz também a alteração de assoc_existente.ativo = False.
            antiga = db.session.get(AlunoProfessor, assoc_antiga_id)
            assert antiga.ativo is True


class TestDesassociarProfessor:
    def test_falha_sem_usuario_logado(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_desassoc_1').id
            assert AlunoService.desassociar_professor(aluno_id) is False

    def test_falha_se_nao_ha_associacao(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_desassoc_2', is_admin=True).id
            aluno_id = _criar_usuario('as_desassoc_aluno2').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            assert AlunoService.desassociar_professor(aluno_id) is False

    def test_admin_pode_desassociar(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_desassoc_3', is_admin=True).id
            aluno = _criar_usuario('as_desassoc_aluno3')
            prof = _criar_usuario('as_desassoc_prof3', tipo_usuario='professor')
            _associar(aluno.id, prof.id)
            aluno_id = aluno.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.desassociar_professor(aluno_id)
            assert resultado is True

            assoc = AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first()
            assert assoc is None

    def test_professor_dono_pode_desassociar(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_desassoc_aluno4')
            prof = _criar_usuario('as_desassoc_prof4', tipo_usuario='professor')
            _associar(aluno.id, prof.id)
            aluno_id, prof_id = aluno.id, prof.id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            assert AlunoService.desassociar_professor(aluno_id) is True

    def test_outro_professor_nao_pode_desassociar(self, app):
        with app.app_context():
            aluno = _criar_usuario('as_desassoc_aluno5')
            prof1 = _criar_usuario('as_desassoc_prof5a', tipo_usuario='professor')
            prof2 = _criar_usuario('as_desassoc_prof5b', tipo_usuario='professor')
            _associar(aluno.id, prof1.id)
            aluno_id, prof2_id = aluno.id, prof2.id

        with app.test_request_context():
            login_user(db.session.get(User, prof2_id))
            assert AlunoService.desassociar_professor(aluno_id) is False


class TestCriarAluno:
    def test_falha_sem_usuario_logado(self, app):
        with app.app_context():
            resultado = AlunoService.criar_aluno({
                'username': 'novo_aluno', 'email': 'novo@teste.com', 'password': 'senha123'
            })
            assert resultado is None

    def test_falha_se_nao_e_admin(self, app):
        with app.app_context():
            prof_id = _criar_usuario('as_criar_prof1', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, prof_id))
            resultado = AlunoService.criar_aluno({
                'username': 'novo_aluno2', 'email': 'novo2@teste.com', 'password': 'senha123'
            })
            assert resultado is None

    def test_admin_cria_aluno_com_sucesso(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_criar_admin1', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.criar_aluno({
                'username': 'novo_aluno3', 'email': 'novo3@teste.com',
                'password': 'senha123', 'nome_completo': 'Novo Aluno'
            })
            assert resultado is not None
            assert resultado.tipo_usuario == 'aluno'
            assert resultado.check_password('senha123')


class TestAtualizarAluno:
    def test_falha_sem_usuario_logado(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_atualizar_1').id
            assert AlunoService.atualizar_aluno(aluno_id, {'nome_completo': 'X'}) is None

    def test_admin_pode_atualizar(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_atualizar_2', is_admin=True).id
            aluno_id = _criar_usuario('as_atualizar_aluno2').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.atualizar_aluno(aluno_id, {'nome_completo': 'Atualizado'})
            assert resultado is not None
            assert resultado.nome_completo == 'Atualizado'

    def test_proprio_aluno_pode_atualizar(self, app):
        with app.app_context():
            aluno_id = _criar_usuario('as_atualizar_self').id

        with app.test_request_context():
            login_user(db.session.get(User, aluno_id))
            resultado = AlunoService.atualizar_aluno(aluno_id, {'telefone': '11999999999'})
            assert resultado is not None
            assert resultado.telefone == '11999999999'

    def test_outro_aluno_nao_pode_atualizar(self, app):
        with app.app_context():
            a1_id = _criar_usuario('as_atualizar_a1').id
            a2_id = _criar_usuario('as_atualizar_a2').id

        with app.test_request_context():
            login_user(db.session.get(User, a1_id))
            resultado = AlunoService.atualizar_aluno(a2_id, {'nome_completo': 'Hackeado'})
            assert resultado is None

    def test_falha_email_ja_em_uso(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_atualizar_3', is_admin=True).id
            _criar_usuario('as_atualizar_existente', ativo=True)
            outro = db.session.get(User, _criar_usuario('as_atualizar_alvo').id)
            outro.email = 'alvo@teste.com'
            db.session.commit()
            existente = User.query.filter_by(username='as_atualizar_existente').first()
            existente.email = 'jaexiste@teste.com'
            db.session.commit()
            alvo_id = outro.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.atualizar_aluno(alvo_id, {'email': 'jaexiste@teste.com'})
            assert resultado is None

    def test_atualiza_email_disponivel(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_atualizar_4', is_admin=True).id
            aluno_id = _criar_usuario('as_atualizar_aluno4').id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.atualizar_aluno(aluno_id, {'email': 'disponivel@teste.com'})
            assert resultado is not None
            assert resultado.email == 'disponivel@teste.com'

    def test_retorna_none_para_aluno_inexistente(self, app):
        with app.app_context():
            admin_id = _criar_usuario('as_atualizar_5', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))
            resultado = AlunoService.atualizar_aluno(99999, {'nome_completo': 'X'})
            assert resultado is None
