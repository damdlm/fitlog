"""Testes para HistoricoMetricasService -- snapshots periódicos do
painel de monitoramento (ver models.HistoricoMetricas)."""
from datetime import datetime, timedelta, timezone

from models import db, HistoricoMetricas
from services.historico_metricas_service import HistoricoMetricasService


class TestCapturarSnapshot:

    def test_captura_grava_um_snapshot_resumido(self, app):
        with app.app_context():
            ok = HistoricoMetricasService.capturar_snapshot()
            assert ok is True

            snapshot = HistoricoMetricas.query.one()
            assert 'cpu_processo_pct' in snapshot.dados
            assert 'memoria_sistema_usada_pct' in snapshot.dados

    def test_falha_ao_coletar_metricas_nao_propaga_e_retorna_false(self, app, monkeypatch):
        from services.monitoring_service import MonitoringService

        def quebrado():
            raise RuntimeError("falha simulada")
        monkeypatch.setattr(MonitoringService, 'get_all_metrics', staticmethod(quebrado))

        with app.app_context():
            ok = HistoricoMetricasService.capturar_snapshot()

        assert ok is False


class TestObterSerie:

    def test_sem_snapshots_retorna_lista_vazia(self, app):
        with app.app_context():
            resultado = HistoricoMetricasService.obter_serie(horas=24)

        assert resultado['disponivel'] is True
        assert resultado['pontos'] == []

    def test_retorna_apenas_snapshots_dentro_da_janela_em_ordem(self, app):
        with app.app_context():
            agora = datetime.now(timezone.utc)
            db.session.add(HistoricoMetricas(coletado_em=agora - timedelta(hours=30), dados={"cpu_processo_pct": 1}))
            db.session.add(HistoricoMetricas(coletado_em=agora - timedelta(hours=2), dados={"cpu_processo_pct": 2}))
            db.session.add(HistoricoMetricas(coletado_em=agora - timedelta(minutes=5), dados={"cpu_processo_pct": 3}))
            db.session.commit()

            resultado = HistoricoMetricasService.obter_serie(horas=24)

        assert [p['cpu_processo_pct'] for p in resultado['pontos']] == [2, 3]


class TestLimparAntigas:

    def test_remove_apenas_snapshots_fora_da_retencao(self, app):
        with app.app_context():
            agora = datetime.now(timezone.utc)
            db.session.add(HistoricoMetricas(coletado_em=agora - timedelta(days=10), dados={}))
            db.session.add(HistoricoMetricas(coletado_em=agora - timedelta(days=1), dados={}))
            db.session.commit()

            total_removido = HistoricoMetricasService.limpar_antigas(dias_retencao=7)

        assert total_removido == 1
        with app.app_context():
            assert HistoricoMetricas.query.count() == 1
