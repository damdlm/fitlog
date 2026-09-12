"""Testes para FitBotUsoService -- agregação de uso técnico das IAs do
FitBot (ver models.FitBotChamada e services/fitbot_service.py)."""
from models import db, FitBotChamada
from services.fitbot_uso_service import FitBotUsoService


class TestRegistrar:

    def test_grava_chamada_com_sucesso(self, app):
        with app.app_context():
            FitBotUsoService.registrar('groq', True, 850, tokens_entrada=120, tokens_saida=40)

            chamada = FitBotChamada.query.one()
            assert chamada.provedor == 'groq'
            assert chamada.sucesso is True
            assert chamada.duracao_ms == 850
            assert chamada.tokens_entrada == 120
            assert chamada.tokens_saida == 40
            assert chamada.motivo_falha is None

    def test_grava_chamada_com_falha_e_motivo(self, app):
        with app.app_context():
            FitBotUsoService.registrar('gemini', False, 300, motivo_falha='HTTP 503: fora do ar')

            chamada = FitBotChamada.query.one()
            assert chamada.sucesso is False
            assert chamada.motivo_falha == 'HTTP 503: fora do ar'

    def test_falha_ao_gravar_nao_propaga_excecao(self, app, monkeypatch):
        with app.app_context():
            def commit_quebrado():
                raise RuntimeError("banco fora do ar")
            monkeypatch.setattr(db.session, 'commit', commit_quebrado)

            # Não deve levantar -- best-effort, nunca pode derrubar o FitBot.
            FitBotUsoService.registrar('groq', True, 500)


class TestGetMetricas:

    def test_sem_chamadas_retorna_lista_vazia(self, app):
        with app.app_context():
            resultado = FitBotUsoService.get_metricas(horas=24)

        assert resultado['disponivel'] is True
        assert resultado['total_chamadas'] == 0
        assert resultado['provedores'] == []

    def test_agrega_por_provedor(self, app):
        with app.app_context():
            FitBotUsoService.registrar('groq', True, 400, tokens_entrada=100, tokens_saida=50)
            FitBotUsoService.registrar('groq', True, 600, tokens_entrada=100, tokens_saida=50)
            FitBotUsoService.registrar('groq', False, 200, motivo_falha='rate limit (429)')
            FitBotUsoService.registrar('gemini', True, 900, tokens_entrada=200, tokens_saida=80)

            resultado = FitBotUsoService.get_metricas(horas=24)

        assert resultado['total_chamadas'] == 4
        por_provedor = {p['provedor']: p for p in resultado['provedores']}

        groq = por_provedor['groq']
        assert groq['chamadas'] == 3
        assert groq['sucessos'] == 2
        assert groq['falhas'] == 1
        assert groq['taxa_sucesso_pct'] == round(100 * 2 / 3, 1)
        assert groq['duracao_media_ms'] == round((400 + 600 + 200) / 3)
        assert groq['tokens_entrada'] == 200
        assert groq['tokens_saida'] == 100

        gemini = por_provedor['gemini']
        assert gemini['chamadas'] == 1
        assert gemini['taxa_sucesso_pct'] == 100.0

    def test_ignora_chamadas_fora_da_janela(self, app):
        from datetime import datetime, timedelta, timezone

        with app.app_context():
            antiga = FitBotChamada(
                provedor='groq', sucesso=True, duracao_ms=500,
                criado_em=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            db.session.add(antiga)
            db.session.commit()

            FitBotUsoService.registrar('groq', True, 400)

            resultado = FitBotUsoService.get_metricas(horas=24)

        assert resultado['total_chamadas'] == 1
