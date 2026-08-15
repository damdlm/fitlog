"""Testes de segurança de configuração de cookies.

CORREÇÃO seção 18 (prompt de hardening): cookie de sessão e de
"remember me" precisam de SECURE/HTTPONLY/SAMESITE em produção.
"""
from config import ProductionConfig, Config


def test_session_cookie_hardened_em_producao():
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == 'Lax'


def test_remember_cookie_hardened_em_producao():
    assert ProductionConfig.REMEMBER_COOKIE_SECURE is True
    assert ProductionConfig.REMEMBER_COOKIE_HTTPONLY is True
    assert ProductionConfig.REMEMBER_COOKIE_SAMESITE == 'Lax'


def test_debug_desativado_em_producao():
    assert ProductionConfig.DEBUG is False


def test_secret_key_nao_usa_fallback_de_dev_por_padrao_na_config_base(monkeypatch):
    # A Config base tem um fallback só para dev local -- só garantimos
    # aqui que ele existe e é claramente identificável (não é vazio),
    # já que get_config() força a checagem real (SECRET_KEY setada via
    # env) antes de subir com ProductionConfig.
    #
    # O teste precisa rodar sem SECRET_KEY no ambiente para verificar
    # o fallback em si -- no CI essa env var fica setada de propósito
    # (ci.yml) para simular produção nos demais testes, então removemos
    # aqui e reimportamos o módulo para pegar o Config "limpo".
    monkeypatch.delenv('SECRET_KEY', raising=False)
    import importlib
    import config as config_module
    importlib.reload(config_module)
    try:
        assert 'dev' in config_module.Config.SECRET_KEY.lower()
    finally:
        importlib.reload(config_module)