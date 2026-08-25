"""Testes de integração para routes/billing_routes.py e para o gating
de acesso premium aplicado em Estatísticas/FitBot
(utils/decorators.py:acesso_premium_required)."""
from datetime import datetime, timedelta, timezone

import requests

from models import db, User, AlunoProfessor, Assinatura, EventoWebhookAsaas, Plano
from services.billing_service import BillingService, CpfCnpjNecessarioError


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo_usuario)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _preencher_dados_cobranca(usuario, cpf_cnpj='12345678900'):
    """Preenche os 4 campos que o Asaas exige pra checkout de cartão
    recorrente -- usado nos testes que só querem testar o fluxo de
    /billing/assinar em si, sem estarem testando a validação desses
    campos (essa fica em TestDadosCobrancaObrigatorios)."""
    usuario.cpf_cnpj = cpf_cnpj
    usuario.telefone = '11987654321'
    usuario.endereco_cep = '01310100'
    usuario.endereco_numero = '100'
    return usuario


def _criar_planos():
    db.session.add(Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599))
    db.session.add(Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
                          preco_centavos=2990, min_alunos=3, max_alunos=9))
    db.session.add(Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor',
                          preco_centavos=9990, min_alunos=10, max_alunos=None))


def _vincular_alunos(professor, quantidade):
    for i in range(quantidade):
        aluno = _criar_usuario(f'{professor.username}_aluno_{i}')
        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))


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
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 200
        assert b'text/html' in resp.headers.get('Content-Type', '').encode()

    def test_professor_ve_tela(self, client, app):
        with app.app_context():
            professor = _criar_usuario('minha_assinatura_prof_html', tipo_usuario='professor')
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 200

    def test_formulario_de_assinar_inclui_csrf_token(self, client, app):
        """Regressão: o <form> desta tela precisa do campo hidden
        csrf_token -- a suíte roda com WTF_CSRF_ENABLED=False (ver
        tests/conftest.py), então um POST via client.post() direto NÃO
        pega a falta desse campo; só olhar o HTML renderizado pega."""
        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('minha_assinatura_csrf_html')
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

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
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/billing/api/minha-assinatura')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['status'] == 'trialing'
        assert data['acesso_premium'] is True

    def test_professor_sem_alunos_nao_precisa_de_plano_gestao(self, client, app):
        with app.app_context():
            professor = _criar_usuario('minha_assinatura_prof', tipo_usuario='professor')
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.get('/billing/api/minha-assinatura')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['plano_gestao_necessario'] is None


# ---------------------------------------------------------------------
# POST /billing/assinar
# ---------------------------------------------------------------------

class TestAssinar:
    def test_exige_login(self, client):
        resp = client.post('/billing/assinar')
        assert resp.status_code in (302, 401)

    def test_professor_sem_alunos_e_oferecido_plano_fit(self, client, app, monkeypatch):
        """Até 2 alunos, o único plano relevante pro professor é o
        Fit (Estatísticas/FitBot) -- não existe mais um botão
        separado de "gestão"."""
        capturado = {}

        def _fake_checkout(usuario, plano):
            capturado['plano_codigo'] = plano.codigo
            return 'https://sandbox.asaas.com/i/fake'

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_checkout))

        with app.app_context():
            _criar_planos()
            professor = _criar_usuario('assinar_prof_sem_alunos', tipo_usuario='professor')
            _preencher_dados_cobranca(professor)
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake'
        assert capturado['plano_codigo'] == 'aluno_fit'

    def test_professor_com_5_alunos_e_oferecido_plano_pro(self, client, app, monkeypatch):
        capturado = {}

        def _fake_checkout(usuario, plano):
            capturado['plano_codigo'] = plano.codigo
            return 'https://sandbox.asaas.com/i/fake-pro'

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_checkout))

        with app.app_context():
            _criar_planos()
            professor = _criar_usuario('assinar_prof_5_alunos', tipo_usuario='professor')
            _vincular_alunos(professor, 5)
            _preencher_dados_cobranca(professor)
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert capturado['plano_codigo'] == 'professor_pro'

    def test_aluno_redireciona_para_checkout_gerado(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake-checkout'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_aluno_ok')
            _preencher_dados_cobranca(aluno)
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake-checkout'

    def test_falha_no_gateway_nao_quebra_a_pagina(self, client, app, monkeypatch):

        def _fake_falha(*a, **k):
            raise requests.RequestException('timeout simulado')

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_falha))

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_aluno_falha')
            _preencher_dados_cobranca(aluno)
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')


# ---------------------------------------------------------------------
# Dados de cobrança obrigatórios (exigência do Asaas pra gerar qualquer cobrança)
# ---------------------------------------------------------------------

class TestDadosCobrancaObrigatorios:
    def test_sem_nenhum_dado_no_form_nao_chama_o_gateway(self, client, app, monkeypatch):
        chamou = {'valor': False}

        def _fake_checkout(*a, **k):
            chamou['valor'] = True
            return 'https://sandbox.asaas.com/i/nao-deveria-chegar-aqui'

        monkeypatch.setattr(BillingService, 'criar_assinatura_checkout', staticmethod(_fake_checkout))

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_sem_dados')
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')
        assert chamou['valor'] is False

    def test_cpf_cnpj_com_formato_invalido_e_rejeitado(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_cpf_invalido')
            aluno.telefone = '11987654321'
            aluno.endereco_cep = '01310100'
            aluno.endereco_numero = '100'
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', data={'cpf_cnpj': '123'}, follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

        with app.app_context():
            aluno_ref = User.query.get(aluno_ref.id)
            assert aluno_ref.cpf_cnpj is None

    def test_cep_com_formato_invalido_e_rejeitado(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_cep_invalido')
            aluno.cpf_cnpj = '12345678900'
            aluno.telefone = '11987654321'
            aluno.endereco_numero = '100'
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', data={'endereco_cep': 'não é um cep'}, follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

        with app.app_context():
            aluno_ref = User.query.get(aluno_ref.id)
            assert aluno_ref.endereco_cep is None

    def test_todos_os_dados_no_form_sao_limpos_salvos_e_prosseguem_pro_checkout(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake-com-dados'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_dados_completos')
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        # Com pontuação de propósito -- o backend deve limpar antes de salvar.
        resp = client.post('/billing/assinar', data={
            'cpf_cnpj': '123.456.789-00',
            'telefone': '(11) 98765-4321',
            'endereco_cep': '01310-100',
            'endereco_numero': '100',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake-com-dados'

        with app.app_context():
            aluno_ref = User.query.get(aluno_ref.id)
            assert aluno_ref.cpf_cnpj == '12345678900'
            assert aluno_ref.telefone == '11987654321'
            assert aluno_ref.endereco_cep == '01310100'
            assert aluno_ref.endereco_numero == '100'

    def test_falta_so_o_endereco_pede_so_o_que_falta(self, client, app, monkeypatch):
        """Quem já tem CPF/telefone salvos (ex: preencheu o perfil
        antes) só precisa completar o que falta -- não reenvia tudo."""
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake-so-endereco'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_so_falta_endereco')
            aluno.cpf_cnpj = '12345678900'
            aluno.telefone = '11987654321'
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', data={
            'endereco_cep': '01310100',
            'endereco_numero': '100',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake-so-endereco'

    def test_usuario_que_ja_tem_tudo_nao_precisa_reenviar_nada(self, client, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'criar_assinatura_checkout',
            staticmethod(lambda usuario, plano: 'https://sandbox.asaas.com/i/fake-ja-tinha-tudo'),
        )

        with app.app_context():
            _criar_planos()
            aluno = _criar_usuario('assinar_ja_tem_tudo')
            _preencher_dados_cobranca(aluno, cpf_cnpj='11144477735')
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.post('/billing/assinar', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get('Location') == 'https://sandbox.asaas.com/i/fake-ja-tinha-tudo'


# ---------------------------------------------------------------------
# Gating de Estatísticas / FitBot (acesso_premium_required)
# ---------------------------------------------------------------------

class TestGatingAcessoPremium:
    def test_aluno_sem_assinatura_e_bloqueado_em_estatisticas(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('sem_trial_estatisticas')
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

    def test_aluno_em_trial_acessa_estatisticas(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('com_trial_estatisticas')
            BillingService.iniciar_trial(aluno)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200

    def test_professor_sem_trial_e_bloqueado_em_estatisticas(self, client, app):
        """Regressão: professor agora é gateado pelo Plano Fit igual
        ao aluno -- antes era isento por completo."""
        with app.app_context():
            professor = _criar_usuario('prof_sem_billing_estatisticas', tipo_usuario='professor')
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.get('/estatisticas/estatisticas', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

    def test_professor_com_trial_acessa_estatisticas(self, client, app):
        with app.app_context():
            professor = _criar_usuario('prof_com_trial_estatisticas', tipo_usuario='professor')
            BillingService.iniciar_trial(professor)
            db.session.commit()
            professor_ref = User.query.get(professor.id)

        _login(client, professor_ref)
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200

    def test_aluno_bloqueado_recebe_json_em_rota_de_api(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('sem_trial_api')
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/api/progresso')
        assert resp.status_code == 403
        assert resp.get_json()['erro'] == 'assinatura_necessaria'

    def test_aluno_trial_expirado_e_bloqueado(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('trial_expirado_estatisticas')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.trial_termina_em = datetime.now(timezone.utc) - timedelta(days=1)
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/estatisticas/estatisticas', follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------
# Gating de acesso aos alunos (professor_acesso_alunos_required)
# ---------------------------------------------------------------------

class TestGatingAcessoAosAlunos:
    def test_professor_pro_blocked_e_bloqueado_ao_ver_aluno(self, client, app):
        with app.app_context():
            _criar_planos()
            professor = _criar_usuario('prof_bloqueado_ve_aluno', tipo_usuario='professor')
            _vincular_alunos(professor, 5)
            pro = Plano.query.filter_by(codigo='professor_pro').first()
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'blocked'
            assinatura.plano_id = pro.id
            db.session.commit()
            professor_ref = User.query.get(professor.id)
            aluno_id = AlunoProfessor.query.filter_by(professor_id=professor.id).first().aluno_id

        _login(client, professor_ref)
        resp = client.get(f'/professor/aluno/{aluno_id}', follow_redirects=False)
        assert resp.status_code == 302
        assert '/billing/minha-assinatura' in resp.headers.get('Location', '')

    def test_professor_ate_2_alunos_nunca_e_bloqueado(self, client, app):
        with app.app_context():
            _criar_planos()
            professor = _criar_usuario('prof_2alunos_sempre_ve', tipo_usuario='professor')
            _vincular_alunos(professor, 2)
            db.session.commit()
            professor_ref = User.query.get(professor.id)
            aluno_id = AlunoProfessor.query.filter_by(professor_id=professor.id).first().aluno_id

        _login(client, professor_ref)
        resp = client.get(f'/professor/aluno/{aluno_id}')
        assert resp.status_code == 200
