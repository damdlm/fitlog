"""Lote 6e da análise de UX.

C2: tema System / Dark / Light no app todo, escolhido no menu do avatar
e guardado no aparelho ("sistema" segue o claro/escuro do aparelho).
Padrão: claro. O interruptor próprio do calendário saiu; o calendário
segue o tema do app.

As cores fixas das telas viraram var(--fl-c-*, <cor do claro>): sem o
tema escuro as variáveis não existem e vale a cor original (o claro não
muda). Os testes de invariantes abaixo garantem isso em todos os arquivos.
"""
import glob
import re

import pytest

from tests.integration.test_routes.test_observacao_exercicio_treino import _criar_usuario, _login

VAR = re.compile(r'var\(--fl-c-([\w-]+)')


def _arquivos():
    return ([f for f in glob.glob('templates/**/*.html', recursive=True)]
            + [f for f in glob.glob('static/css/**/*.css', recursive=True)])


def _ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return f.read()


class TestInvariantesDasCores:
    def test_toda_variavel_tem_a_cor_do_claro_como_reserva(self):
        sem_reserva = []
        # tema-escuro.css só vale no escuro, onde as variáveis existem
        for f in [f for f in _arquivos() if not f.endswith('tema-escuro.css')]:
            s = _ler(f)
            for m in re.finditer(r'var\(--fl-c-[\w-]+(\)|,)', s):
                if m.group(1) == ')':
                    sem_reserva.append(f'{f}: {s[m.start():m.start() + 40]}')
        assert not sem_reserva, sem_reserva

    def test_toda_variavel_usada_existe_no_tema_escuro(self):
        css = _ler('static/css/tema-escuro.css')
        definidas = set(re.findall(r'--fl-c-([\w-]+)\s*:', css))
        usadas = set()
        for f in _arquivos():
            usadas |= set(VAR.findall(_ler(f)))
        assert usadas - definidas == set()

    def test_cor_de_grafico_nao_usa_variavel(self):
        # canvas (Chart.js) não entende var(): cores em string de JS ficam fixas
        em_string = []
        for f in _arquivos():
            for m in re.finditer(r"""['"`]var\(--fl-c-""", _ler(f)):
                em_string.append(f)
        assert not em_string, em_string

    def test_variavel_do_tema_vem_antes_de_outra_variavel(self):
        # var(--x, var(--fl-c-...)) nunca usaria a do tema quando --x existe
        invertidas = []
        for f in _arquivos():
            invertidas += [f for _ in re.finditer(r'var\(--(?!fl-c-)[\w-]+, var\(--fl-c-', _ler(f))]
        assert not invertidas, invertidas

    def test_tema_escuro_so_vale_com_data_bs_theme_dark(self):
        css = _ler('static/css/tema-escuro.css')
        sem_escopo = []
        for bloco in re.findall(r'(?:^|})\s*([^{}@/]+)\{', css):
            seletores = [s.strip() for s in bloco.split(',') if s.strip()]
            sem_escopo += [s for s in seletores if '[data-bs-theme="dark"]' not in s]
        assert not sem_escopo, sem_escopo


class TestBase:
    def test_area_logada_tem_o_tema(self, client, app):
        with app.app_context():
            _criar_usuario('tema_logado')
        _login(client, 'tema_logado')
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        assert "localStorage.getItem('fitlog:tema')" in html
        assert "document.documentElement.setAttribute('data-bs-theme', escuro ? 'dark' : 'light')" in html
        assert '/static/css/tema-escuro.' in html and '/static/js/tema.' in html
        # seletor só no menu do avatar (saiu do painel "Ajustes")
        assert html.count('role="radiogroup" aria-label="Tema do app"') == 1
        for opcao in ('sistema', 'escuro', 'claro'):
            assert html.count(f'data-tema-opcao="{opcao}"') == 1
        assert 'mais-tema' not in html
        avatar = html.split('class="dropdown-tema"')[1].split('auth/logout')[0]
        assert 'aria-label="Tema do app"' in avatar
        # nomes e ordem: System, Dark, Light
        seletor = avatar.split('role="radiogroup"')[1].split('</div>')[0]
        nomes = re.findall(r'<span>(\w+)</span>', seletor)
        assert nomes == ['System', 'Dark', 'Light']
        assert seletor.index('data-tema-opcao="sistema"') < seletor.index('data-tema-opcao="escuro"') \
            < seletor.index('data-tema-opcao="claro"')
        # "System" acompanha o aparelho já na primeira pintura
        assert "if (pref !== 'claro' && pref !== 'escuro' && pref !== 'sistema') {" in html
        assert "(pref === 'sistema' && !!window.matchMedia" in html
        assert "matchMedia('(prefers-color-scheme: dark)').matches);" in html
        assert '.tema-seletor {\n            display: grid;\n            grid-template-columns: repeat(3, 1fr);' in html.replace('\r\n', '\n')
        # fundo do documento também no <html> (faixa no Safari ao trocar o tema)
        css_html = html.replace('\r\n', '\n').split('        html {\n            overflow-x: hidden;')[1].split('}')[0]
        assert 'background-color: var(--fl-c-sup2, #f8f9fa);' in css_html
        # e o body cobre a tela toda (abaixo dele o Safari não repinta o fundo)
        css_body = html.replace('\r\n', '\n').split('        body {\n            background-color: var(--fl-c-sup2, #f8f9fa);')[1].split('}')[0]
        assert 'min-height: 100vh;' in css_body and 'min-height: 100dvh;' in css_body
        # quem tinha o calendário escuro continua no escuro
        assert "localStorage.getItem('fitlog_calendar_theme') === 'dark' ? 'escuro' : 'claro'" in html

    def test_deslogado_sem_tema(self, client):
        html = client.get('/auth/login').get_data(as_text=True)
        assert 'fitlog:tema' not in html and 'tema-escuro.' not in html

    @pytest.mark.parametrize('url', ['/precos', '/faq'])
    def test_paginas_com_visual_proprio_ficam_claras(self, client, app, url):
        with app.app_context():
            _criar_usuario('tema_publico' + url.strip('/'))
        _login(client, 'tema_publico' + url.strip('/'))
        html = client.get(url).get_data(as_text=True)
        assert 'fitlog:tema' not in html and 'data-tema-opcao' not in html


class TestFinanceiroLogin:
    def test_tela_de_senha_segue_o_tema(self, client, app):
        from extensions import limiter
        from models import User, db
        limiter.reset()
        with app.app_context():
            u = User(username='tema_fin', email='tema_fin@teste.com', tipo_usuario='aluno', is_admin=True)
            u.set_password('senha-correta-1')
            db.session.add(u)
            db.session.commit()
        client.post('/auth/login', data={'username': 'tema_fin', 'password': 'senha-correta-1'})
        html = client.get('/admin/financeiro/login').get_data(as_text=True)
        assert 'Confirme seu acesso' in html
        assert "localStorage.getItem('fitlog:tema')" in html and '/static/css/tema-escuro.' in html
        limiter.reset()

    def test_escuro_da_tela_de_senha(self):
        css = _ler('static/css/tema-escuro.css')
        for sel in ('[data-bs-theme="dark"] .login-card {', '[data-bs-theme="dark"] .login-input-group {',
                    '[data-bs-theme="dark"] .login-input-group input:-webkit-autofill {'):
            assert sel in css
        assert 'tema_sempre_claro' not in _ler('templates/admin/financeiro_login.html')

    def test_fundo_do_documento_no_html_escuro(self):
        css = _ler('static/css/tema-escuro.css')
        assert 'html[data-bs-theme="dark"] {\n    background-color: var(--fl-fundo);\n}' in css.replace('\r\n', '\n')


class TestMenusDestacadosNoEscuro:
    def test_menus_com_contorno_e_fundo_de_superficie(self):
        css = _ler('static/css/tema-escuro.css').replace('\r\n', '\n')
        menu = css.split('[data-bs-theme="dark"] .dropdown-menu {')[1].split('}')[0]
        sheet = css.split('[data-bs-theme="dark"] .mais-sheet {')[1].split('}')[0]
        for bloco in (menu, sheet):
            assert 'border: 1px solid var(--fl-borda);' in bloco
            assert 'background-color: var(--fl-superficie);' in bloco
        assert '--bs-dropdown-bg: var(--fl-superficie);' in menu
        assert '--bs-offcanvas-bg: var(--fl-superficie);' in sheet and 'border-bottom: 0;' in sheet


class TestLogoEscura:
    def test_marca_dagua_do_inicio_usa_a_logo_transparente(self):
        css = _ler('static/css/tema-escuro.css')
        assert '[data-bs-theme="dark"] .watermark {' in css
        assert 'url("../images/fitlog-logo-b.png")' in css
        import os
        assert os.path.exists('static/images/fitlog-logo-b.png')


class TestCalendario:
    def test_interruptor_saiu_e_segue_o_app(self, client, app):
        with app.app_context():
            _criar_usuario('tema_cal')
        _login(client, 'tema_cal')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        assert 'id="themeToggle"' not in html and 'theme-toggle' not in html
        assert "document.addEventListener('fitlog:tema', sincronizarTema);" in html
        assert "document.documentElement.getAttribute('data-bs-theme') === 'dark'" in html
        # o estilo do botão de compartilhar ficava junto do CSS do interruptor
        estilo = html.split('.btn-compartilhar-calendario {')[1].split('}')[0]
        assert 'background: linear-gradient(135deg, #F28C33 0%, #FFB366 100%);' in estilo

    def test_tema_aplicado_antes_do_primeiro_quadro(self, client, app):
        # sem piscar claro no tema escuro: o tema vai para a página logo
        # na abertura do bloco, não no fim do carregamento
        with app.app_context():
            _criar_usuario('tema_cal_flash')
        _login(client, 'tema_cal_flash')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        abertura = '<div class="calendar-page" id="calendarPage" data-theme="light">'
        inicio = html.split(abertura)[1].split('</script>')[0]
        assert inicio.lstrip().startswith('<script>')
        assert "var page = document.getElementById('calendarPage');" in inicio
        assert "page.setAttribute('data-theme', tema);" in inicio
        assert "page.setAttribute('data-bs-theme', tema);" in inicio

    def test_tutorial_do_calendario_sem_o_interruptor(self):
        assert '#themeToggle' not in _ler('static/js/calendario-tour.js')


class TestScripts:
    def test_tema_js(self):
        js = _ler('static/js/tema.js')
        assert "var CHAVE = 'fitlog:tema';" in js
        assert "var VALIDAS = ['claro', 'escuro', 'sistema'];" in js
        assert "return VALIDAS.indexOf(p) !== -1 ? p : 'claro';" in js  # padrão claro
        # "System" segue o aparelho, inclusive com a página aberta
        assert "window.matchMedia('(prefers-color-scheme: dark)')" in js
        assert "return pref === 'escuro' || (pref === 'sistema' && !!(midia && midia.matches));" in js
        assert "if (preferencia() === 'sistema') aplicar('sistema');" in js
        assert "new CustomEvent('fitlog:tema'" in js
        assert 'window.FitLogTema' in js

    def test_graficos_acompanham_o_tema(self):
        js = _ler('static/js/chart-ptbr.js')
        assert "Chart.defaults.locale = 'pt-BR';" in js
        assert "id: 'fitlogTema'" in js
        assert "document.addEventListener('fitlog:tema'" in js
        # caminhos, não objetos: o Chart.js recria as escalas a cada update()
        assert 'function ler(cfg, caminho)' in js