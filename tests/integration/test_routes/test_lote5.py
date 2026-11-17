"""Lote 5 da análise de UX: área do professor.

Pr1: barra inferior própria do professor. Pr3: lista de alunos com o
último treino, a frequência semanal e o selo "Parado". Pr4: o professor
vê a mesma tela Progresso do aluno (APIs com ?aluno_id=). Pr5: limite do
plano no botão "Novo aluno".
"""
from datetime import date, datetime, timedelta, timezone

from models import db, AlunoProfessor, Plano, User
from services.billing_service import BillingService
from services.configuracao_service import ConfiguracaoService
from tests.integration.test_routes.test_register_routes import _criar_usuario, _login
from tests.integration.test_routes.test_registro_ux_lote2 import _ficha_abc, _sessao

HOJE = date.today()


def _professor(username):
    p = _criar_usuario(username)
    p.tipo_usuario = 'professor'
    db.session.commit()
    return p


def _vincular(aluno, professor):
    db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True,
                                  data_associacao=datetime.now(timezone.utc)))
    db.session.commit()


class TestBarraDoProfessor:
    def test_professor_tem_painel_alunos_e_meu_treino(self, client, app):
        with app.app_context():
            _professor('pr1_prof')
        _login(client, 'pr1_prof')
        html = client.get('/professor/dashboard').get_data(as_text=True)
        nav = html.split('<nav class="bottom-nav d-lg-none"', 1)[1].split('</nav>', 1)[0]
        assert '<span>Painel</span>' in nav and '<span>Alunos</span>' in nav and '<span>Meu treino</span>' in nav
        assert '<span>Calendário</span>' not in nav and '<span>Progresso</span>' not in nav
        assert 'Meu calendário' in html and 'Meu progresso' in html  # em Ajustes

    def test_aluno_continua_com_a_barra_de_sempre(self, client, app):
        with app.app_context():
            _criar_usuario('pr1_aluno')
        _login(client, 'pr1_aluno')
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        nav = html.split('<nav class="bottom-nav d-lg-none"', 1)[1].split('</nav>', 1)[0]
        assert '<span>Início</span>' in nav and '<span>Progresso</span>' in nav and '<span>Painel</span>' not in nav
        assert 'Meu calendário' not in html


class TestListaDeAlunos:
    def test_ultimo_treino_frequencia_e_parado(self, client, app):
        with app.app_context():
            prof = _professor('pr3_prof')
            ativo, v, ids, ex = _ficha_abc('pr3_ativo')
            for d in (1, 3, 8, 10, 15):
                _sessao(ativo, v, ids['A'], ex, HOJE - timedelta(days=d))
            parado, v2, ids2, ex2 = _ficha_abc('pr3_parado')
            _sessao(parado, v2, ids2['A'], ex2, HOJE - timedelta(days=12))
            novo = _criar_usuario('pr3_novo')
            for a in (ativo, parado, novo):
                _vincular(db.session.get(User, a.id), prof)
        _login(client, 'pr3_prof')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert 'Último treino ontem' in html and '1,2× por semana' in html  # 5 dias em 4 semanas
        assert 'Parado há 12 dias' in html
        assert 'Ainda não treinou' in html
        assert 'registro(s)' not in html
        assert html.index('id="gaBtnNovoAluno"') < html.index('id="gaBusca"')  # ações no topo


class TestProgressoDoAlunoPeloProfessor:
    def _montar(self, app, sufixo):
        with app.app_context():
            prof = _professor(f'pr4_prof_{sufixo}')
            aluno, v, ids, ex = _ficha_abc(f'pr4_aluno_{sufixo}')
            _sessao(aluno, v, ids['A'], ex, HOJE - timedelta(days=1), series=((50, 10), (50, 10)))
            _vincular(db.session.get(User, aluno.id), prof)
            return aluno.id

    def test_pagina_e_o_progresso_do_aluno_so_leitura(self, client, app):
        aluno_id = self._montar(app, 'pag')
        _login(client, 'pr4_prof_pag')
        html = client.get(f'/professor/aluno/{aluno_id}/estatisticas').get_data(as_text=True)
        assert f'const ALUNO_ALVO = {aluno_id};' in html
        assert 'Evolução de Pr4_Aluno_Pag' in html and 'Voltar para Pr4_Aluno_Pag' in html
        assert 'id="btnCompartilharEstatisticas"' not in html and 'id="btnTourEstatisticas"' not in html
        assert 'fitlog:comece:progresso' not in html
        assert 'id="estDesempenhoTreino"' in html

    def test_apis_com_aluno_id(self, client, app):
        aluno_id = self._montar(app, 'api')
        _login(client, 'pr4_prof_api')
        kpis = client.get(f'/api/kpis?dias=30&aluno_id={aluno_id}')
        assert kpis.status_code == 200 and kpis.get_json()['treinos_realizados'] == 1
        assert kpis.get_json()['volume_total'] == 1000
        for url in ('/api/musculo-stats?dias=30', '/api/recordes-pessoais?dias=30', '/api/atividade-geral?dias=30',
                    '/api/progressao-forca/exercicios?dias=30', '/api/progresso?modo=semana&dias=30'):
            assert client.get(f'{url}&aluno_id={aluno_id}').status_code == 200, url
        # sem aluno_id vale o próprio professor, que precisa do plano dele (como
        # sempre); com aluno_id, o professor sem plano vê o aluno (como na tela antiga)
        proprio = client.get('/api/kpis?dias=30')
        assert proprio.status_code == 403 and proprio.get_json()['erro'] == 'assinatura_necessaria'

    def test_outro_professor_e_aluno_nao_veem(self, client, app):
        aluno_id = self._montar(app, 'neg')
        with app.app_context():
            _professor('pr4_intruso')
            _criar_usuario('pr4_colega')
        for quem in ('pr4_intruso', 'pr4_colega'):
            _login(client, quem)
            resp = client.get(f'/api/kpis?dias=30&aluno_id={aluno_id}')
            assert resp.status_code == 403 and 'erro' in resp.get_json(), quem
            client.get('/auth/logout')


class TestLimiteDeAlunos:
    def _planos(self):
        db.session.add_all([
            Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
                  preco_centavos=2990, min_alunos=3, max_alunos=10),
            Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor',
                  preco_centavos=5990, min_alunos=11, max_alunos=None),
        ])
        db.session.commit()

    def test_faixa_gratis_no_limite_leva_para_ampliar(self, client, app):
        with app.app_context():
            self._planos()
            ConfiguracaoService.set_cobranca_ativa(True)
            prof = _professor('pr5_prof')
            for i in range(2):
                _vincular(_criar_usuario(f'pr5_al{i}'), prof)
            info = BillingService.limite_alunos_info(db.session.get(User, prof.id))
            assert info['total'] == 2 and info['limite'] == 2 and info['pode_cadastrar'] is False
        _login(client, 'pr5_prof')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert '2 de 2 alunos · ampliar plano' in html
        assert 'href="/billing/minha-assinatura" class="btn ga-btn-novo is-no-limite"' in html
        painel = client.get('/professor/dashboard').get_data(as_text=True)
        assert '2 de 2 · ampliar plano' in painel

    def test_abaixo_do_limite_mostra_quanto_falta(self, client, app):
        with app.app_context():
            ConfiguracaoService.set_cobranca_ativa(True)
            prof = _professor('pr5_prof2')
            _vincular(_criar_usuario('pr5_b0'), prof)
        _login(client, 'pr5_prof2')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert '1 de 2 alunos' in html and 'ampliar plano' not in html

    def test_sem_cobranca_nao_mostra_limite(self, client, app):
        with app.app_context():
            ConfiguracaoService.set_cobranca_ativa(False)
            _professor('pr5_prof3')
        _login(client, 'pr5_prof3')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert 'class="ga-limite"' not in html and 'href="/professor/aluno/novo"' in html
        with app.app_context():
            ConfiguracaoService.set_cobranca_ativa(True)


class TestAjustesFinais:
    def test_acima_do_limite_nao_mostra_3_de_2(self, client, app):
        with app.app_context():
            ConfiguracaoService.set_cobranca_ativa(True)
            prof = _professor('pr5_acima')
            for i in range(3):
                _vincular(_criar_usuario(f'pr5_ac{i}'), prof)
        _login(client, 'pr5_acima')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert 'Acima do limite de 2 · ampliar plano' in html and '3 de 2' not in html

    def test_todas_as_fichas_mostra_de_qual_ficha_e_o_treino(self, client, app):
        with app.app_context():
            prof = _professor('pr4_todas')
            aluno, v, ids, ex = _ficha_abc('pr4_todas_al')
            _sessao(aluno, v, ids['A'], ex, HOJE)
            _vincular(db.session.get(User, aluno.id), prof)
            aid = aluno.id
        _login(client, 'pr4_todas')
        html = client.get(f'/professor/aluno/{aid}/estatisticas?parcial=1&versao=todas').get_data(as_text=True)
        assert 'Ficha v1' in html
        html = client.get(f'/professor/aluno/{aid}/estatisticas?parcial=1').get_data(as_text=True)
        assert 'Ficha v1' not in html  # só na visão "Todas as fichas"


class TestFrequenciaBaixa:
    def test_menos_de_uma_vez_por_semana(self, client, app):
        with app.app_context():
            prof = _professor('pr3_raro')
            al, v, ids, ex = _ficha_abc('pr3_raro_al')
            _sessao(al, v, ids['A'], ex, HOJE - timedelta(days=2))
            _sessao(al, v, ids['B'], ex, HOJE - timedelta(days=9))
            _vincular(db.session.get(User, al.id), prof)
        _login(client, 'pr3_raro')
        html = client.get('/professor/alunos').get_data(as_text=True)
        assert '2 treinos em 4 semanas' in html and '0,5× por semana' not in html