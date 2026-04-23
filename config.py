import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# FORCE PRODUCTION MODE
if os.getenv('DATABASE_URL', '').startswith('postgresql://') or os.getenv('DATABASE_URL', '').startswith('postgres://'):
    print("🚀 DATABASE_URL detectada, forçando FLASK_ENV=production")
    os.environ['FLASK_ENV'] = 'production'

def get_database_url():
    """Obtém e corrige a URL do banco de dados para Railway"""
    database_url = os.environ.get('DATABASE_URL')
    
    print(f"📌 get_database_url() - URL raw: {database_url[:50] if database_url else 'None'}...")
    
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        if '?' in database_url:
            database_url += '&sslmode=require'
        else:
            database_url += '?sslmode=require'
        
        print(f"✅ URL corrigida: {database_url[:50]}...")
        return database_url
    
    print("⚠️ DATABASE_URL não encontrada, usando SQLite")
    return 'sqlite:///instance/fitlog.db'

def get_config():
    """Retorna a classe de configuração correta baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')
    
    print(f"🔍 FLASK_ENV = {env}")
    print(f"🔍 DATABASE_URL existe? {bool(os.getenv('DATABASE_URL'))}")
    
    if env == 'production':
        print("✅ USANDO ProductionConfig (PostgreSQL)")
        return ProductionConfig
    else:
        print("⚠️ USANDO DevelopmentConfig (SQLite)")
        return DevelopmentConfig

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///instance/fitlog.db')
    print(f"💻 DevelopmentConfig: {SQLALCHEMY_DATABASE_URI}")

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    print(f"🚀 ProductionConfig: usando {SQLALCHEMY_DATABASE_URI[:60]}...")
