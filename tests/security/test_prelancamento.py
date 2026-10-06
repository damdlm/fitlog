"""Testes das correções da auditoria pré-lançamento: rotas de mídia com
prefixo, webhook com reconsulta na API do Asaas, verificação de e-mail,
política de senha e bloqueio de conta no login."""
from unittest.mock import patch, MagicMock

import pytest
import requests

from models import db, User, Assinatura
from services.email_verificacao_service import EmailVerificacaoService


def _form_cadastro(**extra):
    dados = {
        'username': 'novo_aluno', 'email': 'novo@teste.com', 'password': 'Treino#Forte9',
        'confirm_password': 'Treino#Forte9', 'tipo_usuario': 'aluno', 'aceite_termos': 'on',
        'nome_completo': 'Novo Aluno',
    }
    dados.update(extra)
    return dados


def _criar_usuario(username='ana', senha='SenhaForte123!', verificado=True):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno', ativo=True)
    user.set_password(senha)
    if verificado:
        from datetime import datetime, timezone
        user.email_verificado_em = datetime.now(timezone.utc)
    db.session.add(user)
    db.session.commit()
    return user.id


# ---------------------------------------------------------------- mídia
class TestRotasDeMidia:
    def test_professores_media_so_serve_prefixo_professores(self, client):
        with patch('services.storage_service.StorageService.get_object_stream',
                   side_effect=AssertionError('não deveria tocar no bucket')):
            assert client.get('/professores-media/videos/0001-abc.gif').status_code == 404
            assert client.get('/professores-media/professores/../videos/x.gif').status_code == 404
            assert client.get('/professores-media/professores/a/b.jpg').status_code == 404

    def test_exercicios_media_nao_serve_fotos_de_professores(self, client):
        with patch('services.storage_service.StorageService.get_object_stream',
                   side_effect=AssertionError('não deveria tocar no bucket')):
            assert client.get('/exercicios-media/professores/1-123.jpg').status_code == 404
            assert client.get('/exercicios-media/videos/../professores/1-1.jpg').status_code == 404


# -------------------------------------------------------------- webhook
def _resposta_api(status_code=200, corpo=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = corpo or {}
    return r


class TestWebhookReconsultaApi:
    TOKEN = 'segredo-configurado'

    def _preparar(self, app):
        app.config['ASAAS_WEBHOOK_TOKEN'] = self.TOKEN
        app.config['ASAAS_API_KEY'] = 'chave-de-teste'
        uid = _criar_usuario('pagador')
        db.session.add(Assinatura(usuario_id=uid, status='trialing', gateway_subscription_id='sub_x',
                                  gateway_customer_id='cus_1'))
        db.session.commit()

    def _enviar(self, client, evt='evt_1'):
        return client.post(
            '/billing/webhook/asaas',
            json={'id': evt, 'event': 'PAYMENT_CONFIRMED',
                  'payment': {'id': 'pay_1', 'subscription': 'sub_x', 'customer': 'cus_1'}},
            headers={'asaas-access-token': self.TOKEN},
        )

    def _status(self):
        return Assinatura.query.filter_by(gateway_subscription_id='sub_x').first().status

    def test_pagamento_confirmado_na_api_ativa(self, client, app):
        with app.app_context():
            self._preparar(app)
            api = _resposta_api(200, {'status': 'RECEIVED', 'customer': 'cus_1', 'subscription': 'sub_x'})
            with patch('services.billing_service.requests.get', return_value=api):
                assert self._enviar(client).status_code == 200
            assert self._status() == 'active'

    def test_evento_forjado_pagamento_pendente_na_api_nao_ativa(self, client, app):
        with app.app_context():
            self._preparar(app)
            api = _resposta_api(200, {'status': 'PENDING', 'customer': 'cus_1', 'subscription': 'sub_x'})
            with patch('services.billing_service.requests.get', return_value=api):
                assert self._enviar(client).status_code == 200
            assert self._status() == 'trialing'

    def test_pagamento_inexistente_na_api_nao_ativa(self, client, app):
        with app.app_context():
            self._preparar(app)
            with patch('services.billing_service.requests.get', return_value=_resposta_api(404)):
                assert self._enviar(client).status_code == 200
            assert self._status() == 'trialing'

    def test_cliente_divergente_nao_ativa(self, client, app):
        with app.app_context():
            self._preparar(app)
            api = _resposta_api(200, {'status': 'CONFIRMED', 'customer': 'cus_OUTRO', 'subscription': 'sub_x'})
            with patch('services.billing_service.requests.get', return_value=api):
                assert self._enviar(client).status_code == 200
            assert self._status() == 'trialing'

    def test_api_fora_do_ar_devolve_503_para_o_asaas_reenviar(self, client, app):
        with app.app_context():
            self._preparar(app)
            with patch('services.billing_service.requests.get', side_effect=requests.ConnectionError('x')):
                assert self._enviar(client).status_code == 503
            assert self._status() == 'trialing'
            # o evento NÃO foi marcado como processado: o reenvio ainda é aceito
            api = _resposta_api(200, {'status': 'RECEIVED', 'customer': 'cus_1', 'subscription': 'sub_x'})
            with patch('services.billing_service.requests.get', return_value=api):
                assert self._enviar(client).status_code == 200
            assert self._status() == 'active'


# ------------------------------------------------- verificação de e-mail
class TestVerificacaoEmail:
    @pytest.fixture(autouse=True)
    def _ligar(self, app):
        app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = True

    def test_cadastro_envia_link_e_conta_nasce_nao_verificada(self, client, app):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            resp = client.post('/auth/register', data=_form_cadastro())
        assert resp.status_code == 302
        assert envio.call_count == 1
        assert '/auth/verificar-email/' in envio.call_args[0][2]
        with app.app_context():
            assert User.query.filter_by(username='novo_aluno').first().email_verificado_em is None

    def test_nao_verificado_e_barrado_ate_confirmar(self, client, app):
        with app.app_context():
            _criar_usuario('pendente', verificado=False)
        client.post('/auth/login', data={'username': 'pendente', 'password': 'SenhaForte123!'})
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 302 and '/auth/verificar-email' in resp.headers['Location']
        assert client.post('/aluno/cadastrar-treinos', data={}).status_code == 403
        assert client.get('/api/professores/mapa').status_code == 403
        assert client.get('/auth/verificar-email').status_code == 200

    def test_link_valido_verifica_e_libera(self, client, app):
        with app.app_context():
            uid = _criar_usuario('pendente2', verificado=False)
            token = EmailVerificacaoService.gerar_token(db.session.get(User, uid))
        assert client.get(f'/auth/verificar-email/{token}').status_code == 302
        with app.app_context():
            assert db.session.get(User, uid).email_verificado_em is not None
        client.post('/auth/login', data={'username': 'pendente2', 'password': 'SenhaForte123!'})
        assert client.get('/aluno/cadastrar-treinos').status_code == 200

    def test_link_adulterado_ou_expirado_e_recusado(self, client, app):
        with app.app_context():
            uid = _criar_usuario('pendente3', verificado=False)
            token = EmailVerificacaoService.gerar_token(db.session.get(User, uid))
        client.get(f'/auth/verificar-email/{token}x')
        with patch('services.email_verificacao_service.VALIDADE_SEGUNDOS', -1):
            client.get(f'/auth/verificar-email/{token}')
        with app.app_context():
            assert db.session.get(User, uid).email_verificado_em is None

    def test_link_antigo_nao_vale_se_o_email_mudou(self, client, app):
        with app.app_context():
            uid = _criar_usuario('pendente4', verificado=False)
            user = db.session.get(User, uid)
            token = EmailVerificacaoService.gerar_token(user)
            user.email = 'outro@teste.com'
            db.session.commit()
        client.get(f'/auth/verificar-email/{token}')
        with app.app_context():
            assert db.session.get(User, uid).email_verificado_em is None

    def test_reenvio_e_limitado_e_exige_login(self, client, app):
        assert client.post('/auth/reenviar-verificacao').status_code == 302  # -> login
        with app.app_context():
            _criar_usuario('pendente5', verificado=False)
        client.post('/auth/login', data={'username': 'pendente5', 'password': 'SenhaForte123!'})
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            for _ in range(5):
                client.post('/auth/reenviar-verificacao')
        assert envio.call_count == 3

    def test_flag_desligada_nao_barra(self, client, app):
        app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = False
        with app.app_context():
            _criar_usuario('livre', verificado=False)
        client.post('/auth/login', data={'username': 'livre', 'password': 'SenhaForte123!'})
        assert client.get('/aluno/cadastrar-treinos').status_code == 200


# ------------------------------------------------------ política de senha
class TestPoliticaDeSenha:
    @pytest.mark.parametrize('senha', ['Senha1234', 'senha123', 'aaaa1111', 'Qwerty123'])
    def test_senhas_comuns_sao_recusadas(self, senha):
        from utils.validators import validar_senha
        assert validar_senha(senha)[0] is False

    def test_senha_com_username_ou_email_e_recusada(self):
        from utils.validators import validar_senha
        assert validar_senha('carlos2026X', username='carlos')[0] is False
        assert validar_senha('maria.silva9', email='maria.silva@x.com')[0] is False

    def test_senha_boa_passa(self):
        from utils.validators import validar_senha
        assert validar_senha('Treino#Forte9', username='carlos', email='c@x.com')[0] is True

    def test_registro_recusa_senha_comum(self, client, app):
        resp = client.post('/auth/register', data=_form_cadastro(password='Senha1234', confirm_password='Senha1234'))
        assert resp.status_code == 302
        with app.app_context():
            assert User.query.filter_by(username='novo_aluno').first() is None


# ----------------------------------------------------- bloqueio no login
class TestBloqueioDeConta:
    def test_bloqueia_apos_tentativas_erradas_mesmo_com_senha_certa(self, client, app):
        with app.app_context():
            _criar_usuario('alvo')
        for _ in range(8):
            client.post('/auth/login', data={'username': 'alvo', 'password': 'errada123'})
        client.post('/auth/login', data={'username': 'alvo', 'password': 'SenhaForte123!'})
        assert client.get('/aluno/cadastrar-treinos').status_code == 302  # segue deslogado

    def test_sucesso_zera_o_contador(self, client, app):
        with app.app_context():
            _criar_usuario('alvo2')
        for _ in range(5):
            client.post('/auth/login', data={'username': 'alvo2', 'password': 'errada123'})
        client.post('/auth/login', data={'username': 'alvo2', 'password': 'SenhaForte123!'})
        with app.app_context():
            assert User.query.filter_by(username='alvo2').first().falhas_login == 0
