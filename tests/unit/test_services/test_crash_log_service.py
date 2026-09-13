"""Testes para CrashLogService -- travamentos de frontend e backend
registrados para o painel /admin/crash-logs (ver models.CrashLog)."""
from datetime import datetime, timedelta, timezone

from models import db, CrashLog, User
from services.crash_log_service import CrashLogService


class TestRegistrarFrontend:

    def test_grava_travamento_de_frontend(self, app):
        with app.app_context():
            log = CrashLogService.registrar_frontend(
                tipo='js_error', mensagem='TypeError: x is not a function',
                detalhes='stack aqui', url='/aluno/dashboard', user_agent='TesteUA/1.0',
            )
            assert log is not None
            assert log.origem == 'frontend'

            salvo = CrashLog.query.one()
            assert salvo.tipo == 'js_error'
            assert salvo.mensagem == 'TypeError: x is not a function'
            assert salvo.url == '/aluno/dashboard'

    def test_tipo_desconhecido_cai_em_js_error(self, app):
        with app.app_context():
            CrashLogService.registrar_frontend(tipo='algo_novo_do_futuro', mensagem='erro qualquer')

            salvo = CrashLog.query.one()
            assert salvo.tipo == 'js_error'

    def test_mensagem_vazia_nao_quebra(self, app):
        with app.app_context():
            log = CrashLogService.registrar_frontend(tipo='js_error', mensagem='')
            assert log is not None
            assert log.mensagem == '(sem mensagem)'

    def test_associa_usuario_quando_informado(self, app):
        with app.app_context():
            user = User(username='crashlog_user', email='crashlog@teste.com')
            user.set_password('SenhaForte123!')
            db.session.add(user)
            db.session.commit()

            CrashLogService.registrar_frontend(tipo='js_error', mensagem='erro', usuario_id=user.id)

            salvo = CrashLog.query.one()
            assert salvo.usuario_id == user.id


class TestRegistrarBackend:

    def test_grava_travamento_de_backend(self, app):
        with app.app_context():
            log = CrashLogService.registrar_backend(
                tipo='ValueError', mensagem='algo quebrou', detalhes='Traceback...', url='/admin/contas',
            )
            assert log is not None
            assert log.origem == 'backend'

            salvo = CrashLog.query.one()
            assert salvo.tipo == 'ValueError'
            assert salvo.detalhes == 'Traceback...'


class TestListar:

    def test_filtra_por_origem(self, app):
        with app.app_context():
            CrashLogService.registrar_frontend(tipo='js_error', mensagem='erro front')
            CrashLogService.registrar_backend(tipo='ValueError', mensagem='erro back')

            pagina = CrashLogService.listar(origem='frontend')
            assert len(pagina.items) == 1
            assert pagina.items[0].origem == 'frontend'

    def test_sem_filtro_traz_os_dois(self, app):
        with app.app_context():
            CrashLogService.registrar_frontend(tipo='js_error', mensagem='erro front')
            CrashLogService.registrar_backend(tipo='ValueError', mensagem='erro back')

            pagina = CrashLogService.listar()
            assert len(pagina.items) == 2

    def test_mais_recente_primeiro(self, app):
        with app.app_context():
            agora = datetime.now(timezone.utc)
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='antigo', criado_em=agora - timedelta(hours=2)))
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='recente', criado_em=agora))
            db.session.commit()

            pagina = CrashLogService.listar()
            assert pagina.items[0].mensagem == 'recente'


class TestContarRecentes:

    def test_conta_apenas_dentro_da_janela(self, app):
        with app.app_context():
            agora = datetime.now(timezone.utc)
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='dentro', criado_em=agora - timedelta(hours=1)))
            db.session.add(CrashLog(origem='frontend', tipo='js_error', mensagem='fora', criado_em=agora - timedelta(hours=48)))
            db.session.commit()

            total = CrashLogService.contar_recentes(horas=24)
            assert total == 1


class TestLimparAntigas:

    def test_remove_apenas_fora_da_retencao(self, app):
        with app.app_context():
            agora = datetime.now(timezone.utc)
            db.session.add(CrashLog(origem='backend', tipo='ValueError', mensagem='antigo', criado_em=agora - timedelta(days=45)))
            db.session.add(CrashLog(origem='backend', tipo='ValueError', mensagem='recente', criado_em=agora - timedelta(days=1)))
            db.session.commit()

            total_removido = CrashLogService.limpar_antigas(dias_retencao=30)

        assert total_removido == 1
        with app.app_context():
            assert CrashLog.query.count() == 1
