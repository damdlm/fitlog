"""Evento PAYMENT_OVERDUE não reabre nem estende carência de quem já está
bloqueado, cancelado ou em atraso -- só pagamento confirmado devolve acesso."""
from datetime import datetime, timedelta, timezone

import pytest

from models import db, User, Assinatura
from services.billing_service import BillingService


@pytest.fixture(autouse=True)
def _sem_reconsulta_asaas(app):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = False


def _assinatura(status, carencia=None, nome=None):
    user = User(username=nome or f'u_{status}_{id(object())}', email=f'{id(object())}@teste.com', tipo_usuario='aluno')
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    a = Assinatura(usuario_id=user.id, status=status, gateway_subscription_id='sub_c', carencia_termina_em=carencia)
    db.session.add(a)
    db.session.commit()
    return a


def _overdue(evt):
    return BillingService.processar_webhook(
        {'id': evt, 'event': 'PAYMENT_OVERDUE', 'payment': {'id': f'pay_{evt}', 'subscription': 'sub_c'}})


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def test_blocked_continua_bloqueado(app):
    with app.app_context():
        a = _assinatura('blocked', carencia=datetime.now(timezone.utc) - timedelta(days=2))
        antes = _utc(a.carencia_termina_em)
        assert _overdue('e1') is True
        db.session.refresh(a)
        assert a.status == 'blocked'
        assert _utc(a.carencia_termina_em) == antes


def test_canceled_continua_cancelado(app):
    with app.app_context():
        a = _assinatura('canceled')
        assert _overdue('e2') is True
        db.session.refresh(a)
        assert a.status == 'canceled'
        assert a.carencia_termina_em is None


def test_past_due_nao_estende_carencia_em_andamento(app):
    with app.app_context():
        fim = datetime.now(timezone.utc) + timedelta(days=1)
        a = _assinatura('past_due', carencia=fim)
        assert _overdue('e3') is True
        db.session.refresh(a)
        assert a.status == 'past_due'
        assert abs((_utc(a.carencia_termina_em) - fim).total_seconds()) < 1


def test_mesmo_evento_repetido_varias_vezes_nao_estende(app):
    with app.app_context():
        a = _assinatura('active')
        _overdue('e4')
        db.session.refresh(a)
        primeira = _utc(a.carencia_termina_em)
        assert a.status == 'past_due' and primeira is not None
        _overdue('e5')
        _overdue('e6')
        db.session.refresh(a)
        assert _utc(a.carencia_termina_em) == primeira


def test_active_ainda_entra_em_atraso_normalmente(app):
    with app.app_context():
        a = _assinatura('active')
        _overdue('e7')
        db.session.refresh(a)
        assert a.status == 'past_due'
        assert a.carencia_termina_em is not None


def test_past_due_sem_carencia_registrada_recebe_carencia(app):
    with app.app_context():
        a = _assinatura('past_due', carencia=None)
        _overdue('e8')
        db.session.refresh(a)
        assert a.carencia_termina_em is not None


@pytest.mark.parametrize('status', ['blocked', 'canceled'])
def test_pagamento_confirmado_reativa_depois_de_bloqueado_ou_cancelado(app, status):
    with app.app_context():
        a = _assinatura(status)
        BillingService.processar_webhook(
            {'id': f'rec_{status}', 'event': 'PAYMENT_RECEIVED', 'payment': {'id': 'pay_ok', 'subscription': 'sub_c'}})
        db.session.refresh(a)
        assert a.status == 'active'
        assert a.carencia_termina_em is None
