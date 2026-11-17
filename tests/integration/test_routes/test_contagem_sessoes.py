"""Treino = sessão (um treino num dia), não registro (um por exercício).

Cada exercício salvo vira um RegistroTreino; contar registros mostrava ~5x
mais "treinos" do que os feitos (KPI "Treinos realizados" da página
Progresso; "Última atividade dos alunos" e "Treinos nos últimos 30 dias"
do painel do professor). Também cobre a formatação pt-BR de números/pesos.
"""
from datetime import datetime, timedelta

from models import db, AlunoProfessor, ExercicioUsuario, User
from services.dashboard_service import DashboardService
from services.estatistica_service import EstatisticaService
from tests.integration.test_routes.test_estatisticas_periodo import _logar, _montar, _registrar
from utils.format_utils import formatar_kg, formatar_numero_br


def _segundo_exercicio(app, uid):
    with app.app_context():
        ex = ExercicioUsuario(usuario_id=uid, nome='Crucifixo')
        db.session.add(ex)
        db.session.commit()
        return ex.id


def _sessao(app, uid, vid, exs, tid, dias_atras):
    """Uma sessão = vários exercícios no mesmo treino e dia."""
    for ex in exs:
        _registrar(app, uid, vid, ex, tid, dias_atras, carga=10, reps=10, series=3)


class TestKpiTreinosPorSessao:
    def test_kpi_conta_sessoes_nao_exercicios(self, client, app):
        uid, vid, ex1, treinos = _montar(app, 'sessoes_kpi')
        ex2 = _segundo_exercicio(app, uid)
        _sessao(app, uid, vid, [ex1, ex2], treinos['A'], 1)   # 1 sessão, 2 registros
        _sessao(app, uid, vid, [ex1, ex2], treinos['B'], 3)   # 1 sessão, 2 registros
        _sessao(app, uid, vid, [ex1], treinos['A'], 40)       # período anterior
        _logar(client, app, uid)
        k = client.get('/api/kpis?dias=30').get_json()
        assert k['treinos_realizados'] == 2
        assert k['total_series'] == 12
        assert k['treinos_variacao'] == 100.0  # 2 agora vs 1 antes

    def test_dois_treinos_no_mesmo_dia_sao_duas_sessoes(self, app):
        uid, vid, ex1, treinos = _montar(app, 'sessoes_mesmo_dia')
        _sessao(app, uid, vid, [ex1], treinos['A'], 2)
        _sessao(app, uid, vid, [ex1], treinos['B'], 2)
        with app.app_context():
            assert EstatisticaService.calcular_kpis_periodo(user_id=uid, dias=30)['treinos_realizados'] == 2


class TestPainelProfessorPorSessao:
    def test_atividade_uma_linha_por_sessao_e_grafico_conta_sessoes(self, app):
        uid, vid, ex1, treinos = _montar(app, 'sessoes_prof_aluno')
        ex2 = _segundo_exercicio(app, uid)
        _sessao(app, uid, vid, [ex1, ex2], treinos['A'], 1)
        _sessao(app, uid, vid, [ex1, ex2], treinos['B'], 2)
        with app.app_context():
            aluno = db.session.get(User, uid)
            hoje = datetime.now()
            hoje = datetime(hoje.year, hoje.month, hoje.day)
            atividade = DashboardService._atividade_recente([uid])
            assert [(a['treino_codigo'], a['exercicios']) for a in atividade] == [('A', 2), ('B', 2)]
            assert all(a['aluno_nome'] == (aluno.nome_completo or aluno.username) for a in atividade)
            grafico = DashboardService._grafico_30_dias([uid], hoje + timedelta(days=1))
            assert sum(grafico['valores']) == 2  # 4 registros, 2 sessões

    def test_painel_mostra_quantidade_de_exercicios(self, client, app):
        uid, vid, ex1, treinos = _montar(app, 'sessoes_prof_tela')
        ex2 = _segundo_exercicio(app, uid)
        _sessao(app, uid, vid, [ex1, ex2], treinos['A'], 1)
        with app.app_context():
            from services.billing_service import BillingService
            prof = User(username='sessoes_prof', email='sessoes_prof@t.com', tipo_usuario='professor')
            prof.set_password('x' * 12)
            db.session.add(prof)
            db.session.flush()
            BillingService.iniciar_trial(prof)
            db.session.add(AlunoProfessor(aluno_id=uid, professor_id=prof.id))
            db.session.commit()
            prof_id = prof.id
        _logar(client, app, prof_id)
        html = client.get('/professor/dashboard').get_data(as_text=True)
        assert 'Treino A · 2 exercícios ·' in html
        assert html.count('Treino A · ') == 1


class TestFormatoBrasileiro:
    def test_numeros_e_pesos(self):
        assert formatar_numero_br(104025) == '104.025'
        assert formatar_numero_br(32.5) == '32,5'
        assert formatar_numero_br(40.0) == '40'
        assert formatar_numero_br(43.333) == '43,3'
        assert formatar_numero_br(1234.56, 2) == '1.234,56'
        assert formatar_numero_br(None) == '—'
        assert formatar_numero_br('abc') == 'abc'
        assert formatar_kg(59585, 0) == '59.585 kg'
        assert formatar_kg('12.5') == '12,5 kg'
        assert formatar_kg(None) == '—'

    def test_filtros_no_template(self, app):
        with app.app_context():
            tpl = app.jinja_env.from_string('{{ 104025|kg(0) }} | {{ 32.5|kg }} | {{ 1500.75|num_br(2) }}')
            assert tpl.render() == '104.025 kg | 32,5 kg | 1.500,75'

    def test_eixo_do_1rm_nao_usa_tres_casas(self, app):
        with open('templates/aluno/estatisticas.html', encoding='utf-8') as f:
            html = f.read()
        assert 'toFixed(3)' not in html
        assert 'FitLogUtils.formatarKg(ctx.parsed.y)' in html
