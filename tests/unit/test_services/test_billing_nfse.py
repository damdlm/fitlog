"""NFS-e (Asaas): data de competência no fuso de São Paulo, log do
agendamento e tratamento dos eventos INVOICE_* do webhook."""
import logging
from datetime import datetime, timezone

import pytest

import services.billing_service as billing
from models import EventoWebhookAsaas, Notificacao, User, db
from services.billing_service import BillingService, _data_competencia_nfse
from services.notificacao_service import NotificacaoService


@pytest.fixture(autouse=True)
def _sem_reconsulta_asaas(app):
    app.config['ASAAS_WEBHOOK_VERIFICAR_API'] = False
    # _agendar_nota_fiscal monta os headers com a chave; sem ela levanta
    # RuntimeError antes mesmo do POST (que os testes substituem por um fake).
    app.config['ASAAS_API_KEY'] = 'chave_de_teste'


class TestDataCompetenciaNfse:
    def test_depois_das_21h_em_brasilia_continua_no_mesmo_dia(self):
        # 00:30 UTC de 08/10 == 21:30 de 07/10 em Brasília.
        agora = datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc)
        assert _data_competencia_nfse(agora) == '2026-10-07'

    def test_ultimo_dia_do_mes_nao_cai_no_mes_seguinte(self):
        # 01:30 UTC de 01/11 == 22:30 de 31/10 em Brasília.
        agora = datetime(2026, 11, 1, 1, 30, tzinfo=timezone.utc)
        assert _data_competencia_nfse(agora) == '2026-10-31'

    def test_horario_comercial_nao_muda(self):
        agora = datetime(2026, 10, 7, 11, 3, tzinfo=timezone.utc)
        assert _data_competencia_nfse(agora) == '2026-10-07'

    def test_datetime_sem_fuso_e_tratado_como_utc(self):
        assert _data_competencia_nfse(datetime(2026, 11, 1, 1, 30)) == '2026-10-31'

    def test_sem_argumento_devolve_data_valida(self):
        assert len(_data_competencia_nfse()) == 10


class _RespFake:
    def __init__(self, status_code=200, corpo=None, texto=''):
        self.status_code = status_code
        self._corpo = corpo
        self.text = texto

    def json(self):
        if self._corpo is None:
            raise ValueError('sem json')
        return self._corpo


class TestAgendarNotaFiscal:
    def _capturar_post(self, monkeypatch, resposta):
        chamadas = []

        def _post(url, json=None, headers=None, timeout=None):
            chamadas.append({'url': url, 'json': json})
            return resposta

        monkeypatch.setattr(billing.requests, 'post', _post)
        return chamadas

    def test_envia_data_de_competencia_no_fuso_de_sao_paulo(self, app, monkeypatch):
        monkeypatch.setattr(billing, '_data_competencia_nfse', lambda *a, **k: '2026-10-31')
        chamadas = self._capturar_post(monkeypatch, _RespFake(200, {'id': 'inv_1', 'status': 'SCHEDULED'}))
        BillingService._agendar_nota_fiscal('pay_1', 25.0)
        assert chamadas[0]['json']['effectiveDate'] == '2026-10-31'
        assert chamadas[0]['json']['payment'] == 'pay_1'

    def test_loga_id_e_status_quando_asaas_aceita(self, app, monkeypatch, caplog):
        self._capturar_post(monkeypatch, _RespFake(200, {'id': 'inv_abc', 'status': 'SCHEDULED'}))
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            BillingService._agendar_nota_fiscal('pay_2', 25.0)
        assert 'invoice=inv_abc' in caplog.text
        assert 'status=SCHEDULED' in caplog.text

    def test_resposta_sem_json_nao_quebra(self, app, monkeypatch, caplog):
        self._capturar_post(monkeypatch, _RespFake(200, None))
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            BillingService._agendar_nota_fiscal('pay_3', 25.0)
        assert 'Nota fiscal agendada no Asaas' in caplog.text

    def test_erro_http_continua_logando_como_erro(self, app, monkeypatch, caplog):
        self._capturar_post(monkeypatch, _RespFake(400, None, 'recusado'))
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            BillingService._agendar_nota_fiscal('pay_4', 25.0)
        assert 'Asaas respondeu 400 ao agendar nota fiscal' in caplog.text
        assert 'Nota fiscal agendada no Asaas' not in caplog.text


class TestWebhookInvoice:
    PAYLOAD_ERRO = {
        'id': 'evt_inv_erro',
        'event': 'INVOICE_ERROR',
        'invoice': {
            'id': 'inv_9',
            'status': 'ERROR',
            'payment': 'pay_9',
            'statusDescription': 'Falha ao carregar opcao simples nacional',
        },
    }

    def test_invoice_error_e_logado_como_erro_com_a_descricao(self, app, caplog):
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            assert BillingService.processar_webhook(dict(self.PAYLOAD_ERRO)) is True
        registros = [r for r in caplog.records if 'Nota fiscal Asaas' in r.getMessage()]
        assert len(registros) == 1
        assert registros[0].levelno == logging.ERROR
        assert 'Falha ao carregar opcao simples nacional' in registros[0].getMessage()
        assert 'invoice=inv_9' in registros[0].getMessage()

    def test_nao_gera_aviso_de_assinatura_inexistente(self, app, caplog):
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            BillingService.processar_webhook(dict(self.PAYLOAD_ERRO))
        assert 'sem Assinatura correspondente' not in caplog.text

    def test_grava_event_id_e_e_idempotente(self, app, caplog):
        assert BillingService.processar_webhook(dict(self.PAYLOAD_ERRO)) is True
        assert EventoWebhookAsaas.query.filter_by(event_id='evt_inv_erro').count() == 1
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            assert BillingService.processar_webhook(dict(self.PAYLOAD_ERRO)) is True
        assert EventoWebhookAsaas.query.filter_by(event_id='evt_inv_erro').count() == 1
        assert 'já processado antes' in caplog.text

    def test_invoice_autorizada_e_logada_como_info(self, app, caplog):
        payload = {'id': 'evt_inv_ok', 'event': 'INVOICE_AUTHORIZED',
                   'invoice': {'id': 'inv_10', 'status': 'AUTHORIZED', 'payment': 'pay_10', 'number': '123'}}
        with caplog.at_level(logging.INFO, logger='services.billing_service'):
            assert BillingService.processar_webhook(payload) is True
        registros = [r for r in caplog.records if 'Nota fiscal Asaas' in r.getMessage()]
        assert registros and registros[0].levelno == logging.INFO

    def test_payload_invoice_malformado_nao_quebra(self, app):
        payload = {'id': 'evt_inv_mal', 'event': 'INVOICE_UPDATED', 'invoice': 'texto'}
        assert BillingService.processar_webhook(payload) is True

def _usuario(username, is_admin=False):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario='professor', is_admin=is_admin)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.commit()
    return user


def _evento_erro(evt='evt_nf_1', invoice_id='inv_77', motivo='Falha ao carregar opcao simples nacional', **extra):
    invoice = {'id': invoice_id, 'status': 'ERROR', 'payment': 'pay_77', 'statusDescription': motivo}
    invoice.update(extra)
    return {'id': evt, 'event': 'INVOICE_ERROR', 'invoice': invoice}


def _notificacoes_de(usuario, tipo='nota_fiscal_erro'):
    return Notificacao.query.filter_by(destinatario_id=usuario.id, tipo=tipo).all()


class TestNotificacaoAdminErroNota:
    """INVOICE_ERROR vira notificação in-app (sino) pros admins."""

    def test_notifica_o_admin_com_motivo_nota_e_pagamento(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        assert BillingService.processar_webhook(_evento_erro()) is True
        notificacoes = _notificacoes_de(admin)
        assert len(notificacoes) == 1
        n = notificacoes[0]
        assert n.titulo == 'Erro na emissão de nota fiscal'
        assert 'Falha ao carregar opcao simples nacional' in n.mensagem
        assert 'inv_77' in n.mensagem and 'pay_77' in n.mensagem
        assert n.lida is False
        assert n.remetente_id is None

    def test_notifica_todos_os_admins_e_so_eles(self, app):
        admin_extra = _usuario('admin_extra', is_admin=True)
        comum = _usuario('professor_comum')
        BillingService.processar_webhook(_evento_erro())
        assert len(_notificacoes_de(admin_extra)) == 1
        assert len(_notificacoes_de(User.query.filter_by(username='admin').first())) == 1
        assert Notificacao.query.filter_by(destinatario_id=comum.id).count() == 0

    def test_nota_autorizada_nao_notifica(self, app):
        payload = {'id': 'evt_ok', 'event': 'INVOICE_AUTHORIZED',
                   'invoice': {'id': 'inv_1', 'status': 'AUTHORIZED', 'payment': 'pay_1', 'number': '12'}}
        assert BillingService.processar_webhook(payload) is True
        assert Notificacao.query.filter_by(tipo='nota_fiscal_erro').count() == 0

    def test_status_error_em_outro_evento_tambem_notifica(self, app):
        payload = _evento_erro(evt='evt_upd')
        payload['event'] = 'INVOICE_UPDATED'
        BillingService.processar_webhook(payload)
        assert Notificacao.query.filter_by(tipo='nota_fiscal_erro').count() >= 1

    def test_reenvio_do_mesmo_evento_nao_duplica(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        BillingService.processar_webhook(_evento_erro())
        BillingService.processar_webhook(_evento_erro())
        assert len(_notificacoes_de(admin)) == 1
        assert _notificacoes_de(admin)[0].ocorrencias == 1

    def test_mesma_nota_em_eventos_diferentes_agrupa_com_contador(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        BillingService.processar_webhook(_evento_erro(evt='evt_a'))
        BillingService.processar_webhook(_evento_erro(evt='evt_b'))
        notificacoes = _notificacoes_de(admin)
        assert len(notificacoes) == 1
        assert notificacoes[0].ocorrencias == 2

    def test_notas_diferentes_geram_notificacoes_separadas(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        BillingService.processar_webhook(_evento_erro(evt='evt_a', invoice_id='inv_A'))
        BillingService.processar_webhook(_evento_erro(evt='evt_b', invoice_id='inv_B'))
        assert len(_notificacoes_de(admin)) == 2

    def test_sem_motivo_no_evento_usa_texto_padrao(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        payload = _evento_erro()
        del payload['invoice']['statusDescription']
        BillingService.processar_webhook(payload)
        assert 'sem detalhes no evento' in _notificacoes_de(admin)[0].mensagem

    def test_sem_nenhum_admin_nao_quebra_e_avisa_no_log(self, app, caplog):
        User.query.filter_by(is_admin=True).delete()
        db.session.commit()
        with caplog.at_level(logging.WARNING, logger='services.billing_service'):
            assert BillingService.processar_webhook(_evento_erro()) is True
        assert 'nenhum usuário admin para notificar' in caplog.text
        assert EventoWebhookAsaas.query.filter_by(event_id='evt_nf_1').count() == 1

    def test_falha_ao_notificar_nao_derruba_o_webhook(self, app, monkeypatch, caplog):
        def _explode(*a, **k):
            raise RuntimeError('banco fora')

        monkeypatch.setattr(NotificacaoService, 'criar_ou_agrupar', staticmethod(_explode))
        with caplog.at_level(logging.ERROR, logger='services.billing_service'):
            assert BillingService.processar_webhook(_evento_erro()) is True
        assert 'Falha ao notificar os admins' in caplog.text
        assert EventoWebhookAsaas.query.filter_by(event_id='evt_nf_1').count() == 1

    def test_motivo_gigante_e_truncado_sem_estourar_o_limite(self, app):
        admin = User.query.filter_by(is_admin=True).first()
        BillingService.processar_webhook(_evento_erro(motivo='x' * 5000))
        assert len(_notificacoes_de(admin)[0].mensagem) <= 300


class TestNotificacaoAparecePraAdmin:
    """O admin logado enxerga a notificação no sino (API) e na tela."""

    def test_aparece_na_api_do_sino_e_na_tela(self, auth_client):
        with auth_client.application.app_context():
            BillingService.processar_webhook(_evento_erro())

        api = auth_client.get('/api/notificacoes')
        assert api.status_code == 200
        corpo = api.get_json()
        tipos = [n['tipo'] for n in corpo['notificacoes']]
        assert 'nota_fiscal_erro' in tipos
        assert corpo['nao_lidas'] >= 1

        tela = auth_client.get('/notificacoes')
        assert tela.status_code == 200
        html = tela.get_data(as_text=True)
        assert 'Erro na emissão de nota fiscal' in html
        assert 'bi-exclamation-triangle' in html