import os
import secrets
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask

from config import get_config
from models import db, User

from extensions import login_manager, csrf, limiter, cache, compress


# =============================================================
# LOGS
# =============================================================
def setup_logging(app):
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, 'fitlog.log')

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10_485_760,
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # RotatingFileHandler sozinho não é suficiente no Railway: o volume
    # onde logs/fitlog.log é escrito não é coletado pela plataforma, só
    # stdout/stderr do processo do Gunicorn são. Sem um handler para
    # stream, logger.exception(...) e afins não aparecem no painel de
    # logs do Railway -- só localmente, no arquivo.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    # CRÍTICO: os dois handlers acima são anexados no logger RAIZ do
    # Python (logging.getLogger(), sem nome), não em app.logger. Todo
    # módulo do projeto usa o padrão `logger = logging.getLogger(__name__)`
    # (services/, routes/, utils/) -- isso cria um logger com nome
    # próprio (ex: "services.billing_service"), numa hierarquia
    # DIFERENTE da de app.logger, que só existiria se algum ancestral
    # dele tivesse handler configurado. Configurar só em app.logger (como
    # era antes) deixava logger.info(...) de QUALQUER lugar fora deste
    # arquivo INVISÍVEL tanto no Railway quanto no arquivo local -- só
    # logger.warning()+ aparecia, via o handler de último recurso do
    # próprio Python (logging.lastResort, que só cobre WARNING+), o que
    # mascarou esse buraco por um bom tempo (foi o que impediu
    # diagnosticar direito os webhooks do Asaas por várias rodadas).
    # Configurar no logger raiz cobre app.logger também, por propagação
    # -- não precisa mais configurar os dois separadamente.
    root_logger = logging.getLogger()
    # Evita duplicar handlers se create_app() rodar mais de uma vez no
    # mesmo processo (acontece na suíte de testes, um app por teste).
    if not any(getattr(h, '_fitlog_root_handler', False) for h in root_logger.handlers):
        file_handler._fitlog_root_handler = True
        stream_handler._fitlog_root_handler = True
        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)
    root_logger.setLevel(logging.INFO)

    # O Flask anexa seu próprio handler padrão em app.logger na
    # primeira vez que ele é acessado (comportamento antigo, anterior a
    # esta correção também) -- sem remover, toda chamada via
    # app.logger especificamente (só dentro deste arquivo) sai
    # duplicada: uma vez no formato do Flask, outra no nosso. Módulos
    # que usam logging.getLogger(__name__) (todo o resto do código)
    # não têm esse problema, só propagam pro root uma vez.
    app.logger.handlers.clear()

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

    # Mesmo critério usado em _criar_admin_inicial() e no init_db()
    # abaixo, além dos headers de segurança mais adiante -- um único
    # cálculo, reaproveitado, para não divergir entre os pontos que
    # decidem "estamos em produção?".
    em_producao = not (app.config.get('DEBUG', False) or app.config.get('TESTING', False))

    # config básica
    app.config['JSON_AS_ASCII'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.json.ensure_ascii = False

    # ---------------------------------------------------------------
    # CACHE-BUSTING PARA ESTÁTICOS
    # ---------------------------------------------------------------
    # SEND_FILE_MAX_AGE_DEFAULT (config.py) manda o navegador guardar
    # JS/CSS em cache por 1 dia -- ótimo para performance, mas sem
    # versionamento no nome do arquivo, qualquer deploy que altere um
    # .js/.css existente fica "invisível" pro navegador de quem já
    # tinha aberto o site: ele continua servindo a versão antiga do
    # cache local até o cache expirar ou um refresh forçado (Ctrl+Shift+R).
    #
    # `static_v('js/arquivo.js')` resolve isso adicionando `?v=<mtime>`
    # na URL -- o navegador trata URL diferente como recurso diferente,
    # então uma mudança no arquivo (mtime novo) automaticamente vira
    # cache-miss, sem precisar renomear nada nem esperar expirar.
    # Uso no template: {{ static_v('js/admin-monitoramento.js') }}
    # em vez de {{ url_for('static', filename='js/admin-monitoramento.js') }}.
    def static_v(filename):
        from flask import url_for
        caminho_completo = os.path.join(app.static_folder, filename)
        try:
            versao = int(os.path.getmtime(caminho_completo))
        except OSError:
            versao = 0  # arquivo não encontrado -- não quebra o template
        return f"{url_for('static', filename=filename)}?v={versao}"

    app.jinja_env.globals['static_v'] = static_v

    # extensões
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)
    compress.init_app(app)

    login_manager.login_view = 'auth.login'
    # Sem mensagem de flash ao redirecionar pra tela de login (o
    # Flask-Login só usa flash() se login_message não for None).
    login_manager.login_message = None

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
            if em_producao:
                # Em produção o schema é responsabilidade do Alembic
                # (Procfile: "release: alembic upgrade head"), não daqui.
                # Chamar create_all() aqui também mascararia uma
                # migração que falhou: a tabela nasceria sem passar
                # pelo Alembic, sem revisão registrada, e o schema real
                # divergiria do histórico de migrações sem nenhum aviso.
                pass
            else:
                # Dev/testes não têm fase de release rodando migração
                # nenhuma -- create_all() continua sendo o jeito mais
                # simples de ter o schema pronto localmente/na suíte.
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
    # LGPD -- reaceite de Termos/Política quando a versão vigente muda
    # =============================================================
    # Só intercepta navegação de página (GET) -- nunca POSTs/JSON (fetch
    # do FitBot, formulários de ação etc.), pra não quebrar nenhuma
    # chamada AJAX existente com um redirect inesperado. O próprio
    # fluxo de aceite (rota privacidade.aceite) e as rotas de auth
    # (login/logout/registro) ficam de fora, senão ninguém conseguiria
    # nem chegar na tela de aceite.
    @app.before_request
    def _exigir_aceite_lgpd_atual():
        from flask import request as flask_request, session as flask_session, redirect as flask_redirect, url_for as flask_url_for
        from flask_login import current_user as flask_current_user
        from services.privacidade_service import PrivacidadeService

        if flask_request.method != 'GET':
            return None
        if not flask_current_user.is_authenticated:
            return None

        endpoint = flask_request.endpoint or ''
        if endpoint in ('static', 'health', 'health_db') or endpoint.startswith('privacidade.') or endpoint.startswith('auth.'):
            return None

        chave_atual = PrivacidadeService.chave_versoes_atuais()
        if flask_session.get('lgpd_versoes_ok') == chave_atual:
            return None

        if PrivacidadeService.precisa_aceitar_algum(flask_current_user.id):
            return flask_redirect(flask_url_for('privacidade.aceite', next=flask_request.path))

        # Já está em dia -- guarda na sessão pra não bater no banco de
        # novo a cada request, até a próxima mudança de versão.
        flask_session['lgpd_versoes_ok'] = chave_atual
        return None

    # =============================================================
    # COMANDOS CLI (cobrança/assinatura)
    # =============================================================
    # Rodar via Railway Cron (ou qualquer scheduler externo) apontando
    # pra "flask billing-expirar-carencias" / "flask billing-verificar-tiers"
    # -- ver services/billing_service.py. Não existe scheduler embutido
    # no processo web (gunicorn já roda com múltiplos workers; um job
    # dentro do próprio processo rodaria uma vez por worker).
    @app.cli.command("billing-expirar-carencias")
    def billing_expirar_carencias():
        """Move para 'blocked' assinaturas com carência de pagamento
        atrasado vencida, e também inicia a carência de quem pagou
        via Pix e passou do período de ~1 mês sem renovar (Pix não
        avisa atraso via webhook, diferente de cartão -- ver
        BillingService.expirar_pix_vencidos). Rodar a cada hora."""
        from services.billing_service import BillingService
        total_pix = BillingService.expirar_pix_vencidos()
        total = BillingService.expirar_carencias_vencidas()
        print(f"{total_pix} assinatura(s) Pix movida(s) para past_due por período vencido.")
        print(f"{total} assinatura(s) movida(s) para blocked.")

    @app.cli.command("billing-verificar-tiers")
    def billing_verificar_tiers():
        """Lista professores cujo tier calculado (pela contagem atual de
        alunos) difere do tier hoje associado à assinatura -- não aplica
        nada, só reporta para virar notificação/aviso antes de qualquer
        mudança de cobrança. Rodar diariamente."""
        from services.billing_service import BillingService
        mudancas = BillingService.verificar_mudancas_tier_professores()
        if not mudancas:
            print("Nenhuma mudança de tier pendente.")
            return
        for m in mudancas:
            atual = m['tier_atual'].codigo if m['tier_atual'] else 'gratuito'
            novo = m['tier_novo'].codigo if m['tier_novo'] else 'gratuito'
            print(f"professor_id={m['professor'].id} {atual} -> {novo}")

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
    # em_producao já calculado no início de create_app() (reaproveitado
    # também pelo init_db() acima).
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
    # MÍDIA DOS EXERCÍCIOS (BUCKET S3-COMPATÍVEL, COM FALLBACK PRO
    # VOLUME LOCAL DO RAILWAY ENQUANTO A MIGRAÇÃO NÃO TERMINA)
    # =============================================================
    # Histórico: essa mídia vivia só no volume "exercicios", montado em
    # /app/exercicios. Volumes do Railway não funcionam com múltiplas
    # réplicas ("Replicas cannot be used with volumes" -- doc oficial),
    # então pra escalar horizontalmente a mídia precisou migrar pra um
    # bucket S3-compatível (ver services/storage_service.py e
    # scripts/migrar_midia_para_bucket.py).
    #
    # Enquanto gif_url/imagem ainda apontam pra arquivos que só
    # existem no volume (migração gradual, sem downtime), o fallback
    # abaixo mantém tudo funcionando dos dois jeitos.
    EXERCICIOS_MEDIA_DIR = os.environ.get("EXERCICIOS_MEDIA_DIR", "/app/exercicios")

    @app.route("/exercicios-media/<path:caminho>")
    def exercicios_media(caminho):
        from flask import send_from_directory, request, Response, stream_with_context
        import mimetypes
        from services.storage_service import StorageService

        if StorageService.is_configured():
            # Proxy em vez de redirect: Railway Buckets são sempre
            # privados (não existe URL pública nem "bucket público" pra
            # ligar), então um redirect pra URL assinada -- que expira --
            # nunca pode ser cacheado pelo navegador. Isso fazia toda
            # visualização (inclusive reexibições do mesmo exercício)
            # pagar um salto de rede extra: navegador -> app -> bucket.
            # Buscando o objeto aqui e servindo ele direto, com
            # Cache-Control bem longo (os arquivos são endereçados por
            # hash, então o mesmo caminho nunca muda de conteúdo), o
            # navegador simplesmente para de pedir de novo depois da
            # primeira vez.
            obj = StorageService.get_object_stream(
                caminho, range_header=request.headers.get("Range")
            )
            if obj:
                content_type = obj["content_type"] or mimetypes.guess_type(caminho)[0] or "application/octet-stream"
                headers = {
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "Accept-Ranges": "bytes",
                }
                if obj["content_length"] is not None:
                    headers["Content-Length"] = str(obj["content_length"])
                if obj["content_range"]:
                    headers["Content-Range"] = obj["content_range"]

                def gerar():
                    stream = obj["body"]
                    try:
                        while True:
                            trecho = stream.read(64 * 1024)
                            if not trecho:
                                break
                            yield trecho
                    finally:
                        stream.close()

                status = 206 if obj["is_partial"] else 200
                return Response(
                    stream_with_context(gerar()),
                    status=status,
                    mimetype=content_type,
                    headers=headers,
                )
            # Objeto não encontrado no bucket (ex: migração em andamento)
            # -- cai pro volume local abaixo.

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