import os
import traceback
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

print("=" * 50)
print("INICIANDO CONFIG.PY")
print(f"FLASK_ENV = {os.getenv('FLASK_ENV')}")
print(f"DATABASE_URL existe? {bool(os.getenv('DATABASE_URL'))}")
print("=" * 50)

# FORCE PRODUCTION MODE
if os.getenv('DATABASE_URL') and 'postgres' in os.getenv('DATABASE_URL', ''):
    print("🚀 DATABASE_URL com POSTGRES detectada, forçando FLASK_ENV=production")
    os.environ['FLASK_ENV'] = 'production'

def get_database_url():
    """Obtém e corrige a URL do banco de dados para Railway"""
    database_url = os.environ.get('DATABASE_URL')
    
    print(f"📌 get_database_url() - URL raw: {database_url[:60] if database_url else 'None'}...")
    
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        if '?' in database_url:
            database_url += '&sslmode=require'
        else:
            database_url += '?sslmode=require'
        
        print(f"✅ URL corrigida: {database_url[:60]}...")
        return database_url
    
    print("⚠️ DATABASE_URL não encontrada, usando SQLite")
    return 'sqlite:///instance/fitlog.db'

def get_config():
    """Retorna a classe de configuração correta baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')
    
    print(f"🔍 get_config() - FLASK_ENV = {env}")
    print(f"🔍 DATABASE_URL existe? {bool(os.getenv('DATABASE_URL'))}")
    
    if env == 'production':
        print("✅ RETORNANDO ProductionConfig")
        return ProductionConfig
    elif env == 'testing':
        print("✅ RETORNANDO TestingConfig")
        return TestingConfig
    else:
        print("⚠️ RETORNANDO DevelopmentConfig (SQLite)")
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
    print(f"💻 DevelopmentConfig: SQLALCHEMY_DATABASE_URI = {SQLALCHEMY_DATABASE_URI}")

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    print("🧪 TestingConfig ativo")

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    print(f"🚀 ProductionConfig: SQLALCHEMY_DATABASE_URI = {SQLALCHEMY_DATABASE_URI[:80]}...")
    
    # Tenta conectar agora para ver erro
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(SQLALCHEMY_DATABASE_URI)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ TESTE DE CONEXÃO COM POSTGRESQL BEM SUCEDIDO!")
    except Exception as e:
        print(f"❌ ERRO NO TESTE DE CONEXÃO: {e}")
        traceback.print_exc()

print("=" * 50)
print("CONFIG.PY CARREGADO COM SUCESSO")
print("=" * 50)
