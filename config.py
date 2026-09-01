import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

logger.debug("Iniciando config.py | FLASK_ENV=%s | DATABASE_URL definida=%s",
             os.getenv('FLASK_ENV'), bool(os.getenv('DATABASE_URL')))

# Força modo production se PostgreSQL estiver configurado
if os.getenv('DATABASE_URL') and 'postgres' in os.getenv('DATABASE_URL', ''):
    logger.debug("DATABASE_URL com Postgres detectada, forçando FLASK_ENV=production")
    os.environ['FLASK_ENV'] = 'production'


def get_database_url():
    """Obtém e corrige a URL do banco de dados para Railway"""
    database_url = os.environ.get('DATABASE_URL')

    if database_url:
        # Railway às vezes retorna postgres:// em vez de postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        # Nunca logar a URL, nem parcialmente: ela pode conter usuário/senha do banco.
        logger.debug("DATABASE_URL corrigida (postgres:// -> postgresql://) e pronta para uso")
        return database_url

    logger.debug("DATABASE_URL não encontrada, usando SQLite local")
    return 'sqlite:///instance/fitlog.db'


def get_config():
    """Retorna a classe de configuração correta baseada no ambiente"""
    env = os.getenv('FLASK_ENV', 'development')

    config_map = {
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    config_class = config_map.get(env, DevelopmentConfig)

    if config_class is ProductionConfig and not config_class.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY não definida no ambiente de produção. "
            "Configure a variável SECRET_KEY antes de subir a aplicação."
        )

    if config_class is ProductionConfig and not os.getenv('REDIS_URL'):
        # Em dev/testes, storage_uri='memory://' (ver extensions.py) é
        # aceitável -- um único processo. Em produção o Gunicorn roda
        # múltiplos workers (ver gunicorn.conf.py), cada um com sua
        # própria memória; rate limit em memory:// nesse caso conta
        # separadamente por worker, o que não protege de verdade.
        # Exigimos REDIS_URL explicitamente, como já fazemos com
        # SECRET_KEY acima.
        raise RuntimeError(
            "REDIS_URL não definida em produção. O rate limiting "
            "(Flask-Limiter) precisa de armazenamento compartilhado entre "
            "os workers do Gunicorn -- configure REDIS_URL antes de subir "
            "a aplicação."
        )

    logger.debug("get_config() -> FLASK_ENV=%s -> %s", env, config_class.__name__)
    return config_class


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # ATENÇÃO: o fallback acima só é seguro para desenvolvimento local.
    # ProductionConfig sobrescreve SECRET_KEY abaixo e falha se a env var não existir.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # NOTA: sessão é o cookie assinado padrão do Flask (client-side),
    # não sessão em arquivo/Redis no servidor -- o pacote Flask-Session
    # nunca foi instalado, então um antigo `SESSION_TYPE = 'filesystem'`
    # aqui não tinha efeito nenhum (config morta, o Flask ignora
    # silenciosamente chave de config que a extensão dona dela não
    # existe pra ler). Isso é bom pra escalar: qualquer réplica com o
    # mesmo SECRET_KEY valida a sessão de qualquer outra, sem precisar
    # de storage compartilhado.

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Sem isso, o Flask manda "Cache-Control: no-cache" em tudo que está
    # em /static/ (CSS, JS, ícones) — o navegador então revalida com o
    # servidor a cada requisição, mesmo o arquivo não tendo mudado. Como
    # esses arquivos não são versionados por hash no nome, 1 dia é um
    # meio-termo seguro: elimina a maior parte das revalidações dentro
    # de uma mesma sessão/dia de uso, sem deixar uma alteração de CSS/JS
    # presa em cache por muito tempo depois de um deploy.
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24

    # E-mail (usado no fluxo de recuperação de senha), enviado via API
    # HTTPS do Resend (api.resend.com), NAO via SMTP -- a Railway
    # bloqueia portas SMTP de saida (25/465/587) por padrao em alguns
    # planos/regioes (confirmado em producao: "Network is unreachable"
    # na porta 587). A API do Resend usa HTTPS (porta 443), que nao e
    # bloqueada.
    #
    # RESEND_API_KEY e gerada em resend.com -> API Keys. MAIL_DEFAULT_SENDER
    # precisa ser um endereco de um dominio verificado em resend.com ->
    # Domains, OU o remetente de teste onboarding@resend.dev (sem
    # verificacao, mas so entrega para o proprio e-mail cadastrado na
    # conta Resend). Se RESEND_API_KEY nao estiver configurada, o link
    # de reset e apenas registrado no log em vez de enviado de verdade
    # -- ver utils/email_utils.py.
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'onboarding@resend.dev')

    # Destinatário da tela "Contato" (reporte de erro/crítica/elogio).
    # A rota primeiro tenta enviar para todos os usuários com is_admin=True
    # no banco; ADMIN_EMAIL só é usado como fallback se nenhum admin tiver
    # e-mail cadastrado (ex: banco recém-criado, ainda sem admin). Opcional.
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

    # FitBot — assistente virtual de treino (chat com IA)
    #
    # Estratégia de roteamento (pensada para os limites do plano gratuito):
    #   - Mensagem SEM foto  -> Groq (Llama), texto puro, limite bem mais folgado.
    #   - Mensagem COM foto  -> Gemini (Flash-Lite), é o único dos dois com visão.
    #   - Reserva (texto E foto) -> OpenAI (gpt-4o-mini), entra automaticamente
    #     se o Groq ou o Gemini falharem (chave inválida, modelo descontinuado,
    #     erro do provedor etc.). Um alerta por e-mail é disparado pros admins
    #     quando isso acontece -- ver services/fitbot_service.py.
    #
    # As chaves ficam só no servidor — nunca são expostas ao navegador.
    # Se GEMINI_API_KEY ou GROQ_API_KEY não estiverem definidas, o FitBot
    # responde com uma mensagem de erro amigável em vez de quebrar. Se
    # OPENAI_API_KEY não estiver definida, o FitBot simplesmente não tem
    # reserva (comportamento antigo: mensagem de erro se o principal cair).
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    # gemini-1.5-flash foi desativado pelo Google (todo o Gemini 1.5/1.0 já
    # foi encerrado -- chamadas para ele retornam 404). gemini-2.5-flash-lite
    # também parou de aceitar novos usuários/projetos. gemini-3.5-flash-lite
    # é o modelo estável mais barato/rápido da geração atual (Gemini 3) que
    # ainda enxerga imagem. Se GEMINI_MODEL já estiver setada como env var
    # no Railway apontando pro modelo antigo, atualize-a também.
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')

    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    # llama-3.3-70b-versatile foi descontinuado pela Groq (deprecation
    # anunciada em 17/06/2026) -- chamadas para ele retornam 404
    # model_not_found. openai/gpt-oss-120b é a migração recomendada
    # oficialmente pela Groq para esse caso de uso. Se GROQ_MODEL já
    # estiver setada como env var no Railway apontando pro modelo
    # antigo, atualize-a também.
    GROQ_MODEL = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')
    # Modelo de transcrição de áudio (tela "Contato") -- mesma chave da
    # Groq acima, endpoint diferente (audio/transcriptions). turbo é o
    # mais rápido e já cobre português; troque para whisper-large-v3 se
    # precisar de mais precisão.
    GROQ_WHISPER_MODEL = os.getenv('GROQ_WHISPER_MODEL', 'whisper-large-v3-turbo')

    # Reserva única (texto E imagem) do FitBot quando Groq ou Gemini falham.
    # gpt-4o-mini é barato e enxerga imagem, cobrindo os dois casos com uma
    # única chave em vez de duas.
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    # Cache (Flask-Caching) — SimpleCache (em memória do processo) é
    # suficiente em dev/testes. ProductionConfig sobrescreve para Redis,
    # já que o Gunicorn roda múltiplos workers com memórias separadas.
    CACHE_TYPE = 'SimpleCache'

    # CORREÇÃO seção 12 (hardening de segurança -- Trusted Hosts / Host
    # Header): links absolutos gerados pelo servidor (hoje só o de reset
    # de senha) NÃO devem depender do header Host da requisição recebida,
    # porque ele pode ser forjado pelo cliente (Host Header Injection) --
    # um atacante poderia forçar o e-mail de reset a apontar para um
    # domínio dele, capturando o token de reset de outra pessoa.
    #
    # Se APP_BASE_URL estiver definida (ex: "https://fitlog.exemplo.com"),
    # ela é usada como origem confiável em vez do Host recebido. Se não
    # estiver definida, cai no comportamento antigo (url_for com
    # _external=True, baseado no Host) com um aviso no log -- ver
    # routes/auth_routes.py. ProductionConfig não precisa sobrescrever
    # isso: é a mesma variável de ambiente em qualquer ambiente.
    APP_BASE_URL = os.getenv('APP_BASE_URL')

    # Cobrança/assinaturas (Asaas) -- ver services/billing_service.py.
    # ASAAS_API_KEY nunca é exposta ao navegador -- só o backend fala
    # com a API do Asaas (o dado de cartão do usuário vai direto pro
    # checkout hospedado do Asaas, nunca passa pelo nosso servidor).
    # ASAAS_WEBHOOK_TOKEN é o token configurado no painel do Asaas em
    # Integrações > Webhooks, usado para validar que um POST em
    # /billing/webhook/asaas realmente veio do Asaas.
    ASAAS_API_KEY = os.getenv('ASAAS_API_KEY')
    ASAAS_WEBHOOK_TOKEN = os.getenv('ASAAS_WEBHOOK_TOKEN')
    ASAAS_ENV = os.getenv('ASAAS_ENV', 'sandbox')  # 'sandbox' ou 'production'


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///instance/fitlog.db')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CORREÇÃO -- CSRF em HTTPS bloqueando ações legítimas (ex: "Salvar
    # ordem" ao reordenar exercícios): por padrão o Flask-WTF, além de
    # validar o token, também exige um cabeçalho Referer em toda
    # requisição HTTPS (WTF_CSRF_SSL_STRICT=True). Chamadas via
    # fetch() nem sempre mandam Referer -- depende do navegador,
    # bloqueadores de rastreamento (Brave, uBlock, modo privado do
    # Safari) -- e aí o Flask recusa com 400 mesmo o token estando
    # correto. A proteção de verdade contra CSRF é o token em si
    # (validate_csrf, que continua ativo); a checagem de referer é uma
    # camada extra opcional que, na prática, gera falso positivo. Só
    # roda em produção (HTTPS) -- nunca disparava em dev/teste (HTTP),
    # por isso não aparecia nos testes locais.
    WTF_CSRF_SSL_STRICT = False

    # CORREÇÃO seção 18 (hardening de segurança -- cookies): o cookie de
    # "remember me" (Flask-Login) não herda as flags do cookie de sessão
    # acima, então precisa das próprias. Sem isso ele ficaria acessível
    # via JavaScript (sem HTTPONLY) e poderia trafegar em HTTP puro
    # (sem SECURE), quebrando a mesma garantia que já vale pro cookie
    # de sessão normal. Duração mantida no padrão do Flask-Login (365
    # dias) -- não há necessidade de negócio pra encurtar isso agora.
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # Redis é exigido em produção (ver validação em get_config() acima) —
    # reaproveitamos a mesma REDIS_URL do Flask-Limiter para o cache
    # distribuído, em vez de exigir uma segunda variável de ambiente.
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.getenv('REDIS_URL')

    # 'connect_timeout' é específico do psycopg2 (Postgres) — por isso fica
    # só aqui, e não na Config base (SQLite não aceita esse argumento).
    # Sem ele, uma conexão travada (rede, Postgres reiniciando etc.) pode
    # ficar pendurada por bem mais que o --timeout do gunicorn, e o worker
    # morre em silêncio sem nenhum erro no log. Com isso, falha em 10s com
    # uma exceção clara em vez de travar o worker inteiro.
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'connect_args': {
            'connect_timeout': 10,
        },
    }

    # ATENÇÃO: a validação de SECRET_KEY NÃO fica aqui no corpo da classe.
    # Corpo de classe roda assim que o módulo é importado (na definição da
    # classe), então um `raise` aqui quebraria qualquer import de config.py
    # — inclusive em dev/testes — mesmo quando ProductionConfig nunca é
    # selecionada. A validação real acontece em get_config(), que só roda
    # quando o ambiente realmente pede ProductionConfig.
    SECRET_KEY = os.getenv('SECRET_KEY')