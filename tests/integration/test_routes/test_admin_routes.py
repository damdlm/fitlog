"""
Testes de regressão para routes/admin_routes.py.

Cobre principalmente admin.editar_exercicio, que tinha um bug real
encontrado na Fase 5: a rota sempre respondia com redirect() (HTML),
mas o JS de templates/admin/gerenciar_treinos.html chama a rota via
fetch() e faz response.json() -- ou seja, a edição de exercício pelo
modal parecia "não fazer nada" (o parse de JSON falhava silenciosamente
no browser). A correção faz a rota responder com JSON quando a chamada
vem via AJAX (header X-Requested-With, que o próprio JS já envia),
preservando redirect+flash para qualquer outro chamador.
"""
from models import db, User, ExercicioCustomizado, ExercicioUsuario, Musculo


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


HEADERS_AJAX = {'X-Requested-With': 'XMLHttpRequest'}


class TestEditarExercicioAjax:
    """A chamada real do template é sempre via fetch() -- deve responder JSON."""

    def test_edicao_bem_sucedida_retorna_json(self, client, app):
        with app.app_context():
            u = _criar_usuario('user_edit_ok')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_ok')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Reto',
                                  'musculo': 'Peito', 'descricao': ''},
                            headers=HEADERS_AJAX)

        assert resp.content_type == 'application/json'
        data = resp.get_json()
        assert data['success'] is True

        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Reto'

    def test_edicao_exercicio_usuario_base_retorna_json(self, client, app):
        """Personalização de exercício do catálogo (ExercicioUsuario), não custom."""
        with app.app_context():
            u = _criar_usuario('user_edit_base')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino base', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_base')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Personalizado',
                                  'musculo': 'Peito', 'descricao': 'nova descrição'},
                            headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is True
        with app.app_context():
            atualizado = db.session.get(ExercicioUsuario, ex_id)
            assert atualizado.nome == 'Supino Personalizado'

    def test_exercicio_inexistente_retorna_success_false_sem_500(self, client, app):
        with app.app_context():
            _criar_usuario('user_edit_404')
        _login(client, 'user_edit_404')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': '999999', 'nome': 'Fantasma'},
                            headers=HEADERS_AJAX)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False

    def test_dados_invalidos_retorna_success_false(self, client, app):
        with app.app_context():
            _criar_usuario('user_edit_invalido')
        _login(client, 'user_edit_invalido')

        resp = client.post('/admin/editar/exercicio', data={'id': ''}, headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is False

    def test_nao_edita_exercicio_de_outro_usuario(self, client, app):
        """IDOR: usuário A não deve conseguir editar exercício de B via essa rota."""
        with app.app_context():
            a = _criar_usuario('user_edit_a')
            b = _criar_usuario('user_edit_b')
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercício do B')
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'user_edit_a')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_b_id), 'nome': 'Hackeado'},
                            headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is False
        with app.app_context():
            ex_b_depois = db.session.get(ExercicioCustomizado, ex_b_id)
            assert ex_b_depois.nome == 'Exercício do B'


class TestEditarExercicioSemAjax:
    """Sem o header X-Requested-With, mantém o comportamento antigo (redirect)."""

    def test_sem_header_ajax_faz_redirect(self, client, app):
        with app.app_context():
            u = _criar_usuario('user_edit_form')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_form')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Inclinado'})

        assert resp.status_code == 302
        assert '/admin/gerenciar' in resp.headers['Location']

        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Inclinado'


class TestEditarExercicioRequerLogin:
    def test_requer_autenticacao(self, client):
        resp = client.post('/admin/editar/exercicio', data={'id': '1', 'nome': 'x'})
        assert resp.status_code in (302, 401)
