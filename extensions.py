"""
Extensões Flask da aplicação.

Todas as extensões são criadas aqui SEM app, e inicializadas
com init_app(app) dentro de create_app() no app.py.

Qualquer módulo que precise de uma extensão importa daqui,
nunca de app.py — isso evita imports circulares.
"""
import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
)
