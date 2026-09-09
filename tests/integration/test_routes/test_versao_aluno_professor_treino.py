"""Testes de integração para /aluno/versao/<id>/treino (routes/aluno/versao.py)
e /professor/aluno/<id>/versao/<id>/treino (routes/professor_routes.py).

Essas duas rotas são o par gêmeo de cadastrar_treinos_adicionar_treino
(routes/aluno/cadastro_treinos.py): mesmo VersaoService.adicionar_treino_livre
por baixo, só que acessadas pela tela "Ver Versão" (aluno vendo uma versão
específica, ou professor vendo/editando a versão de um aluno) em vez da tela
"Cadastrar Treinos". Nenhuma delas tinha teste algum antes -- cobertura
mínima adicionada junto com a mudança que unificou o modal de
adicionar/editar treino nas duas telas.
"""
from datetime import date, datetime, timezone

from models import (db, User, AlunoProfessor, VersaoGlobal,
                     TreinoVersao, ExercicioUsuario)


def _criar_usuario(username, tipo_usuario='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo_usuario,
              nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _criar_versao_ativa(user_id, numero=1):
    v = VersaoGlobal(numero_versao=numero, descricao='Versao livre', divisao='LIVRE',
                      data_inicio=date(2024, 1, 1), user_id=user_id)
    db.session.add(v)
    db.session.commit()
    return v


class TestVersaoAdicionarTreinoAluno:
    """POST /aluno/versao/<versao_id>/treino"""

    def test_adiciona_treino_ja_com_exercicios(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('vv_aluno1')
            ex1 = ExercicioUsuario(usuario_id=aluno.id, nome='Supino')
            ex2 = ExercicioUsuario(usuario_id=aluno.id, nome='Crucifixo')
            db.session.add_all([ex1, ex2])
            db.session.commit()
            versao = _criar_versao_ativa(aluno.id)
            versao_id, ex1_id, ex2_id = versao.id, ex1.id, ex2.id
            username = aluno.username

        _login(client, username)
        resp = client.post(f'/aluno/versao/{versao_id}/treino', data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{ex1_id}', f'u_{ex2_id}'],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            assert tv is not None
            ids_salvos = {ve.exercicio_usuario_id for ve in tv.exercicios}
            assert ids_salvos == {ex1_id, ex2_id}

    def test_adiciona_treino_sem_exercicios_continua_funcionando(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('vv_aluno2')
            versao = _criar_versao_ativa(aluno.id)
            versao_id = versao.id
            username = aluno.username

        _login(client, username)
        resp = client.post(f'/aluno/versao/{versao_id}/treino', data={
            'nome_treino': 'Treino sem exercícios', 'descricao_treino': ''
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            assert tv is not None
            assert tv.exercicios == []

    def test_idor_so_salva_exercicios_do_proprio_usuario(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('vv_aluno3')
            outro = _criar_usuario('vv_aluno4')
            ex_proprio = ExercicioUsuario(usuario_id=aluno.id, nome='Supino')
            ex_alheio = ExercicioUsuario(usuario_id=outro.id, nome='Exercício alheio')
            db.session.add_all([ex_proprio, ex_alheio])
            db.session.commit()
            versao = _criar_versao_ativa(aluno.id)
            versao_id, ex_proprio_id, ex_alheio_id = versao.id, ex_proprio.id, ex_alheio.id
            username = aluno.username

        _login(client, username)
        client.post(f'/aluno/versao/{versao_id}/treino', data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{ex_proprio_id}', f'u_{ex_alheio_id}'],
        }, follow_redirects=True)

        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            ids_salvos = {ve.exercicio_usuario_id for ve in tv.exercicios}
            assert ids_salvos == {ex_proprio_id}


class TestVersaoAdicionarTreinoAlunoPeloProfessor:
    """POST /professor/aluno/<aluno_id>/versao/<versao_id>/treino"""

    def test_professor_adiciona_treino_ja_com_exercicios(self, client, app):
        with app.app_context():
            prof = _criar_usuario('vv_prof1', tipo_usuario='professor')
            aluno = _criar_usuario('vv_prof1_aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True,
                                           data_associacao=datetime.now(timezone.utc)))
            ex1 = ExercicioUsuario(usuario_id=aluno.id, nome='Supino')
            db.session.add(ex1)
            db.session.commit()
            versao = _criar_versao_ativa(aluno.id)
            versao_id, aluno_id, ex1_id = versao.id, aluno.id, ex1.id
            username = prof.username

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino', data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{ex1_id}'],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            assert tv is not None
            assert {ve.exercicio_usuario_id for ve in tv.exercicios} == {ex1_id}

    def test_professor_sem_vinculo_nao_consegue_adicionar_treino(self, client, app):
        with app.app_context():
            prof = _criar_usuario('vv_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('vv_prof2_aluno')  # sem AlunoProfessor associando os dois
            versao = _criar_versao_ativa(aluno.id)
            versao_id, aluno_id = versao.id, aluno.id
            username = prof.username

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino', data={
            'nome_treino': 'Treino A', 'descricao_treino': ''
        })
        assert resp.status_code in (302, 403, 404)

        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_id).count() == 0
