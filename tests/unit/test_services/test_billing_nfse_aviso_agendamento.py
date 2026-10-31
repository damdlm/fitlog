"""Aviso aos admins quando o Asaas RECUSA o agendamento da NFS-e.

Caso real (29/10/2026): a validação de PIS/COFINS do Asaas passou a recusar
o agendamento (HTTP 400) e o erro só ficou no log do Railway; ninguém emitiu
a nota. Agora o admin é avisado no sino do app -- mas só DEPOIS do commit do
webhook, porque o agendamento roda no meio da transação que ativa o plano.
"""
import pytest
import requests

import services.billing_service as billing
from models import Notificacao, PagamentoRecebido, User, db
from services.billing_service import BillingService
from services.notificacao_service import NotificacaoService
from tests.unit.test_services.test_billing_service import _criar_usuario

ERRO_PIS_COFINS = {'errors': [{
    'code': 'invalid_action',
    'description': 'A Situação tributária do PIS/COFINS é obrigatória',
}]}


@pytest.fixture(autouse=True)
def _config(app):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = False
    app.config['ASAAS_API_KEY'] = 'chave_de_teste'


class _Resp:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        if self._corpo is None:
            raise ValueError('sem json')
        return self._corpo


def _asaas_responde(monkeypatch, resposta=None, erro=None):
    def _post(url, json=None, headers=None, timeout=None):
        if erro:
            raise erro
        return resposta
    monkeypatch.setattr(billing.requests, 'post', _post)


def _avisos():
    from flask import g
    return list(g.get('nfse_avisos_pendentes', []))


def _notificacoes_admin():
    admin = User.query.filter_by(is_admin=True).first()
    return Notificacao.query.filter_by(destinatario_id=admin.id, tipo='nota_fiscal_erro').all()


class TestEnfileiraAviso:
    def test_recusa_400_guarda_o_motivo_do_asaas_e_ainda_nao_notifica(self, app, monkeypatch):
        _asaas_responde(monkeypatch, _Resp(400, ERRO_PIS_COFINS))
        BillingService._agendar_nota_fiscal('pay_1', 5.99)
        assert _avisos() == [{'payment_id': 'pay_1',
                              'motivo': 'A Situação tributária do PIS/COFINS é obrigatória'}]
        assert _notificacoes_admin() == []  # nada é criado no meio da transação

    def test_varios_erros_viram_um_motivo_so(self, app, monkeypatch):
        corpo = {'errors': [{'description': 'Erro A'}, {'description': 'Erro B'}]}
        _asaas_responde(monkeypatch, _Resp(400, corpo))
        BillingService._agendar_nota_fiscal('pay_2', 5.99)
        assert _avisos()[0]['motivo'] == 'Erro A; Erro B'

    def test_resposta_sem_json_usa_o_codigo_http(self, app, monkeypatch):
        _asaas_responde(monkeypatch, _Resp(503, None))
        BillingService._agendar_nota_fiscal('pay_3', 5.99)
        assert _avisos()[0]['motivo'] == 'HTTP 503'

    def test_erro_de_rede_tambem_enfileira(self, app, monkeypatch):
        _asaas_responde(monkeypatch, erro=requests.ConnectionError('fora do ar'))
        BillingService._agendar_nota_fiscal('pay_4', 5.99)
        assert 'sem resposta do Asaas' in _avisos()[0]['motivo']

    def test_sucesso_nao_enfileira_nada(self, app, monkeypatch):
        _asaas_responde(monkeypatch, _Resp(200, {'id': 'inv_1', 'status': 'SCHEDULED'}))
        BillingService._agendar_nota_fiscal('pay_5', 5.99)
        assert _avisos() == []


def _assinatura(username, sub_id):
    aluno = _criar_usuario(username)
    a = BillingService.iniciar_trial(aluno)
    a.status = 'trialing'
    a.gateway_subscription_id = sub_id
    db.session.commit()
    return a


def _evento(evt, sub_id, payment_id):
    return {'id': evt, 'event': 'PAYMENT_CONFIRMED',
            'payment': {'id': payment_id, 'value': 5.99, 'subscription': sub_id,
                        'billingType': 'PIX'}}


class TestWebhookDePagamento:
    def test_recusa_notifica_o_admin_e_o_pagamento_continua_processado(self, app, monkeypatch):
        a = _assinatura('aviso_nota_1', 'sub_aviso_1')
        _asaas_responde(monkeypatch, _Resp(400, ERRO_PIS_COFINS))

        assert BillingService.processar_webhook(_evento('evt_aviso_1', 'sub_aviso_1', 'pay_aviso_1')) is True

        db.session.refresh(a)
        assert a.status == 'active'
        assert PagamentoRecebido.query.filter_by(gateway_payment_id='pay_aviso_1').count() == 1
        notificacoes = _notificacoes_admin()
        assert len(notificacoes) == 1
        n = notificacoes[0]
        assert n.titulo == 'Nota fiscal não foi agendada'
        assert 'PIS/COFINS' in n.mensagem and 'pay_aviso_1' in n.mensagem
        assert 'manualmente' in n.mensagem
        assert _avisos() == []  # fila esvaziada

    def test_asaas_aceitando_a_nota_nao_gera_aviso(self, app, monkeypatch):
        _assinatura('aviso_nota_2', 'sub_aviso_2')
        _asaas_responde(monkeypatch, _Resp(200, {'id': 'inv_ok', 'status': 'SCHEDULED'}))
        BillingService.processar_webhook(_evento('evt_aviso_2', 'sub_aviso_2', 'pay_aviso_2'))
        assert _notificacoes_admin() == []

    def test_reenvio_do_mesmo_evento_nao_duplica_o_aviso(self, app, monkeypatch):
        _assinatura('aviso_nota_3', 'sub_aviso_3')
        _asaas_responde(monkeypatch, _Resp(400, ERRO_PIS_COFINS))
        evento = _evento('evt_aviso_3', 'sub_aviso_3', 'pay_aviso_3')
        BillingService.processar_webhook(dict(evento))
        BillingService.processar_webhook(dict(evento))
        assert len(_notificacoes_admin()) == 1

    def test_aviso_so_sai_depois_do_commit_do_webhook(self, app, monkeypatch):
        _assinatura('aviso_nota_4', 'sub_aviso_4')
        _asaas_responde(monkeypatch, _Resp(400, ERRO_PIS_COFINS))
        ordem = []
        commit_real = db.session.commit

        def commit_registrando():
            ordem.append('commit')
            commit_real()

        monkeypatch.setattr(db.session, 'commit', commit_registrando)
        monkeypatch.setattr(
            NotificacaoService, 'criar_ou_agrupar',
            staticmethod(lambda **kw: ordem.append('notifica')),
        )
        BillingService.processar_webhook(_evento('evt_aviso_4', 'sub_aviso_4', 'pay_aviso_4'))
        assert 'notifica' in ordem and 'commit' in ordem
        assert ordem.index('commit') < ordem.index('notifica')

    def test_falha_ao_notificar_nao_derruba_o_webhook_nem_desfaz_o_plano(self, app, monkeypatch, caplog):
        a = _assinatura('aviso_nota_5', 'sub_aviso_5')
        _asaas_responde(monkeypatch, _Resp(400, ERRO_PIS_COFINS))

        def quebrado(**kw):
            raise RuntimeError('sino fora do ar')

        monkeypatch.setattr(NotificacaoService, 'criar_ou_agrupar', staticmethod(quebrado))
        assert BillingService.processar_webhook(_evento('evt_aviso_5', 'sub_aviso_5', 'pay_aviso_5')) is True
        db.session.refresh(a)
        assert a.status == 'active'
        assert PagamentoRecebido.query.filter_by(gateway_payment_id='pay_aviso_5').count() == 1
        assert 'Falha ao notificar os admins' in caplog.text