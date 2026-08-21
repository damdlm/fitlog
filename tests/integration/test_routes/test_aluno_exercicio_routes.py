"""
Testes de regressão para routes/aluno/exercicio.py (CRUD de exercícios
customizados do aluno). Tinha 54% de cobertura.
"""
from models import db, User, Musculo, ExercicioCustomizado


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestListarExercicios:
    def test_lista_vazia(self, client, app):
        with app.app_context():
            _criar_usuario('ae_list_1')
        _login(client, 'ae_list_1')

        resp = client.get('/aluno/exercicios')
        assert resp.status_code == 200

    def test_lista_exercicio_customizado(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_list_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()

        _login(client, 'ae_list_2')
        resp = client.get('/aluno/exercicios')

        assert resp.status_code == 200
        assert 'Supino' in resp.get_data(as_text=True)

    def test_requer_login(self, client):
        resp = client.get('/aluno/exercicios')
        assert resp.status_code == 302


class TestNovoExercicio:
    def test_cria_exercicio_customizado(self, client, app):
        with app.app_context():
            _criar_usuario('ae_novo_1')
        _login(client, 'ae_novo_1')

        resp = client.post('/aluno/exercicio/novo', data={
            'nome': 'Supino Reto', 'musculo': 'Peito', 'descricao': 'd'
        })

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='ae_novo_1').first()
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id, nome='Supino Reto').first() is not None

    def test_sem_nome_nao_cria(self, client, app):
        with app.app_context():
            _criar_usuario('ae_novo_2')
        _login(client, 'ae_novo_2')

        resp = client.post('/aluno/exercicio/novo', data={'musculo': 'Peito'})

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='ae_novo_2').first()
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id).count() == 0


class TestEditarExercicio:
    def test_form_de_edicao_vem_com_musculo_pre_selecionado(self, client, app):
        """Regressão: o template comparava exercicio.musculo (atributo
        que não existe no modelo -- só musculo_id/musculo_ref), então o
        <select> sempre caía em 'Selecione...' ao abrir a tela de
        edição, mesmo o exercício já tendo um músculo cadastrado."""
        with app.app_context():
            u = _criar_usuario('ae_edit_0')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Costas')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Puxada Frontal', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_edit_0')

        resp = client.get(f'/aluno/exercicio/{ex_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '<option value="Costas" selected>' in html
        # Nenhuma outra opção do dropdown pode vir marcada.
        assert 'selected' not in html.replace('<option value="Costas" selected>', '', 1)

    def test_edita_exercicio_customizado(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_edit_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_edit_1')

        resp = client.post(f'/aluno/exercicio/{ex_id}', data={
            'nome': 'Supino Inclinado', 'musculo': 'Peito', 'descricao': ''
        })

        assert resp.status_code == 302
        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Inclinado'

    def test_exercicio_inexistente_redireciona(self, client, app):
        with app.app_context():
            _criar_usuario('ae_edit_2')
        _login(client, 'ae_edit_2')

        resp = client.get('/aluno/exercicio/999999')
        assert resp.status_code == 302

    def test_nao_edita_exercicio_de_outro_usuario(self, client, app):
        with app.app_context():
            a = _criar_usuario('ae_edit_a')
            b = _criar_usuario('ae_edit_b')
            musc = Musculo(nome=f'm_{b.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercicio do B', musculo_id=musc.id)
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'ae_edit_a')

        resp = client.post(f'/aluno/exercicio/{ex_b_id}', data={'nome': 'Hackeado', 'musculo': 'Peito'})
        assert resp.status_code == 302

        with app.app_context():
            ex_b_depois = db.session.get(ExercicioCustomizado, ex_b_id)
            assert ex_b_depois.nome == 'Exercicio do B'


class TestExcluirExercicio:
    def test_sem_confirmar_nao_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_excl_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_excl_1')

        resp = client.post(f'/aluno/exercicio/{ex_id}/excluir')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_id) is not None

    def test_confirmado_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_excl_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_excl_2')

        resp = client.post(f'/aluno/exercicio/{ex_id}/excluir?confirmar=true')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_id) is None

    def test_nao_exclui_exercicio_de_outro_usuario(self, client, app):
        with app.app_context():
            a = _criar_usuario('ae_excl_a')
            b = _criar_usuario('ae_excl_b')
            musc = Musculo(nome=f'm_{b.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercicio do B', musculo_id=musc.id)
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'ae_excl_a')

        resp = client.post(f'/aluno/exercicio/{ex_b_id}/excluir?confirmar=true')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_b_id) is not None