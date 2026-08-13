"""
Testes de regressão para routes/aluno/treino.py (CRUD de treinos do
aluno/professor -- rota /aluno/treinos era a de maior tráfego do app,
tinha 25% de cobertura, e foi uma das alteradas na otimização de N+1
desta fase).
"""
from models import db, User, Musculo, ExercicioUsuario, Treino
from services.versao_service import VersaoService
from services.treino_service import TreinoService
from datetime import date


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestListarTreinos:
    def test_lista_vazia_sem_treinos(self, client, app):
        with app.app_context():
            _criar_usuario('at_list_1')
        _login(client, 'at_list_1')

        resp = client.get('/aluno/treinos')
        assert resp.status_code == 200

    def test_pagina_carrega_com_filtro_por_data(self, client, app):
        """A tela não lista mais os treinos avulsos (A/B/C) nem tem
        botão 'Novo Treino' -- só o filtro por data para ver/editar
        sessões já registradas. Ver routes/aluno/treino.py::treinos()."""
        with app.app_context():
            u = _criar_usuario('at_list_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [ex.id], [], user_id=u.id)

        _login(client, 'at_list_2')
        resp = client.get('/aluno/treinos')

        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'mtFiltroData' in body
        assert 'Novo Treino' not in body

    def test_professor_tambem_acessa_a_propria_lista(self, client, app):
        with app.app_context():
            _criar_usuario('at_list_prof', tipo_usuario='professor')
        _login(client, 'at_list_prof')

        resp = client.get('/aluno/treinos')
        assert resp.status_code == 200

    def test_requer_login(self, client):
        resp = client.get('/aluno/treinos')
        assert resp.status_code == 302


class TestNovoTreino:
    def test_cria_treino_com_sucesso(self, client, app):
        with app.app_context():
            _criar_usuario('at_novo_1')
        _login(client, 'at_novo_1')

        resp = client.post('/aluno/treino/novo', data={'id': 'A', 'nome': 'Treino A', 'descricao': 'peito'})

        assert resp.status_code == 302
        assert '/aluno/treinos' in resp.headers['Location']
        with app.app_context():
            u = User.query.filter_by(username='at_novo_1').first()
            assert Treino.query.filter_by(codigo='A', user_id=u.id).first() is not None

    def test_codigo_invalido_nao_cria(self, client, app):
        with app.app_context():
            _criar_usuario('at_novo_2')
        _login(client, 'at_novo_2')

        resp = client.post('/aluno/treino/novo', data={'id': 'AB', 'nome': 'Treino AB'})

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='at_novo_2').first()
            assert Treino.query.filter_by(user_id=u.id).count() == 0

    def test_codigo_duplicado_nao_cria_outro(self, client, app):
        with app.app_context():
            u = _criar_usuario('at_novo_3')
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
        _login(client, 'at_novo_3')

        resp = client.post('/aluno/treino/novo', data={'id': 'A', 'nome': 'Outro Treino A'})

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='at_novo_3').first()
            assert Treino.query.filter_by(codigo='A', user_id=u.id).count() == 1


class TestEditarTreino:
    def test_edita_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('at_edit_1')
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            treino_id = treino.id
        _login(client, 'at_edit_1')

        resp = client.post(f'/aluno/treino/{treino_id}', data={'id': 'A', 'nome': 'Treino A Editado', 'descricao': 'novo'})

        assert resp.status_code == 302
        with app.app_context():
            atualizado = db.session.get(Treino, treino_id)
            assert atualizado.nome == 'Treino A Editado'

    def test_treino_inexistente_retorna_redirect_sem_500(self, client, app):
        with app.app_context():
            _criar_usuario('at_edit_2')
        _login(client, 'at_edit_2')

        resp = client.get('/aluno/treino/999999')
        assert resp.status_code == 302

    def test_nao_edita_treino_de_outro_usuario(self, client, app):
        """IDOR: usuário A não pode editar treino do usuário B via URL direta."""
        with app.app_context():
            a = _criar_usuario('at_edit_a')
            b = _criar_usuario('at_edit_b')
            treino_b = TreinoService.create('A', 'Treino do B', 'd', user_id=b.id)
            treino_b_id = treino_b.id
        _login(client, 'at_edit_a')

        resp_get = client.get(f'/aluno/treino/{treino_b_id}')
        assert resp_get.status_code == 302  # "não encontrado" (mascarado como não existente, não 403)

        resp_post = client.post(f'/aluno/treino/{treino_b_id}',
                                 data={'id': 'X', 'nome': 'Hackeado'})
        assert resp_post.status_code == 302
        with app.app_context():
            treino_b_depois = db.session.get(Treino, treino_b_id)
            assert treino_b_depois.nome == 'Treino do B'


class TestExcluirTreino:
    def test_sem_confirmar_nao_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('at_excl_1')
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            treino_id = treino.id
        _login(client, 'at_excl_1')

        resp = client.get(f'/aluno/treino/{treino_id}/excluir')

        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(Treino, treino_id) is not None

    def test_confirmado_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('at_excl_2')
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            treino_id = treino.id
        _login(client, 'at_excl_2')

        resp = client.get(f'/aluno/treino/{treino_id}/excluir?confirmar=true')

        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(Treino, treino_id) is None

    def test_nao_exclui_treino_de_outro_usuario(self, client, app):
        with app.app_context():
            a = _criar_usuario('at_excl_a')
            b = _criar_usuario('at_excl_b')
            treino_b = TreinoService.create('A', 'Treino do B', 'd', user_id=b.id)
            treino_b_id = treino_b.id
        _login(client, 'at_excl_a')

        resp = client.get(f'/aluno/treino/{treino_b_id}/excluir?confirmar=true')

        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(Treino, treino_b_id) is not None