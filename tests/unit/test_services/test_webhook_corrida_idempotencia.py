"""P2-f: o mesmo evento do Asaas chegando em paralelo não pode virar 500."""
from types import SimpleNamespace

import pytest

from models import Assinatura, EventoWebhookAsaas, db
from services.billing_service import BillingService
from tests.unit.test_services.test_billing_service import _criar_usuario


def _assinatura(username):
    aluno = _criar_usuario(username)
    a = BillingService.iniciar_trial(aluno)
    a.status = 'trialing'
    a.gateway_subscription_id = 'sub_corrida'
    db.session.commit()
    return a


class _QuerySemVerOEventoNaPrimeiraVez:
    """Simula a corrida: o 1o SELECT de idempotência não enxerga o evento
    (a outra requisição ainda não tinha commitado); os seguintes enxergam."""

    def __init__(self, real):
        self._real = real
        self.chamadas = 0

    def filter_by(self, **kw):
        self.chamadas += 1
        if self.chamadas == 1:
            return SimpleNamespace(first=lambda: None)
        return self._real.filter_by(**kw)


PAYLOAD = {'id': 'evt_corrida_1', 'event': 'PAYMENT_CONFIRMED', 'payment': {'subscription': 'sub_corrida'}}


def test_evento_duplicado_em_paralelo_retorna_true_sem_estourar(app, monkeypatch):
    with app.app_context():
        a = _assinatura('corrida_webhook')
        assert BillingService.processar_webhook(dict(PAYLOAD)) is True  # "outra requisição" ganhou
        db.session.refresh(a)
        assert a.status == 'active'

        monkeypatch.setattr(EventoWebhookAsaas, 'query', _QuerySemVerOEventoNaPrimeiraVez(EventoWebhookAsaas.query))
        assert BillingService.processar_webhook(dict(PAYLOAD)) is True  # sem o tratamento: IntegrityError

        assert EventoWebhookAsaas.query.filter_by(event_id='evt_corrida_1').count() == 1
        db.session.refresh(a)
        assert a.status == 'active'


def test_integrity_error_que_nao_e_duplicata_continua_subindo(app, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        _assinatura('corrida_webhook_outro_erro')

        def commit_quebrado():
            raise IntegrityError('INSERT', {}, Exception('violação qualquer'))

        monkeypatch.setattr(db.session, 'commit', commit_quebrado)
        with pytest.raises(IntegrityError):
            BillingService.processar_webhook({'id': 'evt_corrida_2', 'event': 'PAYMENT_CONFIRMED',
                                              'payment': {'subscription': 'sub_corrida'}})
