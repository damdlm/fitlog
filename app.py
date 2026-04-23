import os
import secrets
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import get_config
from models import db, User

from extensions import limiter, cache

login_manager = LoginManager()
csrf = CSRFProtect()


# =============================================================
# LOGS
# =============================================================
def setup_logging(app):
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, 'fitlog.log')

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10_485_760,
        backupCount=10,
        encoding='utf-8'
    )

    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    file_handler.setLevel(logging.INFO)

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('FitLog iniciado')


# =============================================================
# ADMIN INICIAL
# =============================================================
def _criar_admin_inicial(app):
    admin_password = os.getenv('ADMIN_PASSWORD', '').strip()

    if not admin_password:
        admin_password = secrets.token_urlsafe(16)
        app.logger.warning(f"ADMIN gerado: {admin_password}")

    elif len(admin_password) < 12:
        raise ValueError("ADMIN_PASSWORD precisa ter pelo menos 12 caracteres")

    admin = User(
        username='admin',
        email='admin@fitlog.com',
        is_admin=True
    )

    admin.set_password(admin_password)

    db.session.add(admin)
    db.session.commit()


# =============================================================
# FACTORY
# =============================================================
def create_app(config_class=None):

    if config_class is None:
        config_class = get_config()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # config básica
    app.config['JSON_AS_ASCII'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.json.ensure_ascii = False

    # extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    setup_logging(app)

    from middleware.logging_middleware import setup_middleware
    setup_middleware(app)

    # =============================================================
    # DB INIT
    # =============================================================
    with app.app_context():
        db.create_all()

        if User.query.count() == 0:
            _criar_admin_inicial(app)

    # =============================================================
    # BLUEPRINTS
    # =============================================================
    from routes import register_all_routes
    register_all_routes(app)

    # =============================================================
    # CONTEXT
    # =============================================================
    from utils.format_utils import (
        data_atual_iso,
        data_atual_formatada,
        formatar_data,
        formatar_data_para_input,
    )

    @app.context_processor
    def utility_processor():
        from datetime import datetime
        return dict(
            data_atual_iso=data_atual_iso,
            data_atual_formatada=data_atual_formatada,
            formatar_data=formatar_data,
            formatar_data_para_input=formatar_data_para_input,
            now=datetime.now,
        )

    # =============================================================
    # 🔥 FIX RAILWAY: HEALTH CHECK OBRIGATÓRIO
    # =============================================================
    @app.route("/health")
    def health():
        return "OK", 200

    @app.route("/")
    def root():
        return "FitLog rodando", 200

    return app


# =============================================================
# GUNICORN ENTRYPOINT
# =============================================================
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
