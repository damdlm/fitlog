"""
Redis fora do ar NÃO pode derrubar o site.

Incidente 02/11/2026 ~12:04: o Redis reiniciou no Railway e, por ~3 min,
TODAS as páginas responderam 500 -- o context processor do menu lê
ConfiguracaoService.tela_assinatura_ativa() do cache, e a exceção do
redis-py subia sem tratamento (inclusive na própria página de erro 500).

Estes testes sobem o app com cache e rate limiter apontando para um Redis
REAL inexistente (porta 1 em 127.0.0.1, conexão recusada na hora), em vez
de mockar -- assim pegam também erro de configuração (CACHE_OPTIONS,
RATELIMIT_*), não só o try/except do CacheService.

Fixture própria, sem segurar o app_context aberto durante as chamadas do
test client (ver nota em tests/security/test_sessions.py).
"""
import pytest

from app import create_app
from config import ProductionConfig
from models import db as _db
from services.base_service import CacheService, cached
from tests.conftest import (
    TestConfig,
    _seed_telas_controladas,
    _seed_telas_controladas_professor,
)

REDIS_MORTO = 'redis://127.0.0.1:1/0'


class RedisMortoConfig(TestConfig):
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = REDIS_MORTO
    CACHE_OPTIONS = dict(ProductionConfig._REDIS_TIMEOUTS)
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = REDIS_MORTO
    RATELIMIT_STORAGE_OPTIONS = dict(ProductionConfig._REDIS_TIMEOUTS)
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = ProductionConfig.RATELIMIT_IN_MEMORY_FALLBACK_ENABLED
    RATELIMIT_SWALLOW_ERRORS = ProductionConfig.RATELIMIT_SWALLOW_ERRORS


@pytest.fixture
def app_sem_redis():
    app = create_app(RedisMortoConfig)
    with app.app_context():
        _db.create_all()
        _seed_telas_controladas()
        _seed_telas_controladas_professor()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client_sem_redis(app_sem_redis):
    return app_sem_redis.test_client()


class TestConfiguracaoProducao:
    def test_timeouts_curtos_no_cache_e_no_limiter(self):
        for opcoes in (ProductionConfig.CACHE_OPTIONS, ProductionConfig.RATELIMIT_STORAGE_OPTIONS):
            assert 0 < opcoes['socket_connect_timeout'] <= 5
            assert 0 < opcoes['socket_timeout'] <= 5

    def test_limiter_com_fallback_em_memoria(self):
        assert ProductionConfig.RATELIMIT_IN_MEMORY_FALLBACK_ENABLED is True
        assert ProductionConfig.RATELIMIT_SWALLOW_ERRORS is True


class TestCacheServiceSemRedis:
    def test_get_vira_cache_miss(self, app_sem_redis):
        with app_sem_redis.app_context():
            assert CacheService.get('qualquer') is None

    def test_set_e_invalidate_nao_levantam(self, app_sem_redis):
        with app_sem_redis.app_context():
            CacheService.set('k', 1, ttl_seconds=10)
            CacheService.invalidate('k')
            CacheService.invalidate_pattern('k')

    def test_decorator_cached_executa_a_funcao(self, app_sem_redis):
        chamadas = []

        @cached(ttl_seconds=10, key_prefix='teste_redis_morto')
        def calcula(x):
            chamadas.append(x)
            return x * 2

        with app_sem_redis.app_context():
            assert calcula(21) == 42
            assert calcula(21) == 42
        # Sem cache, a função roda toda vez -- mas roda, em vez de quebrar.
        assert chamadas == [21, 21]


class TestPaginasSemRedis:
    @pytest.mark.parametrize('url', ['/', '/auth/login', '/precos', '/health'])
    def test_paginas_publicas_respondem_200(self, client_sem_redis, url):
        resp = client_sem_redis.get(url)
        assert resp.status_code == 200, f'{url} -> {resp.status_code}'

    def test_login_com_senha_errada_nao_da_500(self, client_sem_redis):
        # O bloqueio por conta+IP guarda o contador no cache: sem Redis o
        # contador não persiste, mas o login tem que responder normalmente.
        resp = client_sem_redis.post(
            '/auth/login',
            data={'username': 'ninguem@example.com', 'password': 'errada'},
        )
        assert resp.status_code < 500
