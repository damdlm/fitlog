"""Lote 4 da análise de UX.

T3: nomes de academia nos apelidos (migração só acrescenta) e busca por
relevância. E3: "ficha" no lugar de "versão" nos textos. E1: "Comece por
aqui". D1: últimos treinos por sessão + "Registrar próximo treino". E4:
Progresso sem registros com um aviso só. T5: seta do cartão encerrado.
"""
import glob
import importlib.util
import json
import unicodedata
from datetime import date, datetime, timedelta, timezone

from alembic.migration import MigrationContext
from alembic.operations import Operations

from models import db, ExercicioSistema, User
from services.billing_service import BillingService
from tests.integration.test_routes.test_register_routes import _criar_usuario, _login
from tests.integration.test_routes.test_registro_ux_lote2 import _ficha_abc, _sessao

MIGRACAO = glob.glob('migrations/versions/*_apelidos_academia_catalogo.py')[0]


def _migracao():
    spec = importlib.util.spec_from_file_location('mig_apelidos', MIGRACAO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _com_trial(username):
    u = User.query.filter_by(username=username).one()
    BillingService.iniciar_trial(u)
    db.session.commit()


def _norm(t):
    t = unicodedata.normalize('NFD', (t or '').lower())
    return ' '.join(''.join(c for c in t if unicodedata.category(c) != 'Mn').split())


class TestApelidosDeAcademia:
    def test_json_tem_os_apelidos_sem_repetir_entre_exercicios(self):
        mig = _migracao()
        with open('data/exercises.json', encoding='utf-8') as f:
            exercicios = json.load(f)
        por_id = {x['id']: x for x in exercicios}
        dono = {}
        for x in exercicios:
            for t in [x['name']] + (x.get('nicknames') or []):
                dono.setdefault(_norm(t), set()).add(x['id'])
        assert len(mig.APELIDOS) >= 50
        for id_original, apelidos in mig.APELIDOS.items():
            assert id_original in por_id
            for a in apelidos:
                assert a in por_id[id_original]['nicknames'], (id_original, a)
                assert dono[_norm(a)] == {id_original}, (a, dono[_norm(a)])
        assert 'Cadeira extensora' in por_id['0585']['nicknames']

    def test_migracao_so_acrescenta_e_volta_ao_original(self, app):
        mig = _migracao()
        with app.app_context():
            db.session.add_all([
                ExercicioSistema(id_original='0585', nome='Extensão de perna na máquina de alavanca',
                                 nicknames=['Extensão de perna na máquina']),
                ExercicioSistema(id_original='2331', nome='Bicicleta elíptica', nicknames=[]),
            ])
            db.session.commit()

            def rodar(f):
                with db.engine.begin() as conn:
                    with Operations.context(MigrationContext.configure(conn)):
                        f()

            def ler(i):
                db.session.expire_all()
                return db.session.query(ExercicioSistema).filter_by(id_original=i).one().nicknames

            rodar(mig.upgrade)
            rodar(mig.upgrade)  # de novo: não duplica
            assert ler('0585') == ['Extensão de perna na máquina', 'Cadeira extensora', 'Extensora',
                                   'Cadeira de extensão']
            assert ler('2331') == ['Elíptico', 'Transport', 'Transport elíptico']
            rodar(mig.downgrade)
            assert ler('0585') == ['Extensão de perna na máquina']
            assert ler('2331') == []

    def test_busca_por_relevancia_nas_duas_telas(self, client, app):
        with app.app_context():
            _ficha_abc('t3_busca')
            db.session.add(ExercicioSistema(id_original='9585', nome='Extensão de perna (teste)',
                                            nicknames=['Cadeira extensora (teste)', 'Extensora (teste)']))
            db.session.commit()
        _login(client, 't3_busca')
        cards = client.get('/aluno/catalogo-exercicios/cards').get_data(as_text=True)
        assert 'data-apelidos="cadeira extensora (teste)|extensora (teste)"' in cards and 'data-i="0"' in cards
        lista = client.get('/registrar/catalogo-avulso').get_data(as_text=True)
        assert 'data-apelidos="cadeira extensora (teste)|extensora (teste)"' in lista and 'data-i="0"' in lista
        with open('static/js/fitlog-utils.js', encoding='utf-8') as f:
            utils = f.read()
        assert 'function pontuarBusca(' in utils and 'pontuarBusca,' in utils
        with open('static/js/editar-treino-versao.js', encoding='utf-8') as f:
            assert 'U.pontuarBusca' in f.read()


class TestFichaNoLugarDeVersao:
    def test_telas_e_mensagens_falam_ficha(self, client, app):
        with app.app_context():
            u, v, _ids, _ex = _ficha_abc('e3_ficha')
            vid = v.id
        _login(client, 'e3_ficha')
        lista = client.get('/aluno/versoes').get_data(as_text=True)
        assert 'Minhas Fichas' in lista and 'Minhas Versões' not in lista
        detalhe = client.get(f'/aluno/versao/{vid}').get_data(as_text=True)
        assert 'Treinos desta ficha' in detalhe and 'Treinos desta versão' not in detalhe
        assert 'Editar Ficha' in detalhe

    def test_versao_do_ios_e_da_politica_continuam(self):
        with open('templates/register/registrar_treino.html', encoding='utf-8') as f:
            assert 'versões do iOS' in f.read()
        with open('templates/privacidade/politica.html', encoding='utf-8') as f:
            assert 'Versão 2026-08-31' in f.read()


class TestComecePorAqui:
    def test_conta_nova_ve_os_tres_passos(self, client, app):
        with app.app_context():
            _criar_usuario('e1_novo')
            _com_trial('e1_novo')
        _login(client, 'e1_novo')
        inicio = client.get('/').get_data(as_text=True)
        # tela inicial: faixa compacta com o próximo passo
        assert 'class="comece-mini"' in inicio and 'Próximo: <span data-comece-proximo>Monte sua ficha' in inicio
        painel = client.get('/aluno/dashboard').get_data(as_text=True)
        assert 'class="comece-card"' in painel and 'data-feitos="0"' in painel
        assert 'Monte sua ficha' in painel and 'Veja seu progresso' in painel
        assert "fitlog:comece:progresso:" in client.get('/aluno/estatisticas').get_data(as_text=True)

    def test_ficha_e_treino_feitos_marcam_dois_passos(self, client, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('e1_meio')
            _sessao(u, v, ids['A'], ex, date.today() - timedelta(days=1))
        _login(client, 'e1_meio')
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        assert 'data-feitos="2"' in html

    def test_conta_antiga_com_tudo_feito_nao_ve(self, client, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('e1_antigo')
            _sessao(u, v, ids['A'], ex, date.today() - timedelta(days=1))
            db.session.get(User, u.id).created_at = datetime.now(timezone.utc) - timedelta(days=90)
            db.session.commit()
        _login(client, 'e1_antigo')
        assert 'id="comeceCard"' not in client.get('/aluno/dashboard').get_data(as_text=True)

    def test_professor_nao_ve(self, client, app):
        with app.app_context():
            u = _criar_usuario('e1_prof')
            u.tipo_usuario = 'professor'
            db.session.commit()
        _login(client, 'e1_prof')
        assert 'id="comeceCard"' not in client.get('/').get_data(as_text=True)


class TestUltimosTreinosPorSessao:
    def test_um_cartao_por_dia_e_treino_com_volume_e_proximo(self, client, app):
        hoje = date.today()
        with app.app_context():
            u, v, ids, ex = _ficha_abc('d1_sessoes')
            # mesmo treino A em dois dias da mesma semana: antes viravam uma lista só
            _sessao(u, v, ids['A'], ex, hoje - timedelta(days=3), series=((40, 10), (40, 10)))
            _sessao(u, v, ids['A'], ex, hoje - timedelta(days=1), series=((50, 8), (50, 8), (50, 8)))
            id_b = ids['B']
        _login(client, 'd1_sessoes')
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        assert html.count('<details class="dash-sessao"') == 2
        ontem = (hoje - timedelta(days=1)).strftime('%d/%m')
        primeira = html.split('<details class="dash-sessao"', 2)[1]
        assert ontem in primeira and '1.200 kg' in primeira  # 50 × 8 × 3
        assert '50 kg × 8 · 3 séries' in primeira
        assert f'treino={id_b}' in html and 'Registrar próximo treino: B' in html

    def test_sem_registros(self, client, app):
        with app.app_context():
            _ficha_abc('d1_vazio')
        _login(client, 'd1_vazio')
        html = client.get('/aluno/dashboard').get_data(as_text=True)
        assert 'dash-sessao"' not in html and 'Registrar primeiro treino: A' in html


class TestProgressoVazio:
    def test_sem_registros_um_aviso_so(self, client, app):
        with app.app_context():
            _criar_usuario('e4_vazio')
            _com_trial('e4_vazio')
        _login(client, 'e4_vazio')
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        assert 'Registrar meu primeiro treino' in html
        assert 'id="kpiVolume"' not in html and 'chart.umd.min.js' not in html
        assert 'id="btnCompartilharEstatisticas"' not in html

    def test_com_registros_tela_normal(self, client, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('e4_cheio')
            _sessao(u, v, ids['A'], ex, date.today())
            _com_trial('e4_cheio')
        _login(client, 'e4_cheio')
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        assert 'Registrar meu primeiro treino' not in html
        assert 'id="kpiVolume"' in html and 'chart.umd.min.js' in html


class TestSetaDaFichaEncerrada:
    def test_cartao_nao_quebra_linha(self):
        with open('templates/aluno/versoes.html', encoding='utf-8') as f:
            css = f.read()
        assert '.v-card { flex-wrap: nowrap; }' in css and '.v-card > div:first-child { flex: 1 1 auto; min-width: 0; }' in css
