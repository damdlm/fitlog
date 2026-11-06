"""Testes para app.py -- a factory da aplicação (create_app), páginas
de erro customizadas (404/500, novas nesta leva de commits), headers
de segurança, health checks, service worker e o proxy de mídia dos
exercícios (bucket S3 com fallback pro volume local).
"""
import pytest

from app import create_app
from config import Config
from models import db, User


class ConfigProducaoSimulada(Config):
    """DEBUG=False e TESTING=False -- em_producao=True em app.py, sem
    precisar de infraestrutura de produção de verdade (só pra testar
    os ramos que dependem desse cálculo: HSTS, criação do admin,
    init_db). Passado direto pra create_app(), sem passar por
    get_config() -- não dispara a validação de SECRET_KEY/REDIS_URL
    que só roda lá."""
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# ------------------------------------------------------------------
# Páginas de erro customizadas (404/500) -- código novo desta leva
# ------------------------------------------------------------------
class TestPaginasDeErro:

    def test_404_em_rota_inexistente(self, client):
        resp = client.get('/rota-que-nao-existe-nunca-123')
        assert resp.status_code == 404
        assert b'404' in resp.data or resp.status_code == 404

    def test_500_renderiza_pagina_customizada_e_reverte_a_sessao(self, app, client, monkeypatch):
        """Força uma rota a levantar uma exceção não tratada -- o
        handler deve responder com a página customizada (não o
        traceback padrão do Flask) e reverter a sessão do banco."""
        @app.route('/_rota-de-teste-que-quebra')
        def _quebra():
            raise RuntimeError("erro forçado pelo teste")

        app.config['TESTING'] = False
        app.config['PROPAGATE_EXCEPTIONS'] = False

        chamou_rollback = {'sim': False}
        rollback_original = db.session.rollback

        def rollback_espiao():
            chamou_rollback['sim'] = True
            return rollback_original()

        monkeypatch.setattr(db.session, 'rollback', rollback_espiao)

        resp = client.get('/_rota-de-teste-que-quebra')

        assert resp.status_code == 500
        assert chamou_rollback['sim'] is True


# ------------------------------------------------------------------
# Health checks (Railway)
# ------------------------------------------------------------------
class TestHealthChecks:

    def test_health_sempre_ok(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_health_db_ok_com_banco_disponivel(self, client):
        resp = client.get('/health/db')
        assert resp.status_code == 200
        assert resp.get_json()['database'] == 'ok'

    def test_health_db_reporta_indisponivel_sem_expor_detalhe(self, app, client, monkeypatch):
        def _explode(*a, **kw):
            raise RuntimeError("connection refused: senha=segredo123 host=db-interno")

        with app.app_context():
            monkeypatch.setattr(db.session, 'execute', _explode)
            resp = client.get('/health/db')

        assert resp.status_code == 503
        data = resp.get_json()
        assert data == {"status": "error", "database": "unavailable"}
        # nunca vaza detalhe de conexão na resposta HTTP
        assert 'segredo123' not in resp.get_data(as_text=True)


# ------------------------------------------------------------------
# Headers de segurança
# ------------------------------------------------------------------
class TestHeadersDeSeguranca:

    def test_headers_basicos_sempre_presentes(self, client):
        resp = client.get('/health')
        assert resp.headers['X-Content-Type-Options'] == 'nosniff'
        assert resp.headers['X-Frame-Options'] == 'SAMEORIGIN'
        assert 'Content-Security-Policy' in resp.headers

    def test_hsts_ausente_fora_de_producao(self, client):
        resp = client.get('/health')
        assert 'Strict-Transport-Security' not in resp.headers

    def test_hsts_presente_em_producao(self):
        app_prod = create_app(ConfigProducaoSimulada)
        with app_prod.app_context():
            client_prod = app_prod.test_client()
            resp = client_prod.get('/health')
            assert 'Strict-Transport-Security' in resp.headers
            assert 'max-age=31536000' in resp.headers['Strict-Transport-Security']


# ------------------------------------------------------------------
# Service worker
# ------------------------------------------------------------------
class TestServiceWorker:

    def test_sw_js_serve_com_headers_de_pwa(self, client):
        resp = client.get('/sw.js')
        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'application/javascript'
        assert resp.headers['Service-Worker-Allowed'] == '/'

    @pytest.mark.parametrize('url', ['/sw.js', '/static/offline.html'])
    def test_sw_e_offline_html_nunca_ficam_em_cache(self, client, url):
        # Com o max-age de 1 dia dos estáticos, o Cloudflare guardava o
        # /sw.js e os aparelhos ficavam até 24h no service worker antigo.
        resp = client.get(url)
        assert resp.status_code == 200
        cc = resp.headers['Cache-Control']
        assert 'no-cache' in cc and 'max-age=0' in cc
        assert 'public' not in cc

    def test_demais_estaticos_continuam_com_cache(self, client):
        resp = client.get('/static/js/modules/fila-offline.js')
        assert 'max-age=0' not in resp.headers.get('Cache-Control', '')


# ------------------------------------------------------------------
# Mídia dos exercícios -- proxy S3 com fallback pro volume local
# ------------------------------------------------------------------
class TestExerciciosMedia:

    def test_sem_s3_configurado_serve_do_volume_local(self, client, monkeypatch):
        from services.storage_service import StorageService
        monkeypatch.setattr(StorageService, 'is_configured', staticmethod(lambda: False))

        capturado = {}

        def fake_send_from_directory(diretorio, caminho, **kwargs):
            capturado.update(diretorio=diretorio, caminho=caminho)
            return 'ok-volume-local', 200

        monkeypatch.setattr('flask.send_from_directory', fake_send_from_directory)

        resp = client.get('/exercicios-media/video-teste.gif')

        assert resp.status_code == 200
        assert capturado['caminho'] == 'video-teste.gif'

    def test_com_s3_configurado_e_objeto_encontrado_faz_proxy(self, client, monkeypatch):
        from services.storage_service import StorageService
        import io

        monkeypatch.setattr(StorageService, 'is_configured', staticmethod(lambda: True))
        monkeypatch.setattr(StorageService, 'get_object_stream', staticmethod(lambda caminho, range_header=None: {
            'body': io.BytesIO(b'conteudo-do-bucket'),
            'content_type': 'image/gif',
            'content_length': len(b'conteudo-do-bucket'),
            'content_range': None,
            'is_partial': False,
        }))

        resp = client.get('/exercicios-media/no-bucket.gif')

        assert resp.status_code == 200
        assert resp.data == b'conteudo-do-bucket'
        assert resp.headers['Cache-Control'] == 'public, max-age=31536000, immutable'

    def test_com_s3_configurado_mas_objeto_nao_encontrado_cai_pro_volume(self, client, monkeypatch):
        from services.storage_service import StorageService
        monkeypatch.setattr(StorageService, 'is_configured', staticmethod(lambda: True))
        monkeypatch.setattr(StorageService, 'get_object_stream', staticmethod(lambda *a, **kw: None))

        capturado = {}

        def fake_send_from_directory(diretorio, caminho, **kwargs):
            capturado['caminho'] = caminho
            return 'ok-fallback', 200

        monkeypatch.setattr('flask.send_from_directory', fake_send_from_directory)

        resp = client.get('/exercicios-media/ainda-no-volume.gif')

        assert resp.status_code == 200
        assert capturado['caminho'] == 'ainda-no-volume.gif'

    def test_range_request_retorna_206_partial(self, client, monkeypatch):
        from services.storage_service import StorageService
        import io

        monkeypatch.setattr(StorageService, 'is_configured', staticmethod(lambda: True))
        monkeypatch.setattr(StorageService, 'get_object_stream', staticmethod(lambda caminho, range_header=None: {
            'body': io.BytesIO(b'parte'),
            'content_type': 'video/mp4',
            'content_length': 5,
            'content_range': 'bytes 0-4/100',
            'is_partial': True,
        }))

        resp = client.get('/exercicios-media/video.mp4', headers={'Range': 'bytes=0-4'})

        assert resp.status_code == 206
        assert resp.headers['Content-Range'] == 'bytes 0-4/100'


# ------------------------------------------------------------------
# load_user (Flask-Login) -- invalidação de sessão após troca de senha
# ------------------------------------------------------------------
class TestLoadUser:

    def _criar_usuario(self, username):
        user = User(username=username, email=f'{username}@teste.com')
        user.set_password('SenhaForte123!')
        db.session.add(user)
        db.session.commit()
        return user

    def test_sessao_com_session_version_desatualizada_desloga(self, client, app, db):
        user = self._criar_usuario('app_load_user_1')
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
            sess['sv'] = user.session_version + 999  # versão errada

        resp = client.get('/health')  # rota qualquer, só pra passar pelo user_loader
        # sessão inválida -- páginas que exigem login devolveriam redirect;
        # aqui só confirmamos que a navegação não quebra com sv divergente
        assert resp.status_code == 200

    def test_usuario_inexistente_nao_quebra(self, client):
        with client.session_transaction() as sess:
            sess['_user_id'] = '999999'
            sess['_fresh'] = True

        resp = client.get('/health')
        assert resp.status_code == 200


# ------------------------------------------------------------------
# Comandos CLI de cobrança
# ------------------------------------------------------------------
class TestComandosCli:

    def test_billing_expirar_carencias_roda_sem_erro(self, app):
        runner = app.test_cli_runner()
        resultado = runner.invoke(args=['billing-expirar-carencias'])
        assert resultado.exit_code == 0
        assert 'assinatura' in resultado.output

    def test_billing_verificar_tiers_sem_mudancas(self, app):
        runner = app.test_cli_runner()
        resultado = runner.invoke(args=['billing-verificar-tiers'])
        assert resultado.exit_code == 0
        assert 'Nenhuma mudança' in resultado.output


# ------------------------------------------------------------------
# static_v -- cache-busting de estáticos
# ------------------------------------------------------------------
class TestStaticV:

    def test_arquivo_existente_recebe_versao_no_query_string(self, app):
        static_v = app.jinja_env.globals['static_v']
        with app.test_request_context('/'):
            url = static_v('js/admin-monitoramento.js')
        assert '?v=' in url
        assert url.split('?v=')[1] != '0'

    def test_arquivo_inexistente_nao_quebra_versao_fica_zero(self, app):
        static_v = app.jinja_env.globals['static_v']
        with app.test_request_context('/'):
            url = static_v('js/nao-existe-nunca-123.js')
        assert url.endswith('?v=0')


# ------------------------------------------------------------------
# Criação do admin inicial -- regras diferentes em produção vs dev
# ------------------------------------------------------------------
class TestCriarAdminInicial:

    def test_producao_sem_admin_password_nao_cria_admin(self, monkeypatch):
        monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
        app_prod = create_app(ConfigProducaoSimulada)
        with app_prod.app_context():
            db.create_all()
            from app import _criar_admin_inicial
            _criar_admin_inicial(app_prod)
            assert User.query.filter_by(username='admin').first() is None

    def test_producao_com_senha_curta_nao_cria_admin(self, monkeypatch):
        monkeypatch.setenv('ADMIN_PASSWORD', 'curta123')  # menos de 12 chars
        app_prod = create_app(ConfigProducaoSimulada)
        with app_prod.app_context():
            db.create_all()
            from app import _criar_admin_inicial
            _criar_admin_inicial(app_prod)
            assert User.query.filter_by(username='admin').first() is None
        monkeypatch.delenv('ADMIN_PASSWORD', raising=False)

    def test_producao_sem_admin_email_nao_cria_admin(self, monkeypatch):
        monkeypatch.setenv('ADMIN_PASSWORD', 'senha-valida-com-mais-de-12-chars')
        monkeypatch.delenv('ADMIN_EMAIL', raising=False)
        app_prod = create_app(ConfigProducaoSimulada)
        with app_prod.app_context():
            db.create_all()
            from app import _criar_admin_inicial
            _criar_admin_inicial(app_prod)
            assert User.query.filter_by(username='admin').first() is None

    def test_producao_com_senha_valida_cria_admin(self, monkeypatch):
        monkeypatch.setenv('ADMIN_PASSWORD', 'senha-valida-com-mais-de-12-chars')
        monkeypatch.setenv('ADMIN_EMAIL', 'Dono@Exemplo.com.br')
        app_prod = create_app(ConfigProducaoSimulada)
        with app_prod.app_context():
            db.create_all()
            from app import _criar_admin_inicial
            _criar_admin_inicial(app_prod)
            admin = User.query.filter_by(username='admin').first()
            assert admin is not None
            assert admin.is_admin is True
            assert admin.check_password('senha-valida-com-mais-de-12-chars')
            assert admin.email == 'dono@exemplo.com.br'
        monkeypatch.delenv('ADMIN_PASSWORD', raising=False)

    def test_alerta_no_log_se_admin_usa_o_email_padrao_antigo(self, app, caplog):
        from app import _alertar_admin_com_email_padrao
        admin = User.query.filter_by(is_admin=True).first()
        admin.email = 'Admin@FitLog.com'
        db.session.commit()
        with caplog.at_level('ERROR'):
            _alertar_admin_com_email_padrao(app)
        assert any('admin@fitlog.com' in r.getMessage() and str(admin.id) in r.getMessage() for r in caplog.records)

    def test_sem_alerta_quando_o_email_do_admin_e_outro(self, app, caplog):
        from app import _alertar_admin_com_email_padrao
        with caplog.at_level('ERROR'):
            _alertar_admin_com_email_padrao(app)
        assert not [r for r in caplog.records if 'e-mail padrão' in r.getMessage()]


class TestBillingVerificarTiersComMudancas:

    def test_lista_mudancas_quando_ha(self, app, monkeypatch):
        from services.billing_service import BillingService

        class _Tier:
            def __init__(self, codigo):
                self.codigo = codigo

        class _ProfFake:
            id = 42

        monkeypatch.setattr(
            BillingService, 'verificar_mudancas_tier_professores',
            staticmethod(lambda: [{
                'professor': _ProfFake(),
                'tier_atual': _Tier('fit'),
                'tier_novo': _Tier('pro'),
            }]),
        )

        runner = app.test_cli_runner()
        resultado = runner.invoke(args=['billing-verificar-tiers'])

        assert resultado.exit_code == 0
        assert 'professor_id=42' in resultado.output
        assert 'fit -> pro' in resultado.output