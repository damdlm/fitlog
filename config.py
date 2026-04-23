import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    """
    Garante que o DATABASE_URL exista e esteja no formato correto.
    Corrige automaticamente postgres:// -> postgresql://
    """
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "[FITLOG] DATABASE_URL não definida no ambiente (Railway)."
        )

    # Corrige formato antigo do Railway / Heroku
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


class Config:
    """Configuração base compartilhada por todos os ambientes."""

    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv('SECRET_KEY', '')
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT', '')

    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False

    DEBUG = False
    TESTING = False

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Cache
    CACHE_TYPE = os.getenv('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_REDIS_URL = os.getenv('REDIS_URL', None)


class DevelopmentConfig(Config):
    """Desenvolvimento local."""

    DEBUG = True
    SESSION_COOKIE_SECURE = False

    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT') or secrets.token_hex(16)


class ProductionConfig(Config):
    """Produção."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True

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
    CACHE_TYPE = 'NullCache'


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config():
    """Seleciona configuração pelo FLASK_ENV."""
    env = os.getenv('FLASK_ENV', 'development').lower()

    cfg = config_map.get(env)

    if not cfg:
        raise EnvironmentError(
            f"[FITLOG] FLASK_ENV inválido: {env}. Use: development | production | testing"
        )

    if env == 'production':
        _validate_production_secrets()

    return cfg


def _validate_production_secrets():
    """Validação de segurança para produção."""
    placeholders = {
        '',
        'TROQUE_AQUI',
        'TROQUE_AQUI_gere_uma_chave_aleatoria',
        'TROQUE_AQUI_gere_um_salt_aleatorio',
        'dev-key-do-not-use-in-production',
        'password-salt',
    }

    for var in ('SECRET_KEY', 'SECURITY_PASSWORD_SALT'):
        value = os.getenv(var, '').strip()

        if value in placeholders:
            raise EnvironmentError(
                f"""
[FITLOG] Variável '{var}' não configurada corretamente para produção.

Gere um valor seguro com:
python -c "import secrets; print(secrets.token_hex(32))"

Depois configure no Railway:
{var}=<valor-gerado>
"""
            )
