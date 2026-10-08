"""Revisão do código de pagamento: reenvio do mesmo pagamento não estende
acesso, Pix x cartão é decidido pelo tipo do pagamento confirmado, chargeback
corta acesso, a API do Asaas é a fonte dos identificadores e payload fora do
formato não derruba o webhook."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from models import db, User, Assinatura, Plano
from services.billing_service import BillingService


@pytest.fixture(autouse=True)
def _cfg(app):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = False
    app.config['ASAAS_API_KEY'] = 'chave-de-teste'


def _plano():
    p = Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599, ativo=True)
    db.session.add(p)
    db.session.flush()
    return p


def _assinatura(nome, **campos):
    user = User(username=nome, email=f'{nome}@teste.com', tipo_usuario='aluno')
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    a = Assinatura(usuario_id=user.id, plano_id=_plano().id if not Plano.query.first() else Plano.query.first().id, **campos)
    db.session.add(a)
    db.session.commit()
    return a


def _evento(evt, tipo, **payment):
    return {'id': evt, 'event': tipo, 'payment': payment}


# ------------------------------------------------ (3) reenvio não estende
def test_mesmo_pagamento_reenviado_nao_estende_periodo(app):
    with app.app_context():
        a = _assinatura('r3a', status='past_due', forma_pagamento='pix', gateway_customer_id='cus_r3a',
                        carencia_termina_em=datetime.now(timezone.utc) + timedelta(days=1))
        ev = lambda eid: _evento(eid, 'PAYMENT_RECEIVED', id='pay_mesmo', customer='cus_r3a', billingType='PIX')
        BillingService.processar_webhook(ev('evt_1&1'))
        db.session.refresh(a)
        assert a.status == 'active' and a.periodo_atual_fim is not None
        periodo = a.periodo_atual_fim
        # passa o tempo; chega o MESMO pagamento de novo (reenvio / botão do painel)
        a.periodo_atual_fim = datetime.now(timezone.utc) - timedelta(days=5)
        a.status = 'past_due'
        db.session.commit()
        vencido = a.periodo_atual_fim
        BillingService.processar_webhook(ev('evt_1&2'))
        db.session.refresh(a)
        assert a.periodo_atual_fim == vencido, 'o reenvio estendeu o período'
        assert a.status == 'past_due', 'o reenvio reativou uma assinatura vencida'
        assert periodo is not None


def test_confirmed_e_depois_received_do_mesmo_pix_contam_uma_vez(app):
    with app.app_context():
        a = _assinatura('r3b', status='trialing', forma_pagamento='pix', gateway_customer_id='cus_r3b')
        BillingService.processar_webhook(_evento('e1&1', 'PAYMENT_CONFIRMED', id='pay_x', customer='cus_r3b', billingType='PIX'))
        db.session.refresh(a)
        primeiro = a.periodo_atual_fim
        BillingService.processar_webhook(_evento('e2&1', 'PAYMENT_RECEIVED', id='pay_x', customer='cus_r3b', billingType='PIX'))
        db.session.refresh(a)
        assert a.periodo_atual_fim == primeiro


def test_pagamento_novo_continua_estendendo(app):
    with app.app_context():
        a = _assinatura('r3c', status='past_due', forma_pagamento='pix', gateway_customer_id='cus_r3c',
                        carencia_termina_em=datetime.now(timezone.utc) + timedelta(days=1))
        BillingService.processar_webhook(_evento('a&1', 'PAYMENT_RECEIVED', id='pay_mes1', customer='cus_r3c', billingType='PIX'))
        db.session.refresh(a)
        a.periodo_atual_fim = datetime.now(timezone.utc) - timedelta(days=1)
        a.status = 'past_due'
        db.session.commit()
        velho = a.periodo_atual_fim
        BillingService.processar_webhook(_evento('b&1', 'PAYMENT_RECEIVED', id='pay_mes2', customer='cus_r3c', billingType='PIX'))
        db.session.refresh(a)
        assert a.status == 'active' and a.periodo_atual_fim > velho


# --------------------------------------------- (2) Pix x cartão pelo tipo
def test_cartao_confirmado_com_forma_pix_nao_cancela_a_recorrencia(app, monkeypatch):
    deletes = []
    monkeypatch.setattr('services.billing_service.requests.delete', lambda url, **k: deletes.append(url) or MagicMock(status_code=200))
    with app.app_context():
        a = _assinatura('r2a', status='active', forma_pagamento='pix', gateway_customer_id='cus_r2a',
                        gateway_subscription_id='sub_cartao')
        BillingService.processar_webhook(_evento('c&1', 'PAYMENT_CONFIRMED', id='pay_cartao_m2', customer='cus_r2a',
                                                 subscription='sub_cartao', billingType='CREDIT_CARD'))
        db.session.refresh(a)
        assert deletes == []
        assert a.gateway_subscription_id == 'sub_cartao'
        assert a.forma_pagamento == 'cartao'
        assert a.status == 'active'


def test_pix_confirmado_ainda_cancela_o_cartao_antigo(app, monkeypatch):
    deletes = []
    monkeypatch.setattr('services.billing_service.requests.delete', lambda url, **k: deletes.append(url) or MagicMock(status_code=200))
    with app.app_context():
        a = _assinatura('r2b', status='active', forma_pagamento='pix', gateway_customer_id='cus_r2b',
                        gateway_subscription_id='sub_cartao_antigo')
        BillingService.processar_webhook(_evento('p&1', 'PAYMENT_RECEIVED', id='pay_pix_ok', customer='cus_r2b', billingType='PIX'))
        db.session.refresh(a)
        assert deletes and a.gateway_subscription_id is None and a.forma_pagamento == 'pix'


def test_sem_billing_type_usa_a_forma_gravada(app):
    with app.app_context():
        a = _assinatura('r2c', status='trialing', forma_pagamento='pix', gateway_customer_id='cus_r2c')
        BillingService.processar_webhook(_evento('s&1', 'PAYMENT_RECEIVED', id='pay_s', customer='cus_r2c'))
        db.session.refresh(a)
        assert a.periodo_atual_fim is not None


# ---------------------------------------------------------- (4) chargeback
def test_chargeback_corta_o_acesso(app):
    with app.app_context():
        a = _assinatura('cb', status='active', forma_pagamento='cartao', gateway_customer_id='cus_cb',
                        gateway_subscription_id='sub_cb')
        BillingService.processar_webhook(_evento('cb&1', 'PAYMENT_CHARGEBACK_REQUESTED', id='pay_cb',
                                                 customer='cus_cb', subscription='sub_cb'))
        db.session.refresh(a)
        assert a.status == 'canceled'


# ------------------------------------- (5) a API é a fonte dos identificadores
def _api(customer, status='RECEIVED', **extra):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {'status': status, 'customer': customer, **extra}
    return r


def test_pagamento_de_outro_cliente_nao_ativa_a_vitima(app, monkeypatch):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = True
    monkeypatch.setattr('services.billing_service.requests.get', lambda url, **k: _api('cus_atacante', billingType='PIX'))
    with app.app_context():
        vitima = _assinatura('vitima', status='blocked', forma_pagamento='pix', gateway_customer_id='cus_vitima')
        # corpo do webhook aponta para a vítima via externalReference, sem customer
        BillingService.processar_webhook(_evento('f&1', 'PAYMENT_RECEIVED', id='pay_real_do_atacante',
                                                 externalReference=str(vitima.id)))
        db.session.refresh(vitima)
        assert vitima.status == 'blocked'


def test_api_sem_externalreference_localiza_pelo_cliente_real(app, monkeypatch):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = True
    monkeypatch.setattr('services.billing_service.requests.get', lambda url, **k: _api('cus_ok', billingType='PIX'))
    with app.app_context():
        a = _assinatura('legit', status='trialing', forma_pagamento='pix', gateway_customer_id='cus_ok')
        BillingService.processar_webhook(_evento('g&1', 'PAYMENT_RECEIVED', id='pay_legit'))
        db.session.refresh(a)
        assert a.status == 'active'


# ------------------------------------------------ (6) payload fora do formato
@pytest.mark.parametrize('payload', [
    [], 'texto', 42,
    {'id': 'x1', 'event': 'PAYMENT_RECEIVED', 'payment': 'texto'},
    {'id': 'x2', 'event': 'PAYMENT_RECEIVED', 'payment': {'id': 'p', 'externalReference': 123456}},
    {'id': 'x3', 'event': 'PAYMENT_RECEIVED', 'payment': {'id': 'p', 'customer': {'a': 1}, 'subscription': ['s']}},
    {'id': 5, 'event': 'PAYMENT_RECEIVED'},
    {'id': 'x4', 'event': ['PAYMENT_RECEIVED']},
])
def test_payload_fora_do_formato_nao_levanta_excecao(app, payload):
    with app.app_context():
        assert BillingService.processar_webhook(payload) in (True, False)
