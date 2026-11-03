"""
Testes dos comandos `flask ...` definidos em app.py -- os "wrappers" que o
Railway Cron executa (fitlog-cron-*). Os SERVIÇOS por trás deles já têm teste;
aqui o alvo é a casca: texto impresso, código de saída e isolamento de falhas.

Por que importa: o Railway só enxerga o código de saída. Um wrapper que engole
exceção (exit 0) faz o cron aparecer como "Last run succeeded" mesmo falhando
-- exatamente o problema que utils/cron_utils.executar_etapas existe pra evitar.
Também cobre `criar-admin-inicial`, o único jeito suportado de criar o 1º admin
em produção sem deixar ADMIN_PASSWORD no processo web.
"""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models import db, User, Notificacao, CrashLog
from services.billing_service import BillingService
from services.crash_log_service import CrashLogService
from services.geolocalizacao_service import GeolocalizacaoService
from services.historico_metricas_service import HistoricoMetricasService
from services.notificacao_service import NotificacaoService
from services.versao_service import VersaoService


def _invoke(app, *args, input=None):
    return app.test_cli_runner().invoke(args=list(args), input=input)


def _boom(*a, **kw):
    raise RuntimeError('boom')


# ------------------------------------------------------------------
# todos os comandos que os crons/operação dependem continuam registrados
# ------------------------------------------------------------------

COMANDOS_ESPERADOS = {
    'billing-expirar-carencias',          # cron billing-carencias (de hora em hora)
    'billing-rotina-diaria',              # cron billing-tiers (diário)
    'billing-verificar-tiers',
    'billing-notificar-vencimentos',
    'billing-notificar-tier-desatualizado',
    'billing-reiniciar-trials',
    'notificacoes-limpar',                # cron notificacoes-limpar (semanal)
    'versoes-alertar-expiracao',          # cron versoes-expiracao (diário)
    'monitoramento-capturar-snapshot',    # cron monitoramento-snapshot (10 min)
    'geocodificar-professores',           # cron geocodificar-professores (30 min)
    'criar-admin-inicial',
}


def test_todos_os_comandos_de_cron_estao_registrados(app):
    """Renomear/remover um comando faz o cron do Railway passar a falhar em
    silêncio ('No such command'); este teste quebra antes do deploy."""
    assert COMANDOS_ESPERADOS <= set(app.cli.commands)


# ------------------------------------------------------------------
# criar-admin-inicial
# ------------------------------------------------------------------

SENHA_OK = 'senha-bem-longa-123'


@pytest.fixture
def banco_sem_usuarios(app):
    """create_app já semeia um admin em teste; o comando só age em banco vazio."""
    User.query.delete()
    db.session.commit()
    assert User.query.first() is None


class TestCriarAdminInicial:

    def test_nao_faz_nada_se_ja_existe_algum_usuario(self, app):
        antes = User.query.count()

        r = _invoke(app, 'criar-admin-inicial')

        assert r.exit_code == 0
        assert 'nada a fazer' in r.output
        assert User.query.count() == antes
        assert 'ADMIN_PASSWORD' not in os.environ

    def test_nao_pede_senha_quando_ja_existe_usuario(self, app):
        r = _invoke(app, 'criar-admin-inicial', input='')
        assert r.exit_code == 0
        assert 'Senha do admin' not in r.output

    def test_cria_admin_com_a_senha_digitada(self, app, banco_sem_usuarios):
        r = _invoke(app, 'criar-admin-inicial', input=f'{SENHA_OK}\n{SENHA_OK}\n')

        assert r.exit_code == 0, r.output
        assert 'Admin criado com sucesso.' in r.output
        admin = User.query.filter_by(username='admin').one()
        assert admin.is_admin is True
        assert admin.check_password(SENHA_OK)

    def test_senha_nao_aparece_no_terminal(self, app, banco_sem_usuarios):
        r = _invoke(app, 'criar-admin-inicial', input=f'{SENHA_OK}\n{SENHA_OK}\n')
        assert SENHA_OK not in r.output

    def test_nao_deixa_ADMIN_PASSWORD_no_ambiente_do_processo(self, app, banco_sem_usuarios):
        _invoke(app, 'criar-admin-inicial', input=f'{SENHA_OK}\n{SENHA_OK}\n')
        assert 'ADMIN_PASSWORD' not in os.environ

    def test_senha_curta_nao_cria_admin_e_avisa(self, app, banco_sem_usuarios):
        curta = 'curta123'                       # 8 caracteres (< 12)

        r = _invoke(app, 'criar-admin-inicial', input=f'{curta}\n{curta}\n')

        assert 'Não foi possível criar o admin' in r.output
        assert User.query.first() is None
        assert 'ADMIN_PASSWORD' not in os.environ

    def test_confirmacao_diferente_pede_de_novo_e_aceita_o_par_correto(self, app, banco_sem_usuarios):
        entrada = f'{SENHA_OK}\noutra-senha-qualquer\n{SENHA_OK}\n{SENHA_OK}\n'

        r = _invoke(app, 'criar-admin-inicial', input=entrada)

        assert 'do not match' in r.output.lower() or 'não' in r.output.lower()
        assert 'Admin criado com sucesso.' in r.output
        assert User.query.filter_by(username='admin').one().check_password(SENHA_OK)

    def test_abortar_o_prompt_nao_cria_nada_nem_vaza_a_variavel(self, app, banco_sem_usuarios):
        r = _invoke(app, 'criar-admin-inicial', input='')           # EOF no prompt

        assert r.exit_code != 0
        assert User.query.first() is None
        assert 'ADMIN_PASSWORD' not in os.environ

    def test_variavel_e_removida_mesmo_se_a_criacao_levantar_excecao(self, app, banco_sem_usuarios, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, '_criar_admin_inicial', _boom)

        r = _invoke(app, 'criar-admin-inicial', input=f'{SENHA_OK}\n{SENHA_OK}\n')

        assert r.exit_code != 0
        assert 'ADMIN_PASSWORD' not in os.environ


# ------------------------------------------------------------------
# billing-* (casca dos comandos)
# ------------------------------------------------------------------

def _mudanca(prof_id, atual, novo):
    cod = lambda c: SimpleNamespace(codigo=c) if c else None
    return {'professor': SimpleNamespace(id=prof_id), 'tier_atual': cod(atual), 'tier_novo': cod(novo)}


class TestBillingCli:

    def test_notificar_vencimentos_imprime_o_total(self, app, monkeypatch):
        monkeypatch.setattr(BillingService, 'notificar_vencimentos_pendentes', staticmethod(lambda: 7))

        r = _invoke(app, 'billing-notificar-vencimentos')

        assert r.exit_code == 0
        assert '7 notificação(ões) de vencimento enviada(s).' in r.output

    def test_notificar_tier_desatualizado_imprime_o_total(self, app, monkeypatch):
        monkeypatch.setattr(BillingService, 'notificar_professores_tier_desatualizado', staticmethod(lambda: 3))

        r = _invoke(app, 'billing-notificar-tier-desatualizado')

        assert r.exit_code == 0
        assert '3 notificação(ões) de tier desatualizado enviada(s).' in r.output

    def test_verificar_tiers_lista_cada_mudanca_e_chama_de_gratuito_quem_nao_tem_tier(self, app, monkeypatch):
        monkeypatch.setattr(
            BillingService, 'verificar_mudancas_tier_professores',
            staticmethod(lambda: [_mudanca(5, 'professor_pro', 'professor_premium'),
                                  _mudanca(9, None, 'professor_pro'),
                                  _mudanca(11, 'professor_pro', None)]),
        )

        r = _invoke(app, 'billing-verificar-tiers')

        assert r.exit_code == 0
        assert 'professor_id=5 professor_pro -> professor_premium' in r.output
        assert 'professor_id=9 gratuito -> professor_pro' in r.output
        assert 'professor_id=11 professor_pro -> gratuito' in r.output
        assert 'Nenhuma mudança' not in r.output

    def test_rotina_diaria_imprime_resumo_das_tres_etapas(self, app, monkeypatch):
        monkeypatch.setattr(BillingService, 'verificar_mudancas_tier_professores',
                            staticmethod(lambda: [_mudanca(5, 'professor_pro', 'professor_premium'),
                                                  _mudanca(9, None, 'professor_pro')]))
        monkeypatch.setattr(BillingService, 'notificar_professores_tier_desatualizado', staticmethod(lambda: 4))
        monkeypatch.setattr(BillingService, 'notificar_vencimentos_pendentes', staticmethod(lambda: 6))

        r = _invoke(app, 'billing-rotina-diaria')

        assert r.exit_code == 0, r.output
        assert '2 mudança(s) de tier pendente(s).' in r.output
        assert '4 notificação(ões) de tier desatualizado enviada(s).' in r.output
        assert '6 notificação(ões) de vencimento enviada(s).' in r.output

    def test_rotina_diaria_falha_na_primeira_etapa_ainda_roda_as_outras_e_sai_com_1(self, app, monkeypatch):
        rodou = []
        monkeypatch.setattr(BillingService, 'verificar_mudancas_tier_professores', staticmethod(_boom))
        monkeypatch.setattr(BillingService, 'notificar_professores_tier_desatualizado',
                            staticmethod(lambda: rodou.append('tier') or 0))
        monkeypatch.setattr(BillingService, 'notificar_vencimentos_pendentes',
                            staticmethod(lambda: rodou.append('venc') or 0))

        r = _invoke(app, 'billing-rotina-diaria')

        assert r.exit_code == 1
        assert rodou == ['tier', 'venc']
        assert 'FALHA nas etapas: verificar_tiers' in r.output

    def test_rotina_diaria_lista_todas_as_etapas_que_falharam(self, app, monkeypatch):
        monkeypatch.setattr(BillingService, 'verificar_mudancas_tier_professores', staticmethod(_boom))
        monkeypatch.setattr(BillingService, 'notificar_vencimentos_pendentes', staticmethod(_boom))
        monkeypatch.setattr(BillingService, 'notificar_professores_tier_desatualizado', staticmethod(lambda: 0))

        r = _invoke(app, 'billing-rotina-diaria')

        assert r.exit_code == 1
        assert 'verificar_tiers' in r.output and 'notificar_vencimentos' in r.output

    def test_expirar_carencias_imprime_contagens_e_lista_etapas_que_falharam(self, app, monkeypatch):
        monkeypatch.setattr(BillingService, 'expirar_pix_vencidos', staticmethod(lambda: 2))
        monkeypatch.setattr(BillingService, 'expirar_carencias_vencidas', staticmethod(_boom))
        monkeypatch.setattr(BillingService, 'finalizar_cancelamentos_agendados', staticmethod(lambda: 5))

        r = _invoke(app, 'billing-expirar-carencias')

        assert r.exit_code == 1
        assert '2 assinatura(s) Pix movida(s) para past_due' in r.output
        assert '5 cancelamento(s) agendado(s) finalizado(s).' in r.output       # roda mesmo após falha anterior
        assert 'FALHA nas etapas: expirar_carencias_vencidas' in r.output

    def test_expirar_carencias_sucesso_sai_com_zero(self, app, monkeypatch):
        for nome in ('expirar_pix_vencidos', 'expirar_carencias_vencidas', 'finalizar_cancelamentos_agendados'):
            monkeypatch.setattr(BillingService, nome, staticmethod(lambda: 1))

        r = _invoke(app, 'billing-expirar-carencias')

        assert r.exit_code == 0
        assert 'FALHA' not in r.output

    @pytest.mark.parametrize('dias', ['0', '366', '-5', 'abc'])
    def test_reiniciar_trials_rejeita_prazo_fora_de_1_a_365(self, app, dias):
        r = _invoke(app, 'billing-reiniciar-trials', '--dias', dias)
        assert r.exit_code == 2


# ------------------------------------------------------------------
# notificacoes-limpar
# ------------------------------------------------------------------

class TestNotificacoesLimpar:

    def test_imprime_o_total_de_cada_limpeza(self, app, monkeypatch):
        monkeypatch.setattr(NotificacaoService, 'limpar_antigas', staticmethod(lambda: 12))
        monkeypatch.setattr(CrashLogService, 'limpar_antigas', staticmethod(lambda: 3))

        r = _invoke(app, 'notificacoes-limpar')

        assert r.exit_code == 0
        assert '12 notificação(ões) lida(s) antiga(s) removida(s).' in r.output
        assert '3 crash log(s) antigo(s) removido(s).' in r.output

    def test_falha_nas_notificacoes_nao_impede_a_limpeza_dos_crash_logs(self, app, monkeypatch):
        monkeypatch.setattr(NotificacaoService, 'limpar_antigas', staticmethod(lambda: None))
        monkeypatch.setattr(CrashLogService, 'limpar_antigas', staticmethod(lambda: 4))

        r = _invoke(app, 'notificacoes-limpar')

        assert 'Falha ao limpar notificações antigas' in r.output
        assert '4 crash log(s) antigo(s) removido(s).' in r.output

    def test_falha_nos_crash_logs_e_reportada(self, app, monkeypatch):
        monkeypatch.setattr(NotificacaoService, 'limpar_antigas', staticmethod(lambda: 1))
        monkeypatch.setattr(CrashLogService, 'limpar_antigas', staticmethod(lambda: None))

        r = _invoke(app, 'notificacoes-limpar')

        assert '1 notificação(ões) lida(s) antiga(s) removida(s).' in r.output
        assert 'Falha ao limpar crash logs antigos' in r.output

    def test_integracao_remove_so_lidas_antigas_e_crash_logs_vencidos(self, app):
        agora = datetime.now(timezone.utc)
        dest = User(username='dest', email='dest@teste.com', tipo_usuario='aluno')
        dest.set_password('SenhaForte123!')
        db.session.add(dest)
        db.session.commit()

        def _notif(titulo, lida, dias):
            n = Notificacao(destinatario_id=dest.id, tipo='treino_editado', titulo=titulo,
                            mensagem='m', lida=lida, created_at=agora - timedelta(days=dias))
            db.session.add(n)

        _notif('lida_antiga', True, 120)           # única que deve sumir
        _notif('lida_recente', True, 10)
        _notif('nao_lida_antiga', False, 120)      # nunca apaga não lida
        db.session.add(CrashLog(origem='backend', tipo='ValueError', mensagem='m', criado_em=agora - timedelta(days=45)))
        db.session.add(CrashLog(origem='backend', tipo='KeyError', mensagem='m', criado_em=agora - timedelta(days=2)))
        db.session.commit()

        r = _invoke(app, 'notificacoes-limpar')

        assert r.exit_code == 0, r.output
        assert {n.titulo for n in Notificacao.query.all()} == {'lida_recente', 'nao_lida_antiga'}
        assert [c.tipo for c in CrashLog.query.all()] == ['KeyError']


# ------------------------------------------------------------------
# versoes-alertar-expiracao / geocodificar-professores
# ------------------------------------------------------------------

class TestOutrosCrons:

    def test_versoes_alertar_expiracao_imprime_o_total(self, app, monkeypatch):
        monkeypatch.setattr(VersaoService, 'alertar_expiracoes', staticmethod(lambda: 9))

        r = _invoke(app, 'versoes-alertar-expiracao')

        assert r.exit_code == 0
        assert '9 versão(ões) alertada(s) por expiração próxima.' in r.output

    def test_versoes_alertar_expiracao_com_banco_vazio_roda_de_verdade(self, app):
        r = _invoke(app, 'versoes-alertar-expiracao')
        assert r.exit_code == 0, r.output
        assert '0 versão(ões) alertada(s)' in r.output

    def test_geocodificar_professores_imprime_o_total(self, app, monkeypatch):
        monkeypatch.setattr(GeolocalizacaoService, 'geocodificar_pendentes', staticmethod(lambda *a, **k: 4))

        r = _invoke(app, 'geocodificar-professores')

        assert r.exit_code == 0
        assert '4 professor(es) geocodificado(s).' in r.output

    def test_geocodificar_professores_sem_pendentes_roda_de_verdade_sem_rede(self, app):
        r = _invoke(app, 'geocodificar-professores')
        assert r.exit_code == 0, r.output
        assert '0 professor(es) geocodificado(s).' in r.output


# ------------------------------------------------------------------
# monitoramento-capturar-snapshot
# ------------------------------------------------------------------

class TestMonitoramentoSnapshot:

    def test_sucesso_com_limpeza(self, app, monkeypatch):
        monkeypatch.setattr(HistoricoMetricasService, 'capturar_snapshot', staticmethod(lambda: True))
        monkeypatch.setattr(HistoricoMetricasService, 'limpar_antigas', staticmethod(lambda: 5))

        r = _invoke(app, 'monitoramento-capturar-snapshot')

        assert r.exit_code == 0
        assert 'Snapshot de métricas capturado.' in r.output
        assert '5 snapshot(s) antigo(s) removido(s).' in r.output

    def test_falha_na_captura_e_reportada_mas_a_limpeza_ainda_roda(self, app, monkeypatch):
        limpou = []
        monkeypatch.setattr(HistoricoMetricasService, 'capturar_snapshot', staticmethod(lambda: False))
        monkeypatch.setattr(HistoricoMetricasService, 'limpar_antigas',
                            staticmethod(lambda: limpou.append(1) or 0))

        r = _invoke(app, 'monitoramento-capturar-snapshot')

        assert 'Falha ao capturar snapshot de métricas' in r.output
        assert 'Snapshot de métricas capturado.' not in r.output
        assert limpou == [1]

    def test_limpeza_que_falha_retorna_none_e_nao_imprime_total(self, app, monkeypatch):
        monkeypatch.setattr(HistoricoMetricasService, 'capturar_snapshot', staticmethod(lambda: True))
        monkeypatch.setattr(HistoricoMetricasService, 'limpar_antigas', staticmethod(lambda: None))

        r = _invoke(app, 'monitoramento-capturar-snapshot')

        assert r.exit_code == 0
        assert 'Snapshot de métricas capturado.' in r.output
        assert 'antigo(s) removido(s)' not in r.output
