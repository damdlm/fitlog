"""Lote 6a da análise de UX.

P4: Tabela de Progresso no visual do app. P5: atalhos no topo do Progresso.
C1: indicadores do calendário sem corte. X1: contraste dos textos. X2: título
e rótulos para leitor de tela. X3: área de toque. X6: "Tutorial" como "?" no
cabeçalho. Mais: eixos e percentuais dos gráficos no formato brasileiro.
"""
import glob
import re
from datetime import date, datetime, timedelta

from models import (db, User, ExercicioUsuario, HistoricoTreino, RegistroTreino,
                    VersaoExercicio)
from services.billing_service import BillingService
from utils.date_utils import data_para_periodo, data_para_semana
from tests.integration.test_routes.test_register_routes import _login
from tests.integration.test_routes.test_registro_ux_lote2 import _ficha_abc, _sessao


def _com_trial(username):
    u = User.query.filter_by(username=username).one()
    BillingService.iniciar_trial(u)
    db.session.commit()


def _registro_nesta_semana(u, versao, treino_id, ex, carga, reps):
    hoje = date.today()
    r = RegistroTreino(treino_versao_id=treino_id, versao_id=versao.id,
                       periodo=data_para_periodo(hoje), semana=data_para_semana(hoje),
                       exercicio_usuario_id=ex.id, data_registro=datetime.combine(hoje, datetime.min.time()),
                       user_id=u.id)
    db.session.add(r)
    db.session.flush()
    db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=0))
    db.session.commit()


class TestTabelaDeProgresso:
    def _html(self, app, client, username):
        with app.app_context():
            u, v, ids, ex = _ficha_abc(username)
            # Treino B com um exercício só dele (no _ficha_abc os três dividem o mesmo).
            ex_b = ExercicioUsuario(usuario_id=u.id, nome='Remada', musculo_id=ex.musculo_id)
            db.session.add(ex_b)
            db.session.flush()
            VersaoExercicio.query.filter_by(treino_versao_id=ids['B']).delete()
            db.session.add(VersaoExercicio(treino_versao_id=ids['B'], exercicio_usuario_id=ex_b.id, ordem=0))
            db.session.commit()
            _registro_nesta_semana(u, v, ids['A'], ex, 37.5, 10)
            _registro_nesta_semana(u, v, ids['B'], ex_b, 40.0, 8)
            _com_trial(username)
        _login(client, username)
        resp = client.get('/estatisticas/visualizar/tabela')
        assert resp.status_code == 200
        return resp.get_data(as_text=True)

    def test_numeros_no_formato_brasileiro_e_cabecalho_kg_reps(self, app, client):
        html = self._html(app, client, 'tab_br')
        assert '>37,5</td>' in html
        assert '>40</td>' in html
        assert '37.5' not in html and '40.0' not in html
        assert '>kg</th>' in html and '>reps</th>' in html

    def test_linha_com_o_nome_de_cada_treino_e_sem_fonte_manuscrita(self, app, client):
        html = self._html(app, client, 'tab_grupo')
        assert 'class="linha-grupo"' in html
        assert 'Treino A</td>' in html and 'Treino B</td>' in html
        assert 'Patrick Hand' not in html
        assert 'linha-espacadora' not in html
        assert 'class="prog-card"' in html


class TestProgressoAtalhos:
    def test_atalhos_levam_a_secoes_que_existem(self, app, client):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('atalho_aluno')
            _sessao(u, v, ids['A'], ex, date.today() - timedelta(days=1))
            _com_trial('atalho_aluno')
        _login(client, 'atalho_aluno')
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        alvos = re.findall(r'class="est-atalho[^"]*" href="#(\w+)"', html)
        assert alvos == ['recordesPessoais', 'progressaoForca', 'volumeMusculo', 'evolucaoVolume', 'atividade']
        for alvo in alvos:
            assert f'id="{alvo}"' in html
        # Sem cardio registrado, sem atalho de Cardio.
        assert 'href="#cardioSemana"' not in html

    def test_variacao_percentual_com_virgula(self):
        with open('templates/aluno/estatisticas.html', encoding='utf-8') as f:
            src = f.read()
        assert 'FitLogUtils.formatarNumero(Math.abs(valor), 1)}%' in src


class TestCalendarioIndicadores:
    def test_rotulos_curtos_e_sequencia_com_unidade(self, app, client):
        with app.app_context():
            _ficha_abc('cal_rotulos')
        _login(client, 'cal_rotulos')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        assert '>dias no mês</div>' in html
        assert '>sequência</div>' in html
        assert '>dias treinados</div>' not in html and '>sequência atual</div>' not in html
        assert "(sequencia === 1 ? ' dia' : ' dias')" in html


class TestGraficosEmPortugues:
    def test_toda_pagina_com_chartjs_carrega_o_locale_logo_depois(self):
        paginas = [p for p in glob.glob('templates/**/*.html', recursive=True)
                   if 'chart.umd.min.js' in open(p, encoding='utf-8').read()]
        assert paginas
        for p in paginas:
            src = open(p, encoding='utf-8').read()
            i = src.index('chart.umd.min.js')
            assert 'js/chart-ptbr.js' in src[i:i + 200], p
        with open('static/js/chart-ptbr.js', encoding='utf-8') as f:
            assert "Chart.defaults.locale = 'pt-BR'" in f.read()


class TestTutorialNoCabecalho:
    def test_botao_da_tela_vira_gatilho_escondido(self, app, client):
        with app.app_context():
            _ficha_abc('tour_cab')
        _login(client, 'tour_cab')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        assert 'id="btnTourCalendario" data-tour-pagina' in html
        assert 'id="flAjudaTela"' in html
        assert "document.querySelector('[data-tour-pagina]')" in html

    def test_tutoriais_de_modal_continuam_no_lugar(self):
        with open('templates/calendar/calendario.html', encoding='utf-8') as f:
            src = f.read()
        detalhes = re.search(r'<button[^>]*id="btnTourCalendarioDetalhes"[^>]*>', src).group(0)
        assert 'data-tour-pagina' not in detalhes

    def test_cada_tela_tem_no_maximo_um_gatilho_de_pagina(self):
        for p in glob.glob('templates/**/*.html', recursive=True):
            with open(p, encoding='utf-8') as f:
                assert f.read().count('data-tour-pagina>') <= 2, p  # cadastrar: com e sem ficha (if/else)


class TestAcessibilidade:
    def test_h1_escondido_com_o_titulo_da_tela(self, app, client):
        with app.app_context():
            _ficha_abc('a11y_h1')
        _login(client, 'a11y_h1')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        assert '<h1 class="visually-hidden">Calendário</h1>' in html

    def test_tela_com_h1_proprio_nao_ganha_outro(self, client):
        html = client.get('/auth/login').get_data(as_text=True)
        assert html.count('<h1') == 1

    def test_campos_do_fitbot_e_da_busca_com_rotulo(self, app, client):
        with app.app_context():
            _ficha_abc('a11y_rot')
        _login(client, 'a11y_rot')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'aria-label="Mensagem para o FitBot"' in html
        assert 'aria-label="Buscar exercício"' in html

    def test_cinzas_claros_nao_voltam_como_cor_de_texto(self):
        proibidas = re.compile(r'(?<![-\w])color\s*:\s*#(8a8a8a|9a9a9a|999|adb5bd|8a857a|8a8f98)\b', re.I)
        arquivos = glob.glob('templates/**/*.html', recursive=True) + glob.glob('static/css/*.css')
        achados = []
        for p in arquivos:
            with open(p, encoding='utf-8') as f:
                for n, linha in enumerate(f, 1):
                    if proibidas.search(linha):
                        achados.append(f'{p}:{n}')
        assert achados == []

    def test_area_de_toque_ampliada_nos_controles_pequenos(self):
        with open('templates/base.html', encoding='utf-8') as f:
            base = f.read()
        assert '.est-pill::before, .dash-filter-pill::before' in base
        assert 'inset: -9px -2px;' in base

    def test_links_de_paragrafo_sem_cobrir_o_vizinho(self):
        """Links que ficam um embaixo do outro ("Termos de Uso" / "Política de
        Privacidade", rodapé da página inicial): ampliação vertical pequena e
        o link nunca quebra no meio -- senão a área de um cobre o outro."""
        with open('templates/base.html', encoding='utf-8') as f:
            base = f.read()
        assert '.login-terms a, .landing-footer-links a { white-space: nowrap; }' in base
        bloco = base.split('.login-terms a::before, .landing-footer-links a::before {', 1)[1].split('}', 1)[0]
        assert 'inset: -5px -2px;' in bloco
        with open('static/css/auth-login.css', encoding='utf-8') as f:
            assert 'line-height: 1.9;' in f.read()
        with open('static/css/landing.css', encoding='utf-8') as f:
            assert 'line-height: 2.2;' in f.read()


class TestDataDoBrasilNoPainel:
    def test_grafico_da_semana_usa_a_data_de_sao_paulo(self, app, client, monkeypatch):
        """00:30 UTC de quarta (18/11) ainda é terça (17/11) 21:30 em Brasília:
        o último dia do gráfico "esta semana" tem de ser terça."""
        import routes.aluno.main as painel
        from datetime import timezone

        class Relogio(datetime):
            @classmethod
            def now(cls, tz=None):
                agora = datetime(2026, 11, 18, 0, 30, tzinfo=timezone.utc)
                return agora.astimezone(tz) if tz else agora.replace(tzinfo=None)

        with app.app_context():
            _ficha_abc('painel_tz')
        _login(client, 'painel_tz')
        monkeypatch.setattr(painel, 'datetime', Relogio)
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        m = re.search(r'labels: (\[[^\]]*\]),', html)
        assert m, 'gráfico da semana não encontrado'
        assert m.group(1).endswith('"Ter"]')
