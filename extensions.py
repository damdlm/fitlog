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


def _chave_rate_limit():
    """Chave usada pelo Flask-Limiter para agrupar requisições.

    Antes disso, o limite era só por IP (get_remote_address) -- o que
    pune injustamente usuários numa mesma rede (ex: vários alunos na
    mesma academia, atrás do mesmo IP público/NAT): eles dividiam o
    MESMO orçamento de requisições, e o uso normal de um podia derrubar
    todo mundo com erro 429, sem relação nenhuma com abuso de verdade.

    Agora: usuário logado -> conta pelo ID dele (cada um com seu
    próprio orçamento, não importa a rede). Anônimo (ex: tela de
    login) -> continua por IP, que é exatamente onde faz sentido
    proteger contra brute-force/scraping de quem ainda não autenticou.
    """
    from flask_login import current_user
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return get_remote_address()


limiter = Limiter(
    key_func=_chave_rate_limit,
    # Limite GLOBAL (aplicado a toda rota que não tem @limiter.limit
    # próprio). O valor antigo (50/hora) é baixo demais pro uso normal
    # de alguém navegando ativamente no app (calendário, estatísticas,
    # registro de treino, chamadas de API do FitBot) -- 300/hora dá
    # margem confortável pra uso intenso legítimo e ainda protege
    # contra um cliente com bug/loop fazendo requisição sem parar.
    # As rotas sensíveis (login, reset de senha, etc.) já têm limites
    # próprios e MAIS restritos em routes/auth_routes.py -- esses não
    # mudam, continuam valendo por cima deste default.
    default_limits=["2000 per day", "300 per hour"],
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
)

# Cache distribuído: Redis em produção, SimpleCache em dev/testes.
# Configure CACHE_TYPE=redis e CACHE_REDIS_URL no .env para produção.
from flask_caching import Cache
cache = Cache()

# Compressão gzip/brotli das respostas (HTML, CSS, JS, JSON) — a
# aplicação é um MPA que recarrega a página inteira a cada navegação,
# então comprimir o HTML em si (não só os assets estáticos) ajuda em
# toda troca de tela, não só no carregamento inicial.
from flask_compress import Compress
compress = Compress()