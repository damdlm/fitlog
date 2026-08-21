"""Testes de integração para routes/billing_routes.py e para o gating
de acesso premium aplicado em Estatísticas/FitBot
(utils/decorators.py:aluno_premium_required)."""
from datetime import datetime, timedelta, timezone

from models import db, User, Assinatura, EventoWebhookAsaas, Plano
from services.billing_service import BillingService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo_usuario)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


# ---------------------------------------------------------------------
# Webhook /billing/webhook/asaas
# ---------------------------------------------------------------------

class TestWebhookAsaas:
    def test_sem_token_e_rejeitado(self, client, app):
        with app.app_context():
            app.config['ASAAS_WEBHOOK_TOKEN'] = 'segredo-configurado'

        resp = client.post('/billing/webhook/asaas', json={'id': 'evt_1', 'event': 'PAYMENT_CONFIRMED'})
        assert resp.status_code == 401

    def test_token_errado_e_rejeitado(self, client, app):
        with app.app_context():
            app.config['ASAAS_WEBHOOK_TOKEN'] = 'segredo-configurado'

        resp = client.post(
            '/billing/webhook/asaas',
            json={'id': 'evt_1', 'event': 'PAYMENT_CONFIRMED'},
            headers={'asaas-access-token': 'token-errado'},
        )
        assert resp.status_code == 401

    def test_token_correto_e_aceito_e_ativa_assinatura(self, client, app):
        with app.app_context():
            app.config['ASAAS_WEBHOOK_TOKEN'] = 'segredo-configurado'
            aluno = _criar_usuario('webhook_http_1')
            assinatura = Assinatura(usuario_id=aluno.id, status='trialing', gateway_subscription_id='sub_abc')
            db.session.add(assinatura)
            db.session.commit()

        resp = client.post(
            '/billing/webhook/asaas',
            json={'id': 'evt_http_1', 'event': 'PAYMENT_CONFIRMED', 'payment': {'subscription': 'sub_abc'}},
            headers={'asaas-access-token': 'segredo-configurado'},
        )
        assert resp.status_code == 200

        with app.app_context():
            assinatura = Assinatura.query.filter_by(gateway_subscription_id='sub_abc').first()
            assert assinatura.status == 'active'

    def test_nao_exige_login_nem_csrf(self, client, app):
        """O webhook é chamado pelo servidor do Asaas, não pelo navegador
        de um usuário logado -- não pode exigir sessão nem CSRF token."""
        with app.app_context():
            app.config['ASAAS_WEBHOOK_TOKEN'] = 'segredo-configurado'

        resp = client.post(
            '/billing/webhook/asaas',
            json={'id': 'evt_sem_login', 'event': 'PAYMENT_CONFIRMED', 'payment': {}},
            headers={'asaas-access-token': 'segredo-configurado'},
        )
        assert resp.status_code == 200

    def test_evento_reenviado_nao_e_processado_duas_vezes(self, client, app):
        with app.app_context():
            app.config['ASAAS_WEBHOOK_TOKEN'] = 'segredo-configurado'

        payload = {'id': 'evt_duplicado', 'event': 'PAYMENT_CONFIRMED', 'payment': {}}
        headers = {'asaas-access-token': 'segredo-configurado'}

        client.post('/billing/webhook/asaas', json=payload, headers=headers)
        client.post('/billing/webhook/asaas', json=payload, headers=headers)

        with app.app_context():
            assert EventoWebhookAsaas.query.filter_by(event_id='evt_duplicado').count() == 1


# ---------------------------------------------------------------------
# GET /billing/minha-assinatura (tela HTML)
# ---------------------------------------------------------------------

class TestMinhaAssinaturaTela:
    def test_exige_login(self, client):
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code in (302, 401)

    def test_aluno_em_trial_ve_tela(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('minha_assinatura_trial_html')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 200
        assert b'text/html' in resp.headers.get('Content-Type', '').encode()

    def test_professor_ve_tela(self, client, app):
        with app.app_context():
            professor = _criar_usuario('minha_assinatura_prof_html', tipo_usuario='professor')
            db.session.commit()
            professor_id = professor.id
            professor_ref = User.query.get(professor_id)

        _login(client, professor_ref)
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 200

    def test_formulario_de_assinar_inclui_csrf_token(self, client, app):
        """Regressão: os <form> desta tela precisam do campo hidden
        csrf_token -- a suíte roda com WTF_CSRF_ENABLED=False (ver
        tests/conftest.py), então um POST via client.post() direto NÃO
        pega a falta desse campo; só olhar o HTML renderizado pega."""
        with app.app_context():
            db.session.add(Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599))
            aluno = _criar_usuario('minha_assinatura_csrf_html')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 200
        assert b'name="csrf_token"' in resp.data


# ---------------------------------------------------------------------
# GET /billing/api/minha-assinatura (JSON)
# ---------------------------------------------------------------------

class TestApiMinhaAssinatura:
    def test_exige_login(self, client):
        resp = client.get('/billing/api/minha-assinatura')
        assert resp.status_code in (302, 401)

    def test_aluno_em_trial_ve_status_trialing(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('minha_assinatura_trial')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/billing/api/minha-assinatura')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['status'] == 'trialing'
        assert data['acesso_premium'] is True

    def test_professor_ve_tier_gratuito_sem_alunos(self, client, app):
        with app.app_context():
            professor = _criar_usuario('minha_assinatura_prof', tipo_usuario='professor')
            db.session.commit()
            professor_id = professor.id
            professor_ref = User.query.get(professor_id)

        _login(client, professor_ref)
        resp = client.get('/billing/api/minha-assinatura')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier_atual'] == 'gratuito'


# ---------------------------------------------------------------------
# POST /billing/assinar
# ---------------------------------------------------------------------

class TestAssinar:
    def test_exige_login(self, client):
        resp = client.post('/billing/assinar')
        assert resp.status_code in (302, 401)

    def test_professor_na_faixa_gratuita_nao_chama_gateway(self, client, app, monkeypatch):
        chamou = {'valor': False}

        def _fake_checkout(*a, **k):
            chamou['valor'] = True
            return 'https://sandbox.asaas.com/i/fake'

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_checkout))

        with app.app_context():
            professor = _criar_usuario('assinar_prof_gratuito', tipo_usuario='professor')
            db.session.commit()
            professor_id = professor.id
            professor_ref = User.query.get(professor_id)

        _login(client, professor_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')
        assert chamou['valor'] is False

    def test_aluno_redireciona_para_checkout_gerado(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake-checkout'),
        )

        with app.app_context():
            db.session.add(Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599))
            aluno = _criar_usuario('assinar_aluno_ok')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake-checkout'

    def test_falha_no_gateway_nao_quebra_a_pagina(self, client, app, monkeypatch):
        import requests

        def _fake_falha(*a, **k):
            raise requests.RequestException('timeout simulado')

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_falha))

        with app.app_context():
            db.session.add(Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599))
            aluno = _criar_usuario('assinar_aluno_falha')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')


# ---------------------------------------------------------------------
# Gating de Estatísticas / FitBot (aluno_premium_required)
# ---------------------------------------------------------------------

class TestGatingAcessoPremium:
    def test_aluno_sem_assinatura_e_bloqueado_em_estatisticas(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('sem_trial_estatisticas')
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

    def test_aluno_em_trial_acessa_estatisticas(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('com_trial_estatisticas')
            BillingService.iniciar_trial_aluno(aluno)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200

    def test_professor_nunca_e_bloqueado_em_estatisticas(self, client, app):
        with app.app_context():
            professor = _criar_usuario('prof_sem_billing_estatisticas', tipo_usuario='professor')
            db.session.commit()
            professor_id = professor.id
            professor_ref = User.query.get(professor_id)

        _login(client, professor_ref)
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200

    def test_aluno_bloqueado_recebe_json_em_rota_de_api(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('sem_trial_api')
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/api/progresso')
        assert resp.status_code == 403
        assert resp.get_json()['erro'] == 'assinatura_necessaria'

    def test_aluno_trial_expirado_e_bloqueado(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('trial_expirado_estatisticas')
            assinatura = BillingService.iniciar_trial_aluno(aluno)
            assinatura.trial_termina_em = datetime.now(timezone.utc) - timedelta(days=1)
            db.session.commit()
            aluno_id = aluno.id
            aluno_ref = User.query.get(aluno_id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas', follow_redirects=False)
        assert resp.status_code == 302