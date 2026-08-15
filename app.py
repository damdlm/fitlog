import os
import secrets
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from config import get_config
from models import db, User

from extensions import limiter, cache, compress

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

    # RotatingFileHandler sozinho não é suficiente no Railway: o volume
    # onde logs/fitlog.log é escrito não é coletado pela plataforma, só
    # stdout/stderr do processo do Gunicorn são. Sem um handler para
    # stream, logger.exception(...) e afins não aparecem no painel de
    # logs do Railway -- só localmente, no arquivo.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)

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

    except Exception:
        app.logger.exception("Erro ao criar admin inicial")


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
    compress.init_app(app)

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from flask import session as flask_session
        user = db.session.get(User, int(user_id))
        if user is None:
            return None
        # CORREÇÃO 10 (hardening de segurança): invalida sessões antigas
        # após troca de senha. Não é uma query extra -- o usuário já é
        # buscado em toda requisição autenticada por causa do próprio
        # Flask-Login; só comparamos o contador que já veio junto.
        if flask_session.get('sv') != user.session_version:
            return None
        return user

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
            except Exception:
                app.logger.exception("Erro ao verificar admin")

        except Exception:
            app.logger.exception("Erro DB no startup")

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

    @app.route("/health/db")
    def health_db():
        from sqlalchemy import text
        try:
            db.session.execute(text("SELECT 1"))
            return {"status": "ok", "database": "ok"}, 200
        except Exception:
            # Não expor host/usuário/senha/DATABASE_URL nem o traceback
            # completo na resposta HTTP -- só no log interno.
            app.logger.exception("Health check do banco falhou (/health/db)")
            return {"status": "error", "database": "unavailable"}, 503

    # =============================================================
    # HEADERS DE SEGURANÇA
    # =============================================================
    # Mesmo critério de "estamos em produção?" já usado em
    # _criar_admin_inicial() acima, para manter consistência.
    em_producao = not (app.config.get('DEBUG', False) or app.config.get('TESTING', False))

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # CORREÇÃO seção 17 (hardening de segurança -- CSP progressiva):
        # primeira fase, mapeada a partir do que a aplicação realmente
        # usa hoje (grep em todos os templates) -- só 2 CDNs externos
        # (cdn.jsdelivr.net p/ Chart.js/FullCalendar/SortableJS/
        # html2canvas, cdnjs.cloudflare.com p/ Flatpickr), nenhuma
        # imagem/fetch externo, e MUITO script/estilo inline espalhado
        # pelos templates (onclick=, <script> inline, style=) -- por
        # isso 'unsafe-inline' continua liberado por enquanto em
        # script-src/style-src, senão a aplicação quebraria na hora.
        # object-src/base-uri/frame-ancestors já fecham sem custo (a
        # aplicação não usa <object>/<embed>, não precisa trocar <base>,
        # e X-Frame-Options acima já cobre o mesmo que frame-ancestors).
        # Endurecimento futuro (remover unsafe-inline via nonce) fica
        # para uma tarefa própria, por template, testando um de cada vez.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "media-src 'self' https:; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self';"
        )

        # HSTS só faz sentido (e só é seguro) quando servido via HTTPS,
        # ou seja, em produção -- em dev/testes, servido por http://
        # localhost, o navegador não deve ser instruído a forçar HTTPS.
        if em_producao:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response

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

    # =============================================================
    # MÍDIA DOS EXERCÍCIOS (VOLUME DO RAILWAY)
    # =============================================================
    # O volume "exercicios" é montado em /app/exercicios em produção
    # (fora da pasta static/, que vem do repo). gif_url/imagem em
    # exercicios_sistema guardam caminhos relativos tipo
    # "videos/0001-2gPfomN.gif" dentro dessa pasta.
    EXERCICIOS_MEDIA_DIR = os.environ.get("EXERCICIOS_MEDIA_DIR", "/app/exercicios")

    @app.route("/exercicios-media/<path:caminho>")
    def exercicios_media(caminho):
        from flask import send_from_directory
        # Arquivos são endereçados por hash (ex: "0001-2gPfomN.gif" —
        # media_id no nome), então o mesmo caminho nunca muda de conteúdo:
        # seguro cachear por muito tempo no navegador/CDN de borda, em vez
        # de reservir a mídia (e ocupar uma thread do Gunicorn) a cada
        # visita à mesma tela de exercício.
        return send_from_directory(
            EXERCICIOS_MEDIA_DIR, caminho, max_age=60 * 60 * 24 * 30
        )

    return app  # ← estava faltando isso!


# =============================================================
# GUNICORN ENTRYPOINT
# =============================================================
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)