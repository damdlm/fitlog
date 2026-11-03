"""
Testes de BillingService._obter_ou_criar_cliente_asaas -- o passo que garante
que o usuário existe como "cliente" no Asaas antes de qualquer cobrança.

REGRESSÃO PRINCIPAL (virada sandbox -> produção): sandbox e produção do Asaas
são bases de clientes SEPARADAS. Quem tinha um `gateway_customer_id` gravado
em sandbox recebia 404 ao tentar atualizar esse cliente em produção, e o
checkout inteiro quebrava. A correção "self-healing" (404 no PUT -> recria
com POST e troca o id gravado) não tinha NENHUM teste.

Nenhum teste sai pra rede: requests.post/put são substituídos por fakes.
"""

import pytest
import requests

from models import db, User, Plano, Assinatura
from services.billing_service import BillingService, REQUEST_TIMEOUT_SECONDS


class _Resp:
    """Substitui requests.Response -- só o que o service usa."""

    def __init__(self, json_data=None, status_code=200):
        self._json = json_data or {}
        self.status_code = status_code
        self.text = str(self._json)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} erro simulado')

    def json(self):
        return self._json


class _FakeAsaas:
    """Registra as chamadas e devolve respostas programadas por (método, sufixo-da-URL)."""

    def __init__(self):
        self.chamadas = []
        self.put_resp = _Resp({'id': 'cus_existente'})
        self.post_customers_resp = _Resp({'id': 'cus_novo'})
        self.post_checkouts_resp = _Resp({'id': 'chk_1', 'link': 'https://asaas.test/chk_1'})

    def post(self, url, json=None, headers=None, timeout=None):
        self.chamadas.append({'m': 'POST', 'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        if url.endswith('/customers'):
            return self.post_customers_resp
        if url.endswith('/checkouts'):
            return self.post_checkouts_resp
        raise AssertionError(f'POST inesperado: {url}')

    def put(self, url, json=None, headers=None, timeout=None):
        self.chamadas.append({'m': 'PUT', 'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        return self.put_resp

    def metodos(self):
        return [c['m'] for c in self.chamadas]


@pytest.fixture
def asaas(app, monkeypatch):
    fake = _FakeAsaas()
    monkeypatch.setattr('services.billing_service.requests.post', fake.post)
    monkeypatch.setattr('services.billing_service.requests.put', fake.put)
    app.config['ASAAS_API_KEY'] = 'chave-de-teste'
    app.config['ASAAS_ENV'] = 'sandbox'
    app.config['APP_BASE_URL'] = 'https://fitlog.up.railway.app'
    return fake


@pytest.fixture
def usuario_com_assinatura(app):
    """Usuário com TODOS os dados de cobrança preenchidos + Assinatura em trial."""
    u = User(username='cliente1', email='cliente1@teste.com', tipo_usuario='aluno',
             nome_completo='Cliente Um')
    u.set_password('SenhaForte123!')
    u.cpf_cnpj = '12345678900'
    u.telefone = '(11) 98765-4321'
    u.endereco_cep = '01310100'
    u.endereco_numero = '100'
    db.session.add(u)
    db.session.flush()
    assinatura = BillingService.iniciar_trial(u)
    db.session.commit()
    return u, assinatura


def _id_gravado(assinatura_id):
    """Relê do banco (descarta o cache da sessão) -- prova que PERSISTIU."""
    db.session.expire_all()
    return db.session.get(Assinatura, assinatura_id).gateway_customer_id


# ------------------------------------------------------------------
# cliente ainda não existe no Asaas
# ------------------------------------------------------------------

class TestSemClienteGravado:

    def test_cria_cliente_e_grava_o_id_no_banco(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        assert assinatura.gateway_customer_id is None

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert customer_id == 'cus_novo'
        assert asaas.metodos() == ['POST']
        assert _id_gravado(assinatura.id) == 'cus_novo'

    def test_payload_do_cliente_tem_os_dados_de_cobranca_e_telefone_so_digitos(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.chamadas[0]['json'] == {
            'name': 'Cliente Um',
            'email': 'cliente1@teste.com',
            'cpfCnpj': '12345678900',
            'phone': '11987654321',            # "(11) 98765-4321" -> só dígitos
            'postalCode': '01310100',
            'addressNumber': '100',
        }

    def test_sem_nome_completo_usa_o_username(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        usuario.nome_completo = None

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.chamadas[0]['json']['name'] == 'cliente1'

    def test_envia_token_e_timeout_configurados(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        chamada = asaas.chamadas[0]
        assert chamada['headers']['access_token'] == 'chave-de-teste'
        assert chamada['timeout'] == REQUEST_TIMEOUT_SECONDS

    def test_ambiente_producao_usa_a_url_de_producao(self, app, usuario_com_assinatura, asaas):
        app.config['ASAAS_ENV'] = 'production'
        usuario, assinatura = usuario_com_assinatura

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        url = asaas.chamadas[0]['url']
        assert 'sandbox' not in url
        assert url.endswith('/customers')

    def test_erro_do_asaas_ao_criar_propaga_e_nao_grava_id(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        asaas.post_customers_resp = _Resp({'errors': [{'description': 'CPF inválido'}]}, status_code=400)

        with pytest.raises(requests.HTTPError):
            BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert _id_gravado(assinatura.id) is None

    def test_chave_da_api_ausente_levanta_antes_de_chamar_a_rede(self, app, usuario_com_assinatura, asaas):
        app.config['ASAAS_API_KEY'] = None
        usuario, assinatura = usuario_com_assinatura

        with pytest.raises(RuntimeError, match='ASAAS_API_KEY'):
            BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.chamadas == []


# ------------------------------------------------------------------
# cliente já gravado e existente
# ------------------------------------------------------------------

class TestClienteJaExiste:

    @pytest.fixture(autouse=True)
    def _grava_id(self, usuario_com_assinatura):
        _, assinatura = usuario_com_assinatura
        assinatura.gateway_customer_id = 'cus_existente'
        db.session.commit()

    def test_atualiza_via_put_sem_criar_cliente_novo(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert customer_id == 'cus_existente'
        assert asaas.metodos() == ['PUT']
        assert asaas.chamadas[0]['url'].endswith('/customers/cus_existente')
        assert _id_gravado(assinatura.id) == 'cus_existente'

    def test_put_leva_os_dados_atuais_do_usuario(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        usuario.endereco_numero = '999'          # usuário mudou o endereço

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.chamadas[0]['json']['addressNumber'] == '999'

    @pytest.mark.parametrize('status', [400, 401, 403, 422, 500, 503])
    def test_erro_que_nao_e_404_propaga_e_NAO_recria_o_cliente(self, usuario_com_assinatura, asaas, status):
        """Só 404 significa 'cliente não existe'. Um 5xx/401 passageiro NÃO
        pode virar um cliente duplicado no Asaas."""
        usuario, assinatura = usuario_com_assinatura
        asaas.put_resp = _Resp({'errors': []}, status_code=status)

        with pytest.raises(requests.HTTPError):
            BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.metodos() == ['PUT']
        assert _id_gravado(assinatura.id) == 'cus_existente'


# ------------------------------------------------------------------
# AUTO-CURA: cliente gravado não existe mais no Asaas (404)
# ------------------------------------------------------------------

class TestAutoCuraCliente404:

    @pytest.fixture
    def com_id_de_sandbox(self, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        assinatura.gateway_customer_id = 'cus_000_ID_DE_SANDBOX'
        db.session.commit()
        asaas.put_resp = _Resp({'errors': [{'description': 'Não encontrado'}]}, status_code=404)
        asaas.post_customers_resp = _Resp({'id': 'cus_PRODUCAO_novo'})
        return usuario, assinatura

    def test_404_no_put_recria_o_cliente_e_devolve_o_novo_id(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert customer_id == 'cus_PRODUCAO_novo'

    def test_ordem_das_chamadas_e_put_depois_post(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.metodos() == ['PUT', 'POST']
        assert asaas.chamadas[0]['url'].endswith('/customers/cus_000_ID_DE_SANDBOX')
        assert asaas.chamadas[1]['url'].endswith('/customers')

    def test_id_antigo_e_substituido_E_persistido_no_banco(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert _id_gravado(assinatura.id) == 'cus_PRODUCAO_novo'

    def test_cliente_recriado_leva_o_mesmo_payload_do_put(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox

        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        put, post = asaas.chamadas
        assert post['json'] == put['json']
        assert post['json']['cpfCnpj'] == '12345678900'

    def test_segunda_chamada_depois_da_cura_nao_cai_mais_no_404(self, com_id_de_sandbox, asaas):
        """Depois de curar, o id novo é o gravado: o próximo checkout faz só
        um PUT (que agora existe) -- sem recriar de novo."""
        usuario, assinatura = com_id_de_sandbox
        BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)
        asaas.chamadas.clear()
        asaas.put_resp = _Resp({'id': 'cus_PRODUCAO_novo'})       # agora existe

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert customer_id == 'cus_PRODUCAO_novo'
        assert asaas.metodos() == ['PUT']
        assert asaas.chamadas[0]['url'].endswith('/customers/cus_PRODUCAO_novo')

    def test_falha_ao_recriar_propaga_e_mantem_o_id_antigo(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox
        asaas.post_customers_resp = _Resp({'errors': [{'description': 'CPF inválido'}]}, status_code=400)

        with pytest.raises(requests.HTTPError):
            BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert asaas.metodos() == ['PUT', 'POST']
        assert _id_gravado(assinatura.id) == 'cus_000_ID_DE_SANDBOX'

    def test_resposta_do_post_sem_id_nao_corrompe_o_id_gravado(self, com_id_de_sandbox, asaas):
        usuario, assinatura = com_id_de_sandbox
        asaas.post_customers_resp = _Resp({})                     # 200 mas sem 'id'

        with pytest.raises(KeyError):
            BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)

        assert _id_gravado(assinatura.id) == 'cus_000_ID_DE_SANDBOX'


# ------------------------------------------------------------------
# ponta a ponta: o checkout NÃO quebra mais por causa do 404
# ------------------------------------------------------------------

class TestCheckoutComClienteDeSandbox:

    def test_criar_assinatura_checkout_conclui_mesmo_com_cliente_inexistente(self, app, usuario_com_assinatura, asaas):
        usuario, assinatura = usuario_com_assinatura
        assinatura.gateway_customer_id = 'cus_000_ID_DE_SANDBOX'
        fit = Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno',
                    preco_centavos=599, ativo=True)
        db.session.add(fit)
        db.session.commit()
        asaas.put_resp = _Resp({'errors': []}, status_code=404)
        asaas.post_customers_resp = _Resp({'id': 'cus_PRODUCAO_novo'})

        link = BillingService.criar_assinatura_checkout(usuario, fit)

        assert link == 'https://asaas.test/chk_1'
        assert asaas.metodos() == ['PUT', 'POST', 'POST']          # put 404, recria, checkout
        checkout = asaas.chamadas[-1]
        assert checkout['url'].endswith('/checkouts')
        assert 'cus_PRODUCAO_novo' in str(checkout['json'])       # checkout usa o id NOVO
        assert 'cus_000_ID_DE_SANDBOX' not in str(checkout['json'])
        assert _id_gravado(assinatura.id) == 'cus_PRODUCAO_novo'
