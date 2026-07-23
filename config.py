import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

logger.debug("Iniciando config.py | FLASK_ENV=%s | DATABASE_URL definida=%s",
             os.getenv('FLASK_ENV'), bool(os.getenv('DATABASE_URL')))

# Força modo production se PostgreSQL estiver configurado
if os.getenv('DATABASE_URL') and 'postgres' in os.getenv('DATABASE_URL', ''):
    logger.debug("DATABASE_URL com Postgres detectada, forçando FLASK_ENV=production")
    os.environ['FLASK_ENV'] = 'production'


def get_database_url():
    """Obtém e corrige a URL do banco de dados para Railway"""
    database_url = os.environ.get('DATABASE_URL')

    if database_url:
        # Railway às vezes retorna postgres:// em vez de postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        # Nunca logar a URL, nem parcialmente: ela pode conter usuário/senha do banco.
        logger.debug("DATABASE_URL corrigida (postgres:// -> postgresql://) e pronta para uso")
        return database_url

    logger.debug("DATABASE_URL não encontrada, usando SQLite local")
    return 'sqlite:///instance/fitlog.db'


def get_config():
    """Retorna a classe de configuração correta baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')

    config_map = {
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    config_class = config_map.get(env, DevelopmentConfig)

    if config_class is ProductionConfig and not config_class.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY não definida no ambiente de produção. "
            "Configure a variável SECRET_KEY antes de subir a aplicação."
        )

    logger.debug("get_config() -> FLASK_ENV=%s -> %s", env, config_class.__name__)
    return config_class


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # ATENÇÃO: o fallback acima só é seguro para desenvolvimento local.
    # ProductionConfig sobrescreve SECRET_KEY abaixo e falha se a env var não existir.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # E-mail (usado no fluxo de recuperação de senha), enviado via API
    # HTTPS do SendGrid (não via SMTP -- a Railway bloqueia portas SMTP
    # de saída por padrão). O remetente precisa estar verificado no
    # SendGrid via Single Sender Verification (permite usar um Gmail
    # como remetente sem precisar de domínio próprio). Se
    # SENDGRID_API_KEY não for definida, o link de reset é apenas
    # registrado no log em vez de enviado de verdade -- ver
    # utils/email_utils.py.
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///instance/fitlog.db')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # 'connect_timeout' é específico do psycopg2 (Postgres) — por isso fica
    # só aqui, e não na Config base (SQLite não aceita esse argumento).
    # Sem ele, uma conexão travada (rede, Postgres reiniciando etc.) pode
    # ficar pendurada por bem mais que o --timeout do gunicorn, e o worker
    # morre em silêncio sem nenhum erro no log. Com isso, falha em 10s com
    # uma exceção clara em vez de travar o worker inteiro.
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'connect_args': {
            'connect_timeout': 10,
        },
    }

    # ATENÇÃO: a validação de SECRET_KEY NÃO fica aqui no corpo da classe.
    # Corpo de classe roda assim que o módulo é importado (na definição da
    # classe), então um `raise` aqui quebraria qualquer import de config.py
    # — inclusive em dev/testes — mesmo quando ProductionConfig nunca é
    # selecionada. A validação real acontece em get_config(), que só roda
    # quando o ambiente realmente pede ProductionConfig.
    SECRET_KEY = os.getenv('SECRET_KEY')