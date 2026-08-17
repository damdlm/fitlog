"""
Teste de regressão para professor.novo_treino_aluno (routes/professor_routes.py).

Espelha o comportamento de aluno.novo_treino (ver
test_aluno_treino_routes.py::TestNovoTreino): a rota não cadastra treino
diretamente -- treinos só existem dentro de uma versão -- então ela só
direciona o professor para a versão ativa do aluno, se existir, ou para a
tela de criar uma versão nova, caso o aluno ainda não tenha nenhuma.
"""
from datetime import date
from models import db, User, AlunoProfessor
from services.versao_service import VersaoService


def _criar_usuario(username, tipo_usuario, ativo=True):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title(), ativo=ativo)
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestNovoTreinoAluno:
    def test_sem_versao_redireciona_para_nova_versao_do_aluno(self, client, app):
        with app.app_context():
            professor = _criar_usuario('pnt_prof_1', 'professor')
            aluno = _criar_usuario('pnt_aluno_1', 'aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
            db.session.commit()
            aluno_id = aluno.id
        _login(client, 'pnt_prof_1')

        resp = client.get(f'/professor/aluno/{aluno_id}/treino/novo')

        assert resp.status_code == 302
        assert f'/professor/aluno/{aluno_id}/versao/nova' in resp.headers['Location']

    def test_com_versao_ativa_redireciona_para_novo_treino_da_versao(self, client, app):
        with app.app_context():
            professor = _criar_usuario('pnt_prof_2', 'professor')
            aluno = _criar_usuario('pnt_aluno_2', 'aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
            db.session.commit()
            versao = VersaoService.create(descricao='V1', data_inicio=date(2026, 1, 1), user_id=aluno.id)
            aluno_id, versao_id = aluno.id, versao.id
        _login(client, 'pnt_prof_2')

        resp = client.get(f'/professor/aluno/{aluno_id}/treino/novo')

        assert resp.status_code == 302
        assert f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo' in resp.headers['Location']

    def test_professor_sem_vinculo_e_negado(self, client, app):
        with app.app_context():
            _criar_usuario('pnt_prof_3', 'professor')
            outro_professor = _criar_usuario('pnt_prof_4', 'professor')
            aluno = _criar_usuario('pnt_aluno_3', 'aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=outro_professor.id, ativo=True))
            db.session.commit()
            aluno_id = aluno.id
        _login(client, 'pnt_prof_3')

        resp = client.get(f'/professor/aluno/{aluno_id}/treino/novo')

        assert resp.status_code == 302
        assert '/professor/alunos' in resp.headers['Location']