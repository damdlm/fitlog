import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuração base compartilhada por todos os ambientes."""

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv('SECRET_KEY', '')
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT', '')

    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # Sobrescrito em ProductionConfig

    DEBUG = False
    TESTING = False

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Flask-Caching — Redis em produção, SimpleCache em dev
    CACHE_TYPE = os.getenv('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_REDIS_URL = os.getenv('REDIS_URL', None)


class DevelopmentConfig(Config):
    """Desenvolvimento local — segurança relaxada, debug ativo."""

    DEBUG = True
    SESSION_COOKIE_SECURE = False

    # Gera chaves temporárias se não configuradas — apenas para dev
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT') or secrets.token_hex(16)


class ProductionConfig(Config):
    """Produção — validação das variáveis obrigatórias feita em runtime no app.py."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True

    # Lê do ambiente — se vazio, o app.py detecta e recusa iniciar
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT', '')


class TestingConfig(Config):
    """Testes automatizados."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    SECURITY_PASSWORD_SALT = 'test-salt'
    CACHE_TYPE = 'NullCache'  # Sem cache em testes


config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
}


def get_config():
    """Retorna a classe de configuração baseada em FLASK_ENV (padrão: development)."""
    env = os.getenv('FLASK_ENV', 'development').lower()
    cfg = config_map.get(env)
    if cfg is None:
        raise EnvironmentError(
            f"[FITLOG] FLASK_ENV='{env}' invalido. Use: development | production | testing"
        )

    # Validação de segurança em produção — feita aqui em runtime, não no corpo da classe
    if env == 'production':
        _validate_production_secrets()

    return cfg


def _validate_production_secrets():
    """Garante que segredos obrigatórios estão configurados em produção."""
    placeholders = {
        '', 'TROQUE_AQUI', 'TROQUE_AQUI_gere_uma_chave_aleatoria',
        'TROQUE_AQUI_gere_um_salt_aleatorio', 'dev-key-do-not-use-in-production',
        'password-salt',
    }
    for var in ('SECRET_KEY', 'SECURITY_PASSWORD_SALT'):
        value = os.getenv(var, '').strip()
        if value in placeholders:
            raise EnvironmentError(
                f"\n[FITLOG] Variavel '{var}' nao configurada para producao.\n"
                f"Gere um valor com: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
                f"E defina {var}=<valor> no arquivo .env\n"
            )
