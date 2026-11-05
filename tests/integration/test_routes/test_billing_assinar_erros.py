"""
POST /billing/assinar -- ramos de erro e de validação que não tinham teste.
(O caminho feliz, escolha de plano e CPF inválido já estão em
test_billing_routes.py.)

Cada `except` da view transforma uma falha do gateway numa mensagem
amigável + redirect. Se um deles quebrasse, o usuário veria um 500 na hora
de PAGAR.
"""

import pytest
import requests

from models import db, User, Plano
from services.billing_service import (
    BillingService, AssinaturaAtualizadaError, AssinaturaGatewaySumiuError,
    AssinaturaJaAtivaError, DadosCobrancaIncompletosError,
)
from services.configuracao_service import ConfiguracaoService

URL = '/billing/assinar'
VOLTA = '/billing/minha-assinatura'


def _user(username, tipo='aluno', completo=True, admin=False):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo, is_admin=admin)
    u.set_password('SenhaForte123!')
    if completo:
        u.cpf_cnpj, u.telefone = '12345678900', '11987654321'
        u.endereco_cep, u.endereco_numero = '01310100', '100'
    db.session.add(u)
    db.session.commit()
    return u


def _planos():
    db.session.add_all([
        Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599),
        Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
              preco_centavos=2990, min_alunos=3, max_alunos=9),
    ])
    db.session.commit()


def _login(client, username):
    resp = client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123!'})
    with client.session_transaction() as sess:
        sess.pop('_flashes', None)           # descarta o "boas-vindas" do login
    return resp


def _flashes(client):
    with client.session_transaction() as sess:
        return list(sess.get('_flashes', []))


def _checkout(monkeypatch, resultado, nome='criar_assinatura_checkout'):
    """Faz o método do BillingService devolver (ou levantar) `resultado`."""
    chamadas = []

    def _fake(*a, **k):
        chamadas.append((a, k))
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(BillingService, nome, staticmethod(_fake))
    return chamadas


@pytest.fixture
def aluno(client, app):
    _planos()
    _user('aluno_ass')
    _login(client, 'aluno_ass')


# ------------------------------------------------------------------
# Mensagem por tipo de falha
# ------------------------------------------------------------------

class TestFalhasDoGateway:

    def _assinar(self, client):
        resp = client.post(URL)
        assert resp.status_code == 302 and resp.headers['Location'].endswith(VOLTA)
        return _flashes(client)

    def test_plano_trocado_na_mesma_assinatura_e_sucesso_sem_cobranca(self, client, aluno, monkeypatch):
        plano = Plano.query.filter_by(codigo='aluno_fit').one()
        _checkout(monkeypatch, AssinaturaAtualizadaError(plano))

        f = self._assinar(client)

        assert len(f) == 1 and f[0][0] == 'success'
        assert 'Plano Fit' in f[0][1] and 'nenhuma cobrança foi feita agora' in f[0][1]

    def test_assinatura_sumiu_do_gateway_pede_para_tentar_de_novo(self, client, aluno, monkeypatch):
        plano = Plano.query.filter_by(codigo='aluno_fit').one()
        _checkout(monkeypatch, AssinaturaGatewaySumiuError(plano))

        f = self._assinar(client)

        assert f[0][0] == 'warning' and 'Clique em assinar novamente' in f[0][1]

    def test_duplo_clique_nao_cria_outra_cobranca(self, client, aluno, monkeypatch):
        plano = Plano.query.filter_by(codigo='aluno_fit').one()
        _checkout(monkeypatch, AssinaturaJaAtivaError(plano))

        f = self._assinar(client)

        assert f[0][0] == 'info' and 'nenhuma cobrança nova foi criada' in f[0][1]

    def test_dados_incompletos_detectados_so_no_service(self, client, aluno, monkeypatch):
        _checkout(monkeypatch, DadosCobrancaIncompletosError(['cpf_cnpj']))

        f = self._assinar(client)

        assert f[0][0] == 'warning' and 'Preencha CPF/CNPJ' in f[0][1]

    def test_api_key_nao_configurada_vira_mensagem_generica_sem_vazar_detalhe(self, client, aluno, monkeypatch):
        _checkout(monkeypatch, RuntimeError('ASAAS_API_KEY ausente: segredo-interno'))

        f = self._assinar(client)

        assert f[0][0] == 'danger' and 'Cobrança ainda não está disponível' in f[0][1]
        assert 'ASAAS' not in f[0][1] and 'segredo' not in f[0][1]

    @pytest.mark.parametrize('exc', [
        requests.ConnectionError('dns'), requests.Timeout('lento'),
        requests.HTTPError('500 do asaas'),
    ])
    def test_erro_de_rede_ou_http_vira_aviso_de_conexao(self, client, aluno, monkeypatch, exc):
        _checkout(monkeypatch, exc)

        f = self._assinar(client)

        assert f[0][0] == 'danger' and 'Não foi possível conectar ao sistema de pagamento' in f[0][1]
        assert '500' not in f[0][1] and 'dns' not in f[0][1]

    @pytest.mark.parametrize('vazio', [None, ''])
    def test_gateway_sem_url_de_checkout(self, client, aluno, monkeypatch, vazio):
        _checkout(monkeypatch, vazio)

        f = self._assinar(client)

        assert f[0][0] == 'danger' and 'Não foi possível gerar o link de pagamento' in f[0][1]


# ------------------------------------------------------------------
# Pré-condições
# ------------------------------------------------------------------

class TestPreCondicoes:

    def test_modo_gratis_nem_chama_o_gateway(self, client, aluno, monkeypatch):
        ConfiguracaoService.set_cobranca_ativa(False)
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        resp = client.post(URL)

        assert resp.status_code == 302 and resp.headers['Location'].endswith(VOLTA)
        assert chamadas == []
        assert any(c == 'info' and 'gratuito' in m for c, m in _flashes(client))

    def test_tela_de_assinatura_desligada_bloqueia_usuario_comum(self, client, aluno, monkeypatch):
        ConfiguracaoService.set_tela_assinatura_ativa(False)
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        resp = client.post(URL)

        assert resp.status_code == 302 and chamadas == []

    def test_sem_plano_cadastrado_avisa_e_nao_chama_o_gateway(self, client, app, monkeypatch):
        """Seed de planos ausente: erro de operação, não do usuário."""
        _user('aluno_sem_plano')
        _login(client, 'aluno_sem_plano')
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        resp = client.post(URL)

        assert resp.status_code == 302 and resp.headers['Location'].endswith(VOLTA)
        assert chamadas == []
        assert any(c == 'danger' and 'Não foi possível iniciar a assinatura' in m for c, m in _flashes(client))

    def test_plano_fit_inativo_e_tratado_como_ausente(self, client, app, monkeypatch):
        _planos()
        Plano.query.filter_by(codigo='aluno_fit').update({'ativo': False})
        db.session.commit()
        _user('aluno_plano_off')
        _login(client, 'aluno_plano_off')
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        client.post(URL)

        assert chamadas == []

    def test_perfil_que_nao_e_aluno_nem_professor_vai_para_a_home(self, client, app, monkeypatch):
        _planos()
        _user('adm_ass', tipo='admin', admin=True)
        _login(client, 'adm_ass')
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        resp = client.post(URL)

        assert resp.status_code == 302 and not resp.headers['Location'].endswith(VOLTA)
        assert chamadas == []

    def test_professor_escolhendo_plano_inexistente_e_recusado(self, client, app, monkeypatch):
        _planos()
        _user('prof_ass', tipo='professor')
        _login(client, 'prof_ass')
        chamadas = _checkout(monkeypatch, 'https://x/pague')

        resp = client.post(URL, data={'plano_codigo': 'plano_que_nao_existe'})

        assert resp.status_code == 302 and chamadas == []
        assert any(c == 'warning' and 'não está disponível' in m for c, m in _flashes(client))


# ------------------------------------------------------------------
# Dados de cobrança: parciais, normalização e persistência
# ------------------------------------------------------------------

class TestDadosDeCobranca:

    @pytest.fixture
    def sem_dados(self, client, app):
        _planos()
        _user('aluno_sem_dados', completo=False)
        _login(client, 'aluno_sem_dados')

    def _user(self):
        db.session.expire_all()
        return User.query.filter_by(username='aluno_sem_dados').one()

    VALIDO = {'cpf_cnpj': '123.456.789-00', 'telefone': '(11) 98765-4321',
              'endereco_cep': '01310-100', 'endereco_numero': ' 100 '}

    def test_dados_validos_sao_normalizados_gravados_e_seguem_para_o_checkout(self, client, sem_dados, monkeypatch):
        chamadas = _checkout(monkeypatch, 'https://asaas.test/pague')

        resp = client.post(URL, data=self.VALIDO)

        assert resp.status_code == 302 and resp.headers['Location'] == 'https://asaas.test/pague'
        u = self._user()
        assert (u.cpf_cnpj, u.telefone, u.endereco_cep, u.endereco_numero) == \
            ('12345678900', '11987654321', '01310100', '100')
        assert len(chamadas) == 1

    def test_cnpj_de_14_digitos_e_aceito(self, client, sem_dados, monkeypatch):
        _checkout(monkeypatch, 'https://asaas.test/pague')

        client.post(URL, data={**self.VALIDO, 'cpf_cnpj': '12.345.678/0001-99'})

        assert self._user().cpf_cnpj == '12345678000199'

    @pytest.mark.parametrize('campo,ruim', [
        ('telefone', '123'), ('telefone', ''), ('telefone', 'abc'),
        ('endereco_cep', '1234'), ('endereco_cep', '012345678'),
        ('endereco_numero', ''), ('endereco_numero', '   '),
        ('cpf_cnpj', '123456789'), ('cpf_cnpj', ''),
    ])
    def test_um_campo_invalido_barra_tudo_e_nao_grava_nada(self, client, sem_dados, monkeypatch, campo, ruim):
        chamadas = _checkout(monkeypatch, 'https://asaas.test/pague')

        resp = client.post(URL, data={**self.VALIDO, campo: ruim})

        assert resp.status_code == 302 and resp.headers['Location'].endswith(VOLTA)
        assert chamadas == []
        u = self._user()
        assert (u.cpf_cnpj, u.telefone, u.endereco_cep, u.endereco_numero) == (None, None, None, None)
        assert any(c == 'warning' and 'Preencha CPF/CNPJ' in m for c, m in _flashes(client))

    def test_so_pede_o_que_falta_e_preserva_o_que_ja_estava_salvo(self, client, app, monkeypatch):
        _planos()
        u = _user('aluno_parcial', completo=False)
        u.cpf_cnpj, u.telefone = '99999999999', '11911112222'
        db.session.commit()
        _login(client, 'aluno_parcial')
        _checkout(monkeypatch, 'https://asaas.test/pague')

        # tenta sobrescrever o CPF já salvo: deve ser ignorado
        resp = client.post(URL, data={'cpf_cnpj': '00000000000', 'telefone': '11000000000',
                                      'endereco_cep': '01310-100', 'endereco_numero': '7'})

        assert resp.headers['Location'] == 'https://asaas.test/pague'
        db.session.expire_all()
        u = User.query.filter_by(username='aluno_parcial').one()
        assert (u.cpf_cnpj, u.telefone, u.endereco_cep, u.endereco_numero) == \
            ('99999999999', '11911112222', '01310100', '7')


# ------------------------------------------------------------------
# forma_pagamento
# ------------------------------------------------------------------

class TestFormaPagamento:

    def test_pix_usa_o_fluxo_de_pagamento_avulso(self, client, aluno, monkeypatch):
        cartao = _checkout(monkeypatch, 'https://x/cartao')
        pix = _checkout(monkeypatch, 'https://x/pix', nome='criar_pagamento_pix_ativacao')

        resp = client.post(URL, data={'forma_pagamento': 'pix'})

        assert resp.headers['Location'] == 'https://x/pix'
        assert len(pix) == 1 and cartao == []

    @pytest.mark.parametrize('valor', ['', 'boleto', 'PIX', "pix'; DROP TABLE users;--", 'cartao '])
    def test_valor_desconhecido_cai_no_cartao_nunca_repassado_ao_gateway(self, client, aluno, monkeypatch, valor):
        cartao = _checkout(monkeypatch, 'https://x/cartao')
        pix = _checkout(monkeypatch, 'https://x/pix', nome='criar_pagamento_pix_ativacao')

        resp = client.post(URL, data={'forma_pagamento': valor})

        assert resp.headers['Location'] == 'https://x/cartao'     # 'cartao ' vira 'cartao' pelo strip()
        assert pix == [] and len(cartao) == 1

    def test_padrao_sem_campo_e_cartao(self, client, aluno, monkeypatch):
        _checkout(monkeypatch, 'https://x/cartao')
        assert client.post(URL).headers['Location'] == 'https://x/cartao'

    def test_falha_no_pix_tem_o_mesmo_tratamento(self, client, aluno, monkeypatch):
        _checkout(monkeypatch, requests.Timeout('lento'), nome='criar_pagamento_pix_ativacao')

        resp = client.post(URL, data={'forma_pagamento': 'pix'})

        assert resp.headers['Location'].endswith(VOLTA)
        assert any(c == 'danger' and 'conectar' in m for c, m in _flashes(client))
