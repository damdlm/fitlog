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
# ADMIN INICIAL (SEGURADO)
# =============================================================
def _criar_admin_inicial(app):
    try:
        admin_password = os.getenv('ADMIN_PASSWORD', '').strip()
        # DEBUG=True (dev) e TESTING=True (testes/CI) contam como "não
        # produção". TestingConfig só define TESTING, não DEBUG — se
        # checássemos só DEBUG, o ambiente de testes seria tratado como
        # produção e a suíte exigiria ADMIN_PASSWORD para rodar.
        em_producao = not (app.config.get('DEBUG', False) or app.config.get('TESTING', False))

        if not admin_password:
            if em_producao:
                # Em produção, NÃO geramos e escondemos uma senha em log —
                # o log pode ser exposto, versionado por engano, ou lido
                # por qualquer pessoa com acesso ao servidor/observabilidade.
                # Exigimos a variável explicitamente, como já fazemos com
                # SECRET_KEY em config.py.
                app.logger.error(
                    "ADMIN_PASSWORD não definida em produção. Nenhum usuário "
                    "admin foi criado. Defina ADMIN_PASSWORD e reinicie a aplicação."
                )
                return

            # Em desenvolvimento, geramos uma senha temporária, mas ela vai
            # apenas para o console (stdout) — nunca para o arquivo de log
            # persistente em logs/fitlog.log.
            admin_password = secrets.token_urlsafe(16)
            print(
                "\n" + "=" * 60 +
                f"\nADMIN (dev) criado -> usuário: admin | senha: {admin_password}" +
                "\n" + "=" * 60 + "\n"
            )
            app.logger.info("Usuário admin criado com senha temporária (exibida somente no console).")

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

    except Exception as e:
        app.logger.error(f"Erro ao criar admin inicial: {e}")


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

    # =============================================================
    # DB INIT (SEGURO PARA RAILWAY)
    # =============================================================
    def init_db():
        try:
            db.create_all()

            try:
                if User.query.first() is None:
                    _criar_admin_inicial(app)
            except Exception as e:
                app.logger.error(f"Erro ao verificar admin: {e}")

        except Exception as e:
            app.logger.error(f"Erro DB no startup: {e}")

    with app.app_context():
        init_db()

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
    # HEALTH CHECK (RAILWAY)
    # =============================================================
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    # =============================================================
    # SERVICE WORKER (PWA) — precisa ficar na raiz "/" para poder
    # controlar o site inteiro. Servido de /static/sw.js ele só
    # controlaria a pasta /static/, e o "instalar app" não funcionaria.
    # =============================================================
    @app.route("/sw.js")
    def service_worker():
        response = app.send_static_file("sw.js")
        response.headers["Content-Type"] = "application/javascript"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    return app  # ← estava faltando isso!


# =============================================================
# GUNICORN ENTRYPOINT
# =============================================================
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)