"""Jobs periódicos de cobrança (cron): modo grátis, corrida com o webhook,
recuperação de avisos perdidos, reinício de trials e isolamento de falhas."""
import itertools
from datetime import datetime, timedelta, timezone

import pytest

from models import db, User, Assinatura, Notificacao
from services.billing_service import BillingService
from services.configuracao_service import ConfiguracaoService
from utils.cron_utils import executar_etapas


_SEQ = itertools.count(1)


def _agora():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _assinatura(status, **campos):
    n = next(_SEQ)
    user = User(username=f'cron{n}', email=f'cron{n}@teste.com', tipo_usuario='aluno')
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    a = Assinatura(usuario_id=user.id, status=status, **campos)
    db.session.add(a)
    db.session.commit()
    return a


def _modo_gratis():
    ConfiguracaoService.set_cobranca_ativa(False)


# ---------------------------------------------------------------- modo grátis

def test_modo_gratis_nao_expira_carencia(app):
    a = _assinatura('past_due', carencia_termina_em=_agora() - timedelta(days=1))
    _modo_gratis()
    assert BillingService.expirar_carencias_vencidas() == 0
    db.session.refresh(a)
    assert a.status == 'past_due'


def test_modo_gratis_nao_expira_pix(app):
    a = _assinatura('active', forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(days=2))
    _modo_gratis()
    assert BillingService.expirar_pix_vencidos() == 0
    db.session.refresh(a)
    assert a.status == 'active' and a.vencido_em is None


def test_modo_gratis_nao_notifica_vencimento_nem_tier(app):
    _assinatura('past_due', vencido_em=_agora() - timedelta(days=3),
                carencia_termina_em=_agora() + timedelta(days=1))
    _modo_gratis()
    assert BillingService.notificar_vencimentos_pendentes() == 0
    assert BillingService.notificar_professores_tier_desatualizado() == 0
    assert BillingService.verificar_mudancas_tier_professores() == []
    assert Notificacao.query.count() == 0


def test_modo_gratis_ainda_finaliza_cancelamento_pedido_pelo_usuario(app):
    a = _assinatura('active', cancelado_em=_agora() - timedelta(days=5),
                    periodo_atual_fim=_agora() - timedelta(days=1))
    _modo_gratis()
    assert BillingService.finalizar_cancelamentos_agendados() == 1
    db.session.refresh(a)
    assert a.status == 'canceled'


def test_cobranca_ativa_mantem_comportamento_normal(app):
    bloquear = _assinatura('past_due', carencia_termina_em=_agora() - timedelta(hours=1))
    pix = _assinatura('active', forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(hours=1))
    assert BillingService.expirar_carencias_vencidas() == 1
    assert BillingService.expirar_pix_vencidos() == 1
    db.session.refresh(bloquear)
    db.session.refresh(pix)
    assert bloquear.status == 'blocked'
    assert pix.status == 'past_due'
    assert pix.vencido_em is not None and pix.ultima_notificacao_vencimento_dias == 0
    assert _utc(pix.carencia_termina_em) > _agora()


# ------------------------------------------------- corrida cron x webhook

@pytest.mark.parametrize('job, fabrica', [
    ('expirar_carencias_vencidas',
     lambda: _assinatura('past_due', carencia_termina_em=_agora() - timedelta(hours=1))),
    ('expirar_pix_vencidos',
     lambda: _assinatura('active', forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(hours=1))),
])
def test_pagamento_confirmado_no_meio_do_job_nao_e_sobrescrito(app, monkeypatch, job, fabrica):
    a = fabrica()
    original = BillingService._transicionar

    def webhook_chega_antes_da_escrita(assinatura_id, filtros, novo_status):
        # simula o webhook confirmando o pagamento entre o SELECT e o UPDATE do job
        Assinatura.query.filter_by(id=assinatura_id).update(
            {'status': 'active', 'carencia_termina_em': None,
             'periodo_atual_fim': _agora() + timedelta(days=30)}, synchronize_session=False)
        db.session.commit()
        return original(assinatura_id, filtros, novo_status)

    monkeypatch.setattr(BillingService, '_transicionar', staticmethod(webhook_chega_antes_da_escrita))
    assert getattr(BillingService, job)() == 0
    db.session.refresh(a)
    assert a.status == 'active'


# ------------------------------------------- régua de vencimento (marcos)

@pytest.mark.parametrize('dias, esperado', [
    (0, None), (1, 1), (2, 2), (3, 3), (4, 3), (5, 3), (6, 6), (17, 15), (18, 18),
    (19, 18), (27, 18), (28, 28), (37, 28), (38, 38),
])
def test_marco_notificacao_vencimento(dias, esperado):
    assert BillingService._marco_notificacao_vencimento(dias) == esperado


def test_aviso_perdido_e_recuperado_no_proximo_run(app):
    # dia 6 do atraso passou sem cron; só o dia 3 tinha sido avisado
    a = _assinatura('past_due', vencido_em=_agora() - timedelta(days=7),
                    carencia_termina_em=_agora() + timedelta(days=5),
                    ultima_notificacao_vencimento_dias=3)
    assert BillingService.notificar_vencimentos_pendentes() == 1
    db.session.refresh(a)
    assert a.ultima_notificacao_vencimento_dias == 6
    assert BillingService.notificar_vencimentos_pendentes() == 0  # idempotente


def test_entre_marcos_nao_notifica(app):
    _assinatura('past_due', vencido_em=_agora() - timedelta(days=5),
                carencia_termina_em=_agora() + timedelta(days=5),
                ultima_notificacao_vencimento_dias=3)
    assert BillingService.notificar_vencimentos_pendentes() == 0


# ------------------------------------------------------- reiniciar trials

def test_reiniciar_trials_dry_run_nao_altera(app):
    fim = _agora() - timedelta(days=2)
    a = _assinatura('trialing', trial_termina_em=fim)
    assert BillingService.reiniciar_trials(dias=30) == 1
    db.session.refresh(a)
    assert _utc(a.trial_termina_em) == _utc(fim)


def test_reiniciar_trials_executar_estende_e_nao_encurta(app):
    vencido = _assinatura('trialing', trial_termina_em=_agora() - timedelta(days=2))
    longo_fim = _agora() + timedelta(days=90)
    longo = _assinatura('trialing', trial_termina_em=longo_fim)
    ativo = _assinatura('active')
    assert BillingService.reiniciar_trials(dias=30, executar=True) == 1
    for x in (vencido, longo, ativo):
        db.session.refresh(x)
    assert abs((_utc(vencido.trial_termina_em) - (_agora() + timedelta(days=30))).total_seconds()) < 60
    assert _utc(longo.trial_termina_em) == _utc(longo_fim)
    assert ativo.status == 'active'
    assert vencido.acesso_premium_ativo() is True


# ------------------------------------------------------ cron: etapas isoladas

def test_executar_etapas_isola_falhas(app):
    chamadas = []

    def quebra():
        chamadas.append('quebra')
        raise RuntimeError('boom')

    resultados, falhas = executar_etapas([
        ('a', quebra), ('b', lambda: chamadas.append('b') or 7)])
    assert falhas == ['a']
    assert resultados == {'b': 7}
    assert chamadas == ['quebra', 'b']


def test_rotina_diaria_sai_com_erro_se_uma_etapa_falhar_mas_roda_as_demais(app, monkeypatch):
    rodou = []

    def quebra():
        raise RuntimeError('boom')

    monkeypatch.setattr(BillingService, 'notificar_professores_tier_desatualizado', staticmethod(quebra))
    monkeypatch.setattr(BillingService, 'notificar_vencimentos_pendentes',
                        staticmethod(lambda: rodou.append('vencimentos') or 0))
    result = app.test_cli_runner().invoke(args=['billing-rotina-diaria'])
    assert result.exit_code == 1
    assert rodou == ['vencimentos']


def test_rotina_diaria_ok_sai_com_zero(app):
    result = app.test_cli_runner().invoke(args=['billing-rotina-diaria'])
    assert result.exit_code == 0, result.output


def test_expirar_carencias_cli_sai_com_erro_se_etapa_falhar(app, monkeypatch):
    def quebra():
        raise RuntimeError('boom')

    monkeypatch.setattr(BillingService, 'expirar_pix_vencidos', staticmethod(quebra))
    result = app.test_cli_runner().invoke(args=['billing-expirar-carencias'])
    assert result.exit_code == 1


def test_reiniciar_trials_cli_dry_run_por_padrao(app):
    a = _assinatura('trialing', trial_termina_em=_agora() - timedelta(days=1))
    result = app.test_cli_runner().invoke(args=['billing-reiniciar-trials'])
    assert result.exit_code == 0 and 'dry-run' in result.output
    db.session.refresh(a)
    assert _utc(a.trial_termina_em) < _agora()
    result = app.test_cli_runner().invoke(args=['billing-reiniciar-trials', '--executar', '--dias', '15'])
    assert result.exit_code == 0 and '1 trial(s) reiniciado(s) por 15 dias' in result.output
