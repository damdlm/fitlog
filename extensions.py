"""
Extensões Flask da aplicação.

Todas as extensões são criadas aqui SEM app, e inicializadas
com init_app(app) dentro de create_app() no app.py.

Qualquer módulo que precise de uma extensão importa daqui,
nunca de app.py — isso evita imports circulares.

IMPORTANTE: db é a instância única definida em models.py e
re-exportada aqui para conveniência. Nunca instancie SQLAlchemy()
em outro lugar.
"""
import os
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Instância única de db — definida em models.py, importada aqui
from models import db  # noqa: F401

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
)

# Cache distribuído: Redis em produção, SimpleCache em dev/testes.
# Configure CACHE_TYPE=redis e CACHE_REDIS_URL no .env para produção.
from flask_caching import Cache
cache = Cache()
