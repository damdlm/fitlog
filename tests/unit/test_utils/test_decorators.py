"""Testes unitários para utils/decorators.py"""
from datetime import date

from flask import Flask
from flask_login import login_user

from models import db, User, VersaoGlobal
from utils.decorators import (
    admin_required,
    professor_required,
    aluno_required,
    owner_or_admin,
    log_execution_time,
)


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, is_admin=is_admin)
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


class TestAdminRequired:
    def test_redireciona_se_nao_autenticado(self, app):
        with app.test_request_context():
            @admin_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302
            assert '/auth/login' in resultado.location

    def test_redireciona_se_nao_admin(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_admin_1', tipo_usuario='aluno', is_admin=False).id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @admin_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302
            assert '/auth/login' not in resultado.location

    def test_permite_acesso_se_admin(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_admin_2', tipo_usuario='aluno', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @admin_required
            def view():
                return 'conteudo_admin'

            assert view() == 'conteudo_admin'


class TestProfessorRequired:
    def test_redireciona_se_nao_autenticado(self, app):
        with app.test_request_context():
            @professor_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_redireciona_se_aluno(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_prof_1', tipo_usuario='aluno').id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @professor_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_permite_acesso_se_professor(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_prof_2', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @professor_required
            def view():
                return 'conteudo_professor'

            assert view() == 'conteudo_professor'

    def test_permite_acesso_se_admin(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_prof_3', tipo_usuario='aluno', is_admin=True).id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @professor_required
            def view():
                return 'conteudo_professor'

            assert view() == 'conteudo_professor'


class TestAlunoRequired:
    def test_redireciona_se_nao_autenticado(self, app):
        with app.test_request_context():
            @aluno_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_redireciona_se_professor(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_aluno_1', tipo_usuario='professor').id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @aluno_required
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_permite_acesso_se_aluno(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_aluno_2', tipo_usuario='aluno').id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @aluno_required
            def view():
                return 'conteudo_aluno'

            assert view() == 'conteudo_aluno'


class TestOwnerOrAdmin:
    def test_redireciona_se_nao_autenticado(self, app):
        with app.test_request_context():
            @owner_or_admin(lambda *a, **k: None)
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302
            assert '/auth/login' in resultado.location

    def test_permite_acesso_se_admin_mesmo_sem_ser_dono(self, app):
        with app.app_context():
            admin_id = _criar_usuario('dec_owner_admin', is_admin=True).id
            dono = _criar_usuario('dec_owner_dono')
            treino = VersaoGlobal(numero_versao=1, descricao='T', divisao='ABC', data_inicio=date(2026, 1, 1), user_id=dono.id)
            db.session.add(treino)
            db.session.commit()
            treino_id = treino.id

        with app.test_request_context():
            login_user(db.session.get(User, admin_id))

            @owner_or_admin(lambda: db.session.get(VersaoGlobal, treino_id))
            def view():
                return 'ok'

            assert view() == 'ok'

    def test_redireciona_se_recurso_nao_encontrado(self, app):
        with app.app_context():
            u_id = _criar_usuario('dec_owner_notfound').id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))

            @owner_or_admin(lambda: None)
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_permite_acesso_se_dono_user_id(self, app):
        with app.app_context():
            dono = _criar_usuario('dec_owner_dono2')
            treino = VersaoGlobal(numero_versao=1, descricao='T', divisao='ABC', data_inicio=date(2026, 1, 1), user_id=dono.id)
            db.session.add(treino)
            db.session.commit()
            treino_id, dono_id = treino.id, dono.id

        with app.test_request_context():
            login_user(db.session.get(User, dono_id))

            @owner_or_admin(lambda: db.session.get(VersaoGlobal, treino_id))
            def view():
                return 'ok'

            assert view() == 'ok'

    def test_nega_acesso_se_nao_for_dono(self, app):
        with app.app_context():
            dono = _criar_usuario('dec_owner_dono3')
            outro_id = _criar_usuario('dec_owner_outro').id
            treino = VersaoGlobal(numero_versao=1, descricao='T', divisao='ABC', data_inicio=date(2026, 1, 1), user_id=dono.id)
            db.session.add(treino)
            db.session.commit()
            treino_id = treino.id

        with app.test_request_context():
            login_user(db.session.get(User, outro_id))

            @owner_or_admin(lambda: db.session.get(VersaoGlobal, treino_id))
            def view():
                return 'ok'

            resultado = view()
            assert resultado.status_code == 302

    def test_permite_acesso_se_dono_usuario_id(self, app):
        """Cobre o ramo que checa 'usuario_id' em vez de 'user_id'."""
        with app.app_context():
            from models import ExercicioUsuario
            dono = _criar_usuario('dec_owner_usuarioid')
            ex = ExercicioUsuario(usuario_id=dono.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()
            ex_id, dono_id = ex.id, dono.id

        with app.test_request_context():
            from models import ExercicioUsuario
            login_user(db.session.get(User, dono_id))

            @owner_or_admin(lambda: db.session.get(ExercicioUsuario, ex_id))
            def view():
                return 'ok'

            assert view() == 'ok'


class TestLogExecutionTime:
    def test_executa_e_retorna_valor_da_funcao(self, app):
        with app.app_context():
            @log_execution_time
            def soma(a, b):
                return a + b

            assert soma(2, 3) == 5
