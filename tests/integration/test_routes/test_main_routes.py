"""
Testes de regressão para routes/main_routes.py -- '/' passou a ramificar
entre landing page pública (visitante) e dashboard (usuário autenticado),
sem @login_required. Ver routes/main_routes.py para o motivo de não ter
virado uma rota nova (/dashboard).
"""
from models import db, User


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestRaizPublicaEDashboard:
    def test_raiz_sem_login_mostra_landing_publica(self, client):
        resp = client.get('/')

        assert resp.status_code == 200
        assert b'landing-hero' in resp.data
        # CTAs de login/cadastro precisam existir para quem chega sem conta
        assert b'/auth/register' in resp.data
        assert b'/auth/login' in resp.data

    def test_raiz_com_login_mostra_dashboard_normal(self, client, app):
        with app.app_context():
            _criar_usuario('main_route_user')
        _login(client, 'main_route_user')

        resp = client.get('/')

        assert resp.status_code == 200
        assert b'landing-hero' not in resp.data

    def test_landing_nao_expoe_link_para_rota_privada_de_contato(self, client):
        # routes/contato_routes.py ainda exige @login_required -- enquanto
        # isso não mudar, a landing não deve linkar pra lá (rota pública
        # linkando para endpoint autenticado só gera redirect pro login).
        resp = client.get('/')

        assert b'/contato/' not in resp.data

    def test_landing_esconde_login_registrar_do_cabecalho(self, client):
        # A landing já tem CTAs próprias (hero + seção final) -- os
        # botões de Login/Registrar do cabeçalho padrão (base.html)
        # ficavam redundantes aqui, então landing.html esconde esse
        # bloco (ver templates/landing.html: header_guest_actions).
        resp = client.get('/')

        assert b'btn-outline-secondary btn-sm' not in resp.data
        assert b'Come\xc3\xa7ar agora' in resp.data  # CTA do hero continua


class TestSeoBasico:
    """SEO base (Fase 3/7): title/description/canonical/Open Graph no
    <head>, herdados de templates/base.html por qualquer página que o
    estenda -- aqui só valida que os blocos realmente renderizam algo
    coerente, não o conteúdo palavra por palavra."""

    def test_landing_tem_title_description_canonical_e_og(self, client):
        resp = client.get('/')
        html = resp.data.decode('utf-8')

        assert '<title>FitLog — Registre seus treinos' in html
        assert 'content="Organize sua rotina de treinos' in html
        assert 'rel="canonical" href="http://localhost/"' in html
        assert 'property="og:title" content="FitLog — Registre seus treinos' in html
        assert 'property="og:image" content="http://localhost/static/images/og-fitlog.jpg"' in html
        assert 'name="twitter:card" content="summary_large_image"' in html

    def test_canonical_usa_app_base_url_quando_configurada(self, client, app):
        app.config['APP_BASE_URL'] = 'https://fitlog.exemplo.com'

        resp = client.get('/')

        assert b'rel="canonical" href="https://fitlog.exemplo.com/"' in resp.data
        assert b'property="og:image" content="https://fitlog.exemplo.com/static/images/og-fitlog.jpg"' in resp.data

    def test_pagina_sem_override_usa_title_padrao_do_base(self, client):
        # O dashboard (index.html) não sobrescreve title/description --
        # deve herdar o default de base.html em vez de ficar sem
        # <title> nenhum.
        _criar_usuario('seo_fallback_title')
        _login(client, 'seo_fallback_title')

        resp = client.get('/')

        assert b'<title>FitLog \xe2\x80\x94 Seu treino, sempre com voc\xc3\xaa</title>' in resp.data

    def test_politica_e_termos_tem_title_proprio(self, client):
        assert b'<title>Pol\xc3\xadtica de Privacidade \xe2\x80\x94 FitLog</title>' in client.get('/privacidade/').data
        assert b'<title>Termos de Uso \xe2\x80\x94 FitLog</title>' in client.get('/privacidade/termos').data