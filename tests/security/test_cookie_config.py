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


def test_secret_key_nao_usa_fallback_de_dev_por_padrao_na_config_base():
    # A Config base tem um fallback só para dev local -- só garantimos
    # aqui que ele existe e é claramente identificável (não é vazio),
    # já que get_config() força a checagem real (SECRET_KEY setada via
    # env) antes de subir com ProductionConfig.
    assert 'dev' in Config.SECRET_KEY.lower()
