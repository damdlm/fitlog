"""Simulações de tela com Playwright, sem repetir a mesma preparação.

Requisitos (só no ambiente de quem simula, não vão para o requirements):
    pip install playwright && playwright install chromium

Uso:
    from tests.ux.harness import Sessao

    with Sessao('cel') as s:                    # 'cel' | 'escuro' | 'desk'
        pg = s.entrar('ana')                    # usuários em tests/ux/seed.py
        pg.goto(s.url('/aluno/estatisticas'))
        print(s.texto(pg, '#mapaMuscular .mm-painel'))
        s.foto(pg, '#mapaMuscular', 'mapa')     # só quando a mudança é visual
        assert not s.erros(pg)

    # Ajustar dados antes de abrir o navegador:
    with Sessao('desk', preparar=lambda db, m: ...) as s:   # m = módulo models

A base fica em cache em $FITLOG_UX_DIR (padrão /tmp/fitlog_ux) e é refeita
sozinha quando models.py ou data/exercises.json mudam; cada Sessao trabalha
numa cópia, então nada vaza de uma simulação para outra. Para forçar:
    python -m tests.ux.harness --refazer

O que a Sessao já resolve: servidor local numa porta livre, aceite de
Termos/Política, tutoriais (driver.js) desligados, tema escuro, bloqueio de
qualquer requisição externa e coleta de erros de JS (pageerror + console).
"""
import contextlib
import hashlib
import io
import logging
import os
import shutil
import socket
import sys
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASTA = os.environ.get('FITLOG_UX_DIR', '/tmp/fitlog_ux')
VIEWPORTS = {
    'cel': {'viewport': {'width': 390, 'height': 844}, 'is_mobile': True, 'has_touch': True},
    'escuro': {'viewport': {'width': 390, 'height': 844}, 'is_mobile': True, 'has_touch': True},
    'desk': {'viewport': {'width': 1366, 'height': 900}},
}

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# `import app` cria um app padrão (app.py, última linha) com o banco de
# desenvolvimento "sqlite:///instance/fitlog.db", que o Flask-SQLAlchemy
# resolve como instance/instance/fitlog.db (pasta que não existe) e loga um
# traceback "Erro DB no startup". Aponta esse app de importação para um
# arquivo temporário; as sessões usam o próprio banco (config_para).
os.makedirs(PASTA, exist_ok=True)
os.environ.setdefault('DEV_DATABASE_URL', 'sqlite:///' + os.path.join(PASTA, 'import.db'))

# Saída enxuta: create_app() põe o log raiz em INFO (uma linha por
# blueprint, por requisição...). Só avisos e erros aparecem aqui.
logging.disable(logging.INFO)


def config_para(caminho_db):
    from tests.conftest import TestConfig

    class Cfg(TestConfig):
        TESTING = False
        DEBUG = False
        RATELIMIT_ENABLED = False
        WTF_CSRF_ENABLED = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + caminho_db
    return Cfg


def _assinatura():
    h = hashlib.sha1()
    for rel in ('models.py', 'data/exercises.json', 'tests/ux/seed.py'):
        with open(os.path.join(RAIZ, rel), 'rb') as f:
            h.update(f.read())
    return h.hexdigest()[:12]


def base(refazer=False):
    """Caminho da base em cache (monta se faltar ou se o código mudou)."""
    os.makedirs(PASTA, exist_ok=True)
    caminho = os.path.join(PASTA, f'base-{_assinatura()}.db')
    if refazer or not os.path.exists(caminho):
        for antigo in os.listdir(PASTA):
            if antigo.startswith('base-'):
                os.remove(os.path.join(PASTA, antigo))
        from tests.ux.seed import montar
        montar(caminho)
    return caminho


def _porta_livre():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Sessao:
    def __init__(self, cenario='cel', preparar=None, pasta_fotos=None):
        if cenario not in VIEWPORTS:
            raise ValueError(f'cenário deve ser um de {list(VIEWPORTS)}')
        self.cenario = cenario
        self.preparar = preparar
        self.pasta_fotos = pasta_fotos or os.path.join(PASTA, 'fotos')
        self._paginas = []

    # --- ciclo de vida -------------------------------------------------
    def __enter__(self):
        os.chdir(RAIZ)
        from werkzeug.serving import make_server
        with contextlib.redirect_stdout(io.StringIO()):  # o app de importação imprime a senha do admin de dev
            from app import create_app
        import services.privacidade_service as priv
        priv.PrivacidadeService.precisa_aceitar_algum = staticmethod(lambda uid: False)

        self.db_path = os.path.join(PASTA, f'sessao-{os.getpid()}-{id(self)}.db')
        shutil.copy(base(), self.db_path)
        self.app = create_app(config_para(self.db_path))
        with self.app.app_context():
            from models import db
            import models
            db.create_all()
            if self.preparar:
                self.preparar(db, models)
                db.session.commit()
        self.porta = _porta_livre()
        self._srv = make_server('127.0.0.1', self.porta, self.app, threaded=True)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.navegador = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        try:
            self.navegador.close()
            self._pw.stop()
        finally:
            self._srv.shutdown()
            if os.path.exists(self.db_path):
                os.remove(self.db_path)

    # --- uso -----------------------------------------------------------
    def url(self, caminho):
        return f'http://127.0.0.1:{self.porta}{caminho}'

    def entrar(self, usuario, senha='senha forte 1'):
        """Novo contexto (cookies próprios) já logado; devolve a página."""
        ctx = self.navegador.new_context(**VIEWPORTS[self.cenario])
        local = f'http://127.0.0.1:{self.porta}'
        ctx.route('**/*', lambda r: r.continue_() if r.request.url.startswith(local) or
                  r.request.url.startswith('data:') else r.abort())
        tema = "localStorage.setItem('fitlog:tema','escuro');" if self.cenario == 'escuro' else ''
        ctx.add_init_script("(function(){" + tema + "var g=Storage.prototype.getItem;"
                            "Storage.prototype.getItem=function(k){if(String(k).indexOf('fitlog:tour:')===0)return '1';"
                            "return g.apply(this,arguments)};})();")
        pg = ctx.new_page()
        pg._erros = []
        pg.on('pageerror', lambda e: pg._erros.append(str(e)[:200]))
        pg.on('console', lambda m: m.type == 'error' and pg._erros.append('console: ' + m.text[:200]))
        pg.goto(self.url('/auth/login'))
        pg.fill('#loginUsername', usuario)
        pg.fill('#loginPassword', senha)
        with pg.expect_navigation():
            pg.click('button[type=submit]')
        self._paginas.append(pg)
        return pg

    @staticmethod
    def texto(pg, seletor):
        """innerText do elemento, com espaços colapsados ('' se não existir)."""
        if not pg.locator(seletor).count():
            return ''
        return pg.eval_on_selector(seletor, "e => e.innerText.replace(/\\s+/g, ' ').trim()")

    def foto(self, pg, seletor, nome):
        """Screenshot do elemento (ou da página, seletor=None). Devolve o caminho."""
        os.makedirs(self.pasta_fotos, exist_ok=True)
        caminho = os.path.join(self.pasta_fotos, f'{nome}_{self.cenario}.png')
        pg.mouse.move(2, 2)  # tira o hover de cima do elemento
        if seletor:
            pg.locator(seletor).screenshot(path=caminho)
        else:
            pg.screenshot(path=caminho, full_page=True)
        return caminho

    @staticmethod
    def erros(pg):
        """Erros de JS coletados na página (lista vazia = nenhum)."""
        return list(pg._erros)

    @staticmethod
    def largura(pg):
        """scrollWidth do documento: maior que a viewport = rolagem lateral."""
        return pg.evaluate('document.documentElement.scrollWidth')


if __name__ == '__main__':
    print(base(refazer='--refazer' in sys.argv))
