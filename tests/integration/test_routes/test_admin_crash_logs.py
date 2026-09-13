"""Testes de integração para routes/admin_routes.py:crash_logs -- painel
de travamentos e endpoint público que recebe relatos do frontend (ver
static/js/crash-watchdog.js)."""
from models import db, User, CrashLog


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, is_admin=is_admin)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


class TestPainelCrashLogs:
    def test_exige_login(self, client):
        resp = client.get('/admin/crash-logs')
        assert resp.status_code in (302, 401)

    def test_nao_admin_e_bloqueado(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('crashlogs_nao_admin')
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/admin/crash-logs', follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/crash-logs' not in resp.headers.get('Location', '')

    def test_admin_ve_lista_com_travamentos(self, client, app):
        with app.app_context():
            admin = _criar_usuario('crashlogs_admin', is_admin=True)
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='TypeError misterioso'))
            db.session.add(CrashLog(origem='backend', tipo='ValueError', mensagem='falha no servidor'))
            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/crash-logs')
        assert resp.status_code == 200
        assert b'TypeError misterioso' in resp.data
        assert b'falha no servidor' in resp.data

    def test_filtro_por_origem(self, client, app):
        with app.app_context():
            admin = _criar_usuario('crashlogs_admin_filtro', is_admin=True)
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='so_frontend_aqui'))
            db.session.add(CrashLog(origem='backend', tipo='ValueError', mensagem='so_backend_aqui'))
            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/crash-logs?origem=frontend')
        assert resp.status_code == 200
        assert b'so_frontend_aqui' in resp.data
        assert b'so_backend_aqui' not in resp.data


class TestApiReportarCrash:
    def test_aceita_relato_sem_login(self, client, app):
        """Um travamento pode acontecer antes do login (ex: na própria
        tela de login) -- a rota não pode exigir sessão."""
        resp = client.post('/admin/crash-logs/api/reportar', data={
            'tipo': 'js_error',
            'mensagem': 'travou sem estar logado',
            'url': '/auth/login',
        })
        assert resp.status_code == 204

        with app.app_context():
            salvo = CrashLog.query.filter_by(mensagem='travou sem estar logado').one()
            assert salvo.origem == 'frontend'
            assert salvo.usuario_id is None

    def test_associa_usuario_logado(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('crashlogs_reportante')
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        client.post('/admin/crash-logs/api/reportar', data={
            'tipo': 'ui_travada',
            'mensagem': 'UI travada por 9000ms',
        })

        with app.app_context():
            salvo = CrashLog.query.filter_by(mensagem='UI travada por 9000ms').one()
            assert salvo.usuario_id == aluno_ref.id

    def test_sem_mensagem_nao_grava_mas_nao_quebra(self, client, app):
        resp = client.post('/admin/crash-logs/api/reportar', data={'tipo': 'js_error'})
        assert resp.status_code == 204

        with app.app_context():
            assert CrashLog.query.count() == 0
