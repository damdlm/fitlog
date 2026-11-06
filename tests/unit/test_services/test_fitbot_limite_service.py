"""Limites e números do FitBot (services/fitbot_limite_service.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from models import db, User, FitBotMensagem, FitBotChamada
from services import fitbot_limite_service as mod
from services.fitbot_limite_service import FitBotLimiteService, _normalizar_limite, _inicio_do_dia_utc


def _usuario(username, is_admin=False):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno', is_admin=is_admin)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _mensagens(user, n, quando=None):
    for _ in range(n):
        db.session.add(FitBotMensagem(user_id=user.id, criado_em=quando or datetime.now(timezone.utc)))
    db.session.commit()


class TestNormalizarLimite:
    @pytest.mark.parametrize('bruto, esperado', [(None, None), ('', None), ('  ', None), ('0', None), (0, None),
                                                  ('30', 30), (' 15 ', 15), (100, 100)])
    def test_valores_validos(self, bruto, esperado):
        assert _normalizar_limite(bruto) == esperado

    @pytest.mark.parametrize('bruto', ['abc', '-1', '2.5', '9999999'])
    def test_valores_invalidos(self, bruto):
        with pytest.raises(ValueError):
            _normalizar_limite(bruto)


class TestConfiguracao:
    def test_padrao_e_30_por_dia_sem_teto(self, app):
        assert FitBotLimiteService.get_limites() == {'diario': 30, 'mensal': None}

    def test_salvar_e_ler_de_novo_sem_esperar_o_cache(self, app):
        FitBotLimiteService.get_limites()  # popula o cache
        FitBotLimiteService.set_limites('5', '1000')
        assert FitBotLimiteService.get_limites() == {'diario': 5, 'mensal': 1000}
        FitBotLimiteService.set_limites('', '0')
        assert FitBotLimiteService.get_limites() == {'diario': None, 'mensal': None}

    def test_valor_invalido_nao_salva_nada(self, app):
        FitBotLimiteService.set_limites('10', '')
        with pytest.raises(ValueError):
            FitBotLimiteService.set_limites('10', 'muito')
        assert FitBotLimiteService.get_limites() == {'diario': 10, 'mensal': None}


class TestVerificar:
    def test_bloqueia_ao_chegar_na_cota_diaria(self, app):
        FitBotLimiteService.set_limites('3', '')
        u = _usuario('cota_dia')
        _mensagens(u, 2)
        assert FitBotLimiteService.verificar(u) is None
        _mensagens(u, 1)
        bloqueio = FitBotLimiteService.verificar(u)
        assert bloqueio['motivo'] == 'diario' and '3 mensagens' in bloqueio['resposta']

    def test_cota_e_por_usuario(self, app):
        FitBotLimiteService.set_limites('2', '')
        a, b = _usuario('cota_a'), _usuario('cota_b')
        _mensagens(a, 2)
        assert FitBotLimiteService.verificar(a) is not None
        assert FitBotLimiteService.verificar(b) is None

    def test_mensagens_de_ontem_nao_contam(self, app):
        FitBotLimiteService.set_limites('2', '')
        u = _usuario('cota_ontem')
        _mensagens(u, 5, quando=_inicio_do_dia_utc() - timedelta(minutes=1))
        assert FitBotLimiteService.verificar(u) is None

    def test_dia_vira_a_meia_noite_de_brasilia(self, app):
        # 23h30 de Brasília = 02h30 UTC do dia seguinte: ainda é "hoje" no Brasil.
        agora = datetime(2026, 11, 7, 2, 30, tzinfo=timezone.utc)
        assert _inicio_do_dia_utc(agora) == datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)

    def test_teto_mensal_bloqueia_todo_mundo(self, app):
        FitBotLimiteService.set_limites('', '4')
        a, b = _usuario('teto_a'), _usuario('teto_b')
        _mensagens(a, 4)
        bloqueio = FitBotLimiteService.verificar(b)
        assert bloqueio['motivo'] == 'mensal'

    def test_admin_nao_tem_limite(self, app):
        FitBotLimiteService.set_limites('1', '1')
        adm = _usuario('adm_fitbot', is_admin=True)
        _mensagens(adm, 3)
        assert FitBotLimiteService.verificar(adm) is None

    def test_sem_limite_nunca_bloqueia(self, app):
        FitBotLimiteService.set_limites('', '')
        u = _usuario('sem_limite')
        _mensagens(u, 50)
        assert FitBotLimiteService.verificar(u) is None


class TestEstatisticas:
    def test_numeros_do_painel(self, app):
        FitBotLimiteService.set_limites('2', '10')
        a, b = _usuario('est_a'), _usuario('est_b')
        _mensagens(a, 3)
        _mensagens(b, 1)
        db.session.add(FitBotChamada(provedor='groq', sucesso=True, duracao_ms=300,
                                     tokens_entrada=1_000_000, tokens_saida=500_000))
        db.session.commit()

        e = FitBotLimiteService.estatisticas()

        assert e['mensagens_hoje'] == 4 and e['mensagens_mes'] == 4
        assert e['usuarios_hoje'] == 2 and e['usuarios_mes'] == 2
        assert e['usuarios_no_limite_hoje'] == 1          # só "a" passou de 2
        assert e['restante_mes'] == 6
        assert e['top_usuarios_mes'][0]['qtd'] == 3
        assert e['serie_30_dias'][-1]['qtd'] == 4 and len(e['serie_30_dias']) == 30
        # 1M entrada x 0,15 + 0,5M saída x 0,60 = 0,45
        assert e['custo_mes_usd'] == pytest.approx(0.45)
        assert e['custo_por_provedor_mes'][0]['provedor'] == 'groq'

    def test_precos_podem_vir_do_ambiente(self, app, monkeypatch):
        monkeypatch.setenv('FITBOT_PRECOS_JSON', '{"groq": [1, 2]}')
        db.session.add(FitBotChamada(provedor='groq', sucesso=True, duracao_ms=1,
                                     tokens_entrada=1_000_000, tokens_saida=1_000_000))
        db.session.commit()
        assert FitBotLimiteService.estatisticas()['custo_mes_usd'] == pytest.approx(3.0)

    def test_precos_invalidos_no_ambiente_usam_o_padrao(self, app, monkeypatch):
        monkeypatch.setenv('FITBOT_PRECOS_JSON', 'isso não é json')
        assert mod._precos()['groq'] == mod.PRECOS_PADRAO_USD_POR_MILHAO['groq']

    def test_registrar_nunca_derruba_a_resposta(self, app, monkeypatch):
        monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('db fora')))
        FitBotLimiteService.registrar(12345)  # não levanta
