import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

def get_database_url():
    """Obtém e corrige a URL do banco de dados para Railway"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Railway usa 'postgres://' mas SQLAlchemy espera 'postgresql://'
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Adiciona SSL necessário para Railway
        if '?' in database_url:
            database_url += '&sslmode=require'
        else:
            database_url += '?sslmode=require'
        
        return database_url
    
    # Fallback para SQLite durante desenvolvimento local
    return 'sqlite:///instance/fitlog.db'

def get_config_class():
    """Retorna a classe de configuração apropriada baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')
    
    if env == 'production':
        return ProductionConfig
    elif env == 'testing':
        return TestingConfig
    else:
        return DevelopmentConfig

# =============================================================
# FUNÇÃO QUE SEU APP.PY ESTÁ CHAMANDO
# =============================================================
def get_config():
    """Retorna a classe de configuração correta baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')
    
    if env == 'production':
        return ProductionConfig
    elif env == 'testing':
        return TestingConfig
    else:
        return DevelopmentConfig

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Configurações de sessão
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    
    # Configurações de upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///instance/fitlog.db')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    DEBUG = False
    # Usa a função corrigida para Railway
    SQLALCHEMY_DATABASE_URI = get_database_url()
    
    # Configuração adicional para produção
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
