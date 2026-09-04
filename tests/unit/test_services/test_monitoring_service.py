"""Testes para MonitoringService -- coleta de métricas operacionais do
painel de monitoramento do admin (routes/admin_routes.py:monitoramento).

Cobre as 4 fontes de dado (processo/psutil, banco, cache/Redis,
negócio) nos dois cenários que o próprio módulo já foi desenhado pra
tolerar: fonte disponível e fonte indisponível (erro isolado, nunca
derruba o painel inteiro -- ver docstring do módulo).
"""
import builtins
from datetime import datetime, timedelta, timezone

import redis as redis_module

from models import (
    db, User, VersaoGlobal, TreinoVersao, RegistroTreino, Assinatura,
)
from services.monitoring_service import MonitoringService


def _criar_usuario(username, tipo_usuario='aluno', ativo=True):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, ativo=ativo)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.commit()
    return user


class TestGetProcessMetrics:

    def test_psutil_nao_instalado_retorna_indisponivel(self, app, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == 'psutil':
                raise ImportError("psutil não instalado neste ambiente")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', fake_import)

        with app.app_context():
            resultado = MonitoringService.get_process_metrics()

        assert resultado['disponivel'] is False
        assert 'erro' in resultado

    def test_coleta_normal_retorna_estrutura_esperada(self, app):
        with app.app_context():
            resultado = MonitoringService.get_process_metrics()

        assert resultado['disponivel'] is True
        assert resultado['num_workers'] >= 1
        assert isinstance(resultado['workers'], list)
        assert resultado['pid'] > 0
        assert resultado['uptime_segundos'] >= 0
        assert 'cpu_sistema_pct' in resultado
        assert 'memoria_sistema_usada_pct' in resultado

    def test_falha_ao_ler_processo_nao_derruba_e_retorna_indisponivel(self, app, monkeypatch):
        import psutil

        def _explode(pid):
            raise RuntimeError("falha simulada ao ler o processo")

        monkeypatch.setattr(psutil, 'Process', _explode)

        with app.app_context():
            resultado = MonitoringService.get_process_metrics()

        assert resultado['disponivel'] is False
        assert 'erro' in resultado


class TestGetDatabaseMetrics:

    def test_sqlite_retorna_disponivel_com_dialeto_correto(self, app):
        with app.app_context():
            resultado = MonitoringService.get_database_metrics()

        assert resultado['disponivel'] is True
        assert resultado['dialeto'] == 'sqlite'
        assert 'pool' in resultado
        # banco de teste é em memória -- não existe arquivo em disco
        # pra calcular tamanho, então a chave nem deve aparecer.
        assert 'tamanho_mb' not in resultado


class TestGetCacheMetrics:

    def test_sem_redis_url_configurada_retorna_indisponivel(self, app, monkeypatch):
        monkeypatch.delenv('REDIS_URL', raising=False)
        monkeypatch.delenv('CACHE_REDIS_URL', raising=False)

        with app.app_context():
            resultado = MonitoringService.get_cache_metrics()

        assert resultado['disponivel'] is False
        assert 'REDIS_URL' in resultado['erro']

    def test_redis_disponivel_calcula_hit_rate_e_le_info(self, app, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')

        class _FakeRedisClient:
            def info(self):
                return {
                    'redis_version': '7.2.0',
                    'used_memory': 10 * 1024 * 1024,
                    'used_memory_peak': 20 * 1024 * 1024,
                    'maxmemory': 0,
                    'connected_clients': 3,
                    'keyspace_hits': 80,
                    'keyspace_misses': 20,
                    'db0': {'keys': 42, 'expires': 5, 'avg_ttl': 1000},
                    'uptime_in_seconds': 3600,
                    'total_commands_processed': 999,
                }

        monkeypatch.setattr(redis_module, 'from_url', lambda *a, **kw: _FakeRedisClient())

        with app.app_context():
            resultado = MonitoringService.get_cache_metrics()

        assert resultado['disponivel'] is True
        assert resultado['versao_redis'] == '7.2.0'
        assert resultado['memoria_usada_mb'] == 10.0
        assert resultado['memoria_max_mb'] is None  # maxmemory=0 -> sem limite
        assert resultado['total_chaves'] == 42
        assert resultado['hit_rate_pct'] == 80.0  # 80 / (80+20) * 100

    def test_redis_inacessivel_retorna_indisponivel_sem_quebrar(self, app, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')

        def _from_url_explode(*a, **kw):
            raise ConnectionError("Redis fora do ar")

        monkeypatch.setattr(redis_module, 'from_url', _from_url_explode)

        with app.app_context():
            resultado = MonitoringService.get_cache_metrics()

        assert resultado['disponivel'] is False
        assert resultado['erro'] == 'Redis inacessível'

    def test_sem_hits_nem_misses_hit_rate_fica_none(self, app, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')

        class _FakeRedisClientZerado:
            def info(self):
                return {
                    'keyspace_hits': 0, 'keyspace_misses': 0,
                    'used_memory': 0, 'used_memory_peak': 0,
                }

        monkeypatch.setattr(redis_module, 'from_url', lambda *a, **kw: _FakeRedisClientZerado())

        with app.app_context():
            resultado = MonitoringService.get_cache_metrics()

        assert resultado['disponivel'] is True
        assert resultado['hit_rate_pct'] is None


class TestGetBusinessMetrics:

    def test_conta_usuarios_ativos_por_tipo(self, app, db):
        _criar_usuario('mon_aluno1', tipo_usuario='aluno')
        _criar_usuario('mon_aluno2', tipo_usuario='aluno')
        _criar_usuario('mon_prof1', tipo_usuario='professor')
        _criar_usuario('mon_inativo', tipo_usuario='aluno', ativo=False)

        resultado = MonitoringService.get_business_metrics()

        assert resultado['disponivel'] is True
        assert resultado['total_alunos'] >= 2
        assert resultado['total_professores'] >= 1
        # o usuário inativo nunca deve entrar na contagem
        assert resultado['total_usuarios'] == (
            resultado['total_alunos'] + resultado['total_professores']
            + User.query.filter_by(ativo=True).filter(
                ~User.tipo_usuario.in_(['aluno', 'professor'])
            ).count()
        )

    def test_conta_registros_de_hoje_e_assinaturas_por_status(self, app, db):
        u = _criar_usuario('mon_neg1', tipo_usuario='aluno')
        v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                          data_inicio=datetime.now(timezone.utc).date(), user_id=u.id)
        db.session.add(v)
        db.session.commit()

        tv = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='Treino A')
        db.session.add(tv)
        db.session.commit()

        from models import ExercicioUsuario
        ex = ExercicioUsuario(usuario_id=u.id, nome='Supino')
        db.session.add(ex)
        db.session.commit()

        hoje = datetime.now(timezone.utc)
        ontem = hoje - timedelta(days=1)
        db.session.add(RegistroTreino(
            treino_versao_id=tv.id, versao_id=v.id, periodo='2026-09',
            semana=1, data_registro=hoje, user_id=u.id, exercicio_usuario_id=ex.id,
        ))
        db.session.add(RegistroTreino(
            treino_versao_id=tv.id, versao_id=v.id, periodo='2026-09',
            semana=1, data_registro=ontem, user_id=u.id, exercicio_usuario_id=ex.id,
        ))
        db.session.add(Assinatura(usuario_id=u.id, status='active'))
        db.session.commit()

        resultado = MonitoringService.get_business_metrics()

        assert resultado['registros_hoje'] >= 1
        assert resultado['assinaturas_ativas'] >= 1
        assert resultado['total_treinos'] >= 1


class TestGetAllMetrics:

    def test_agrega_as_quatro_fontes(self, app, db):
        with app.app_context():
            resultado = MonitoringService.get_all_metrics()

        assert set(resultado.keys()) == {'coletado_em', 'processo', 'banco', 'cache', 'negocio'}
        assert resultado['negocio']['disponivel'] is True
        assert resultado['banco']['disponivel'] is True
        # 'coletado_em' precisa ser um timestamp ISO válido
        datetime.fromisoformat(resultado['coletado_em'])

    def test_falha_isolada_de_uma_fonte_nao_derruba_as_outras(self, app, db, monkeypatch):
        monkeypatch.setattr(
            MonitoringService, 'get_cache_metrics',
            staticmethod(lambda: {"disponivel": False, "erro": "simulado"}),
        )

        with app.app_context():
            resultado = MonitoringService.get_all_metrics()

        assert resultado['cache']['disponivel'] is False
        assert resultado['negocio']['disponivel'] is True
        assert resultado['banco']['disponivel'] is True
