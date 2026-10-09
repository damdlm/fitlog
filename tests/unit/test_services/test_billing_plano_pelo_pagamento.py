"""O plano e a forma de pagamento só mudam quando um pagamento CONFIRMA, e o
plano é o que corresponde ao VALOR pago. Gerar/abandonar um checkout (cartão
ou Pix) não altera nada -- antes isso liberava os limites do plano maior sem
pagar."""
import pytest

from models import db, Assinatura, Plano
from services.billing_service import BillingService
from tests.unit.test_services.test_billing_service import (
    _criar_usuario, _preencher_dados_cobranca, _criar_planos_professor, _vincular_alunos, _RespostaFake,
)


@pytest.fixture(autouse=True)
def _cfg(app, monkeypatch):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = False
    app.config['ASAAS_API_KEY'] = 'chave-de-teste'
    app.config['APP_BASE_URL'] = 'https://fitlog.up.railway.app'
    monkeypatch.setattr('services.billing_service.requests.put', lambda url, **k: _RespostaFake({'id': 'cus_x'}))
    monkeypatch.setattr('services.billing_service.requests.delete', lambda url, **k: _RespostaFake({}))
    monkeypatch.setattr(
        'services.billing_service.requests.post',
        lambda url, **k: _RespostaFake({'id': 'pay_pix_novo', 'invoiceUrl': 'https://pix/fake',
                                        'link': 'https://checkout/fake'}))


def _professor_ativo_no_pro(nome, alunos=9, forma='pix'):
    pro, premium, fit = _criar_planos_professor()
    prof = _criar_usuario(nome, 'professor')
    _preencher_dados_cobranca(prof)
    a = Assinatura(usuario_id=prof.id, status='active', forma_pagamento=forma, plano_id=pro.id,
                   gateway_customer_id='cus_x')
    db.session.add(a)
    _vincular_alunos(prof, alunos)
    db.session.commit()
    return prof, a, pro, premium


def _recebido(evt, **payment):
    return {'id': evt, 'event': 'PAYMENT_RECEIVED', 'payment': {'customer': 'cus_x', **payment}}


class TestPlanoSoValePeloPagamento:
    def test_pix_gerado_e_nao_pago_nao_libera_mais_alunos(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t1')
            assert BillingService.pode_cadastrar_aluno(prof)[0] is False
            BillingService.criar_pagamento_pix_ativacao(prof, premium)  # só gera, não paga
            db.session.refresh(a)
            assert a.plano_id == pro.id and a.forma_pagamento == 'pix'
            assert BillingService.pode_cadastrar_aluno(prof)[0] is False

    def test_checkout_de_cartao_abandonado_nao_altera_o_plano(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t2', forma='cartao')
            BillingService.criar_assinatura_checkout(prof, premium)  # abriu e desistiu
            db.session.refresh(a)
            assert a.plano_id == pro.id and a.forma_pagamento == 'cartao'
            assert BillingService.pode_cadastrar_aluno(prof)[0] is False

    def test_pagar_o_pix_do_premium_vira_premium_e_libera(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t3')
            BillingService.criar_pagamento_pix_ativacao(prof, premium)
            BillingService.processar_webhook(_recebido(
                'e1&1', id='pay_pix_novo', billingType='PIX', value=premium.preco_centavos / 100))
            db.session.refresh(a)
            assert a.plano_id == premium.id and a.forma_pagamento == 'pix'
            assert BillingService.pode_cadastrar_aluno(prof)[0] is True

    def test_valor_que_nao_e_de_nenhum_plano_mantem_o_plano_atual(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t4')
            BillingService.processar_webhook(_recebido('e2&1', id='pay_a', billingType='PIX', value=1.23))
            db.session.refresh(a)
            assert a.plano_id == pro.id

    def test_pagamento_sem_valor_no_payload_mantem_o_plano_atual(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t5')
            BillingService.processar_webhook(_recebido('e3&1', id='pay_b', billingType='PIX'))
            db.session.refresh(a)
            assert a.plano_id == pro.id

    def test_pagar_menos_que_o_plano_gerado_nao_da_o_plano_maior(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t6')
            BillingService.criar_pagamento_pix_ativacao(prof, premium)
            # paga um Pix de valor do plano Pró (menor) -- recebe o Pró, não o Premium
            BillingService.processar_webhook(_recebido(
                'e4&1', id='pay_menor', billingType='PIX', value=pro.preco_centavos / 100))
            db.session.refresh(a)
            assert a.plano_id == pro.id

    def test_dois_planos_com_o_mesmo_preco_nao_decidem_por_valor(self, app):
        with app.app_context():
            prof, a, pro, premium = _professor_ativo_no_pro('t7')
            db.session.add(Plano(codigo='professor_gemeo', nome='Gêmeo', tipo_usuario='professor',
                                 preco_centavos=premium.preco_centavos, ativo=True))
            db.session.commit()
            BillingService.processar_webhook(_recebido(
                'e5&1', id='pay_c', billingType='PIX', value=premium.preco_centavos / 100))
            db.session.refresh(a)
            assert a.plano_id == pro.id


class TestCartaoPrimeiroPagamentoEPrimeiraRenovacao:
    def test_primeiro_pagamento_do_cartao_define_o_plano_e_a_forma(self, app):
        with app.app_context():
            pro, premium, fit = _criar_planos_professor()
            prof = _criar_usuario('c1', 'professor')
            a = Assinatura(usuario_id=prof.id, status='trialing', plano_id=fit.id, gateway_customer_id='cus_x')
            db.session.add(a)
            db.session.commit()
            BillingService.processar_webhook({
                'id': 'c1&1', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'id': 'pay_c1', 'customer': 'cus_x', 'subscription': 'sub_novo',
                            'billingType': 'CREDIT_CARD', 'value': premium.preco_centavos / 100}})
            db.session.refresh(a)
            assert a.status == 'active' and a.plano_id == premium.id
            assert a.forma_pagamento == 'cartao' and a.gateway_subscription_id == 'sub_novo'

    def test_renovacao_com_fatura_antiga_nao_rebaixa_o_plano(self, app):
        with app.app_context():
            pro, premium, fit = _criar_planos_professor()
            prof = _criar_usuario('c2', 'professor')
            a = Assinatura(usuario_id=prof.id, status='active', plano_id=premium.id, forma_pagamento='cartao',
                           gateway_customer_id='cus_x', gateway_subscription_id='sub_a',
                           gateway_ultimo_pagamento_confirmado_id='pay_anterior')
            db.session.add(a)
            db.session.commit()
            # fatura gerada ANTES do upgrade (valor do Pró) é paga depois dele
            BillingService.processar_webhook({
                'id': 'c2&1', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'id': 'pay_fatura_antiga', 'customer': 'cus_x', 'subscription': 'sub_a',
                            'billingType': 'CREDIT_CARD', 'value': pro.preco_centavos / 100}})
            db.session.refresh(a)
            assert a.plano_id == premium.id and a.status == 'active'

    def test_troca_para_pix_limpa_os_dados_do_cartao(self, app):
        with app.app_context():
            pro, premium, fit = _criar_planos_professor()
            prof = _criar_usuario('c3', 'professor')
            a = Assinatura(usuario_id=prof.id, status='active', plano_id=pro.id, forma_pagamento='cartao',
                           gateway_customer_id='cus_x', gateway_subscription_id='sub_velho',
                           cartao_ultimos_digitos='4242', cartao_bandeira='VISA')
            db.session.add(a)
            db.session.commit()
            BillingService.processar_webhook(_recebido(
                'c3&1', id='pay_pix_troca', billingType='PIX', value=pro.preco_centavos / 100))
            db.session.refresh(a)
            assert a.forma_pagamento == 'pix' and a.gateway_subscription_id is None
            assert a.cartao_ultimos_digitos is None and a.cartao_bandeira is None
