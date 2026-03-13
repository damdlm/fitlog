import os
import sys
import secrets
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import get_config
from models import db, User

# =============================================================
# Extensões inicializadas sem app (Application Factory pattern)
# IMPORTANTE: limiter fica em extensions.py para evitar import
# circular com auth_routes.py (que também precisa do limiter).
# =============================================================
from extensions import limiter

login_manager = LoginManager()
csrf = CSRFProtect()


def setup_logging(app):
    """Configura logging com rotação de arquivo."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, 'fitlog.log')
    file_handler = RotatingFileHandler(log_path, maxBytes=10_485_760, backupCount=10,
                                       encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('FitLog iniciado')


def _criar_admin_inicial(app):
    """
    Cria o usuário admin apenas quando o banco está vazio.

    Segurança:
    - Exige ADMIN_PASSWORD com mínimo de 12 caracteres.
    - Se não configurada, gera senha aleatória e exibe UMA VEZ no log.
    """
    admin_password = os.getenv('ADMIN_PASSWORD', '').strip()

    if not admin_password:
        admin_password = secrets.token_urlsafe(16)
        app.logger.warning(
            "\n" + "=" * 54 + "\n"
            "  AVISO: ADMIN_PASSWORD nao configurada no .env\n"
            f"  Senha gerada: {admin_password}\n"
            "  Salve agora -- nao sera exibida novamente.\n"
            + "=" * 54
        )
    elif len(admin_password) < 12:
        raise ValueError(
            "[FITLOG] ADMIN_PASSWORD precisa ter ao menos 12 caracteres. "
            "Defina uma senha forte no .env."
        )

    admin = User(username='admin', email='admin@fitlog.com', is_admin=True)
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    app.logger.info("Usuario admin criado com sucesso.")


def create_app(config_class=None):
    """Cria e configura a aplicação Flask (Application Factory)."""
    if config_class is None:
        config_class = get_config()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Encoding JSON
    app.config['JSON_AS_ASCII'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.json.ensure_ascii = False

    # Inicializar extensões com o app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Configurar Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faca login para acessar esta pagina.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception as e:
            app.logger.error(f"Erro ao carregar usuario {user_id}: {e}")
            db.session.rollback()
            return None

    # Logging
    setup_logging(app)

    # Middlewares
    from middleware.logging_middleware import setup_middleware
    setup_middleware(app)

    # Banco de dados e admin inicial
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Tabelas verificadas/criadas")
        except Exception as e:
            app.logger.warning(f"Erro ao criar tabelas: {e}")
            db.session.rollback()

        try:
            if User.query.count() == 0:
                _criar_admin_inicial(app)
        except Exception as e:
            app.logger.warning(f"Erro ao verificar/criar admin: {e}")
            db.session.rollback()

    # Blueprints -- importados DENTRO do factory para evitar import circular
    from routes import register_all_routes
    register_all_routes(app)

    # Context processors
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

    return app


# Instância global -- usada pelo servidor WSGI (gunicorn, waitress)
app = create_app()

if __name__ == '__main__':
    print('=' * 60)
    print('FitLog - Sistema de Controle de Treinos'.center(60))
    print('=' * 60)
    print(f"Modo: {'Desenvolvimento' if app.debug else 'Producao'}")
    print('Acesse: http://127.0.0.1:5000')
    print('=' * 60)
    app.run(debug=app.debug, host='127.0.0.1', port=5000)
