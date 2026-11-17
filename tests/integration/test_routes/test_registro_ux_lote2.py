"""Lote 2 da análise de UX: tela de registro de treino.

R1 sugere o próximo treino e mostra quando cada um foi feito; R3 resume a
última sessão num selo; R4 nomes em até 2 linhas; R5 "Cancelar" discreto;
R6 avisos embaixo; R7 busca do "+ Exercício" sem acento e por apelido.
"""
from datetime import date, datetime, timedelta

from models import db, ExercicioSistema, HistoricoTreino, RegistroTreino, TreinoVersao, VersaoExercicio
from routes.register_routes import _anotar_sugestao_treino
from tests.integration.test_routes.test_register_routes import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)

DATA = date(2026, 1, 12)  # segunda


def _ficha_abc(username):
    u = _criar_usuario(username)
    versao, treino_a, ex = _montar_versao_com_treino_e_exercicio(u.id)
    ids = {'A': treino_a}
    for cod in 'BC':
        t = TreinoVersao(versao_id=versao.id, codigo=cod, nome_treino=f'Treino {cod}', descricao_treino='d')
        db.session.add(t)
        db.session.flush()
        db.session.add(VersaoExercicio(treino_versao_id=t.id, exercicio_usuario_id=ex.id, ordem=0))
        ids[cod] = t.id
    db.session.commit()
    return u, versao, ids, ex


def _sessao(u, versao, treino_id, ex, dia, series=((40, 10), (40, 10), (40, 10))):
    r = RegistroTreino(treino_versao_id=treino_id, versao_id=versao.id, periodo='Janeiro/2026', semana=2,
                       exercicio_usuario_id=ex.id, data_registro=datetime.combine(dia, datetime.min.time()),
                       user_id=u.id)
    db.session.add(r)
    db.session.flush()
    for i, (carga, reps) in enumerate(series):
        db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=i))
    db.session.commit()


def _treinos(ids):
    return [{'id': ids[c], 'codigo': c, 'nome': f'Treino {c}', 'descricao': 'd'} for c in 'ABC']


class TestSugestaoProximoTreino:
    def test_sem_historico_sugere_o_primeiro(self, app):
        with app.app_context():
            u, _v, ids, _ex = _ficha_abc('sug_vazio')
            ts = _anotar_sugestao_treino(_treinos(ids), u.id, DATA)
            assert [t['sugerido'] for t in ts] == [True, False, False]
            assert all(t['ultimo_texto'] is None for t in ts)

    def test_sugere_o_seguinte_ao_ultimo_e_volta_ao_a(self, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_ciclo')
            _sessao(u, v, ids['A'], ex, DATA - timedelta(days=5))
            _sessao(u, v, ids['B'], ex, DATA - timedelta(days=3))
            ts = _anotar_sugestao_treino(_treinos(ids), u.id, DATA)
            assert [t['sugerido'] for t in ts] == [False, False, True]
            assert [t['ultimo_texto'] for t in ts] == ['há 5 dias', 'há 3 dias', None]
            _sessao(u, v, ids['C'], ex, DATA - timedelta(days=1))
            ts = _anotar_sugestao_treino(_treinos(ids), u.id, DATA)
            assert [t['sugerido'] for t in ts] == [True, False, False]
            assert ts[2]['ultimo_texto'] == 'ontem'

    def test_feito_hoje_conta_e_futuro_nao(self, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_hoje')
            _sessao(u, v, ids['A'], ex, DATA)
            _sessao(u, v, ids['C'], ex, DATA + timedelta(days=2))  # depois da data escolhida
            ts = _anotar_sugestao_treino(_treinos(ids), u.id, DATA)
            assert ts[0]['ultimo_texto'] == 'hoje'
            assert ts[2]['ultimo_texto'] is None
            assert [t['sugerido'] for t in ts] == [False, True, False]

    def test_dois_no_mesmo_dia_vale_o_registrado_por_ultimo(self, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_mesmo_dia')
            _sessao(u, v, ids['C'], ex, DATA)
            _sessao(u, v, ids['A'], ex, DATA)  # C e depois A, no mesmo dia
            ts = _anotar_sugestao_treino(_treinos(ids), u.id, DATA)
            assert [t['sugerido'] for t in ts] == [False, True, False]
            assert [t['ultimo_texto'] for t in ts] == ['hoje', None, 'hoje']

    def test_ficha_nova_comeca_pelo_primeiro(self, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_ficha_nova')
            _sessao(u, v, ids['B'], ex, DATA - timedelta(days=1))
            outra_ficha = [dict(t, id=t['id'] + 1000) for t in _treinos(ids)]
            ts = _anotar_sugestao_treino(outra_ficha, u.id, DATA)
            assert [t['sugerido'] for t in ts] == [True, False, False]
            assert all(t['ultimo_texto'] is None for t in ts)

    def test_ficha_de_um_treino_so_nao_marca_sugerido_depois_de_feito(self, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_um')
            _sessao(u, v, ids['A'], ex, DATA - timedelta(days=2))
            ts = _anotar_sugestao_treino(_treinos(ids)[:1], u.id, DATA)
            assert ts[0]['sugerido'] is False and ts[0]['ultimo_texto'] == 'há 2 dias'

    def test_tela_mostra_sugerido_e_ultimo(self, client, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('sug_tela')
            _sessao(u, v, ids['A'], ex, DATA - timedelta(days=2))
        _login(client, 'sug_tela')
        html = client.get(f'/registrar/registrar-treino?data={DATA.isoformat()}').get_data(as_text=True)
        assert html.count('class="treino-picker-sugerido"') == 1
        assert 'Último: há 2 dias' in html
        assert html.count('Ainda não feito nesta ficha') == 2
        bloco_b = html.split(f'data-treino-id="{ids["B"]}"')[0].rsplit('<button', 1)[1]
        assert 'is-sugerido' in bloco_b


class TestCardDoExercicio:
    def test_selo_unico_da_ultima_sessao(self, client, app):
        with app.app_context():
            u, v, ids, ex = _ficha_abc('selo_ultima')
            _sessao(u, v, ids['A'], ex, DATA - timedelta(days=2), series=((32.5, 8), (32.5, 8), (32.5, 8)))
            uid, vid, exid = u.id, v.id, ex.id
        _login(client, 'selo_ultima')
        url = f'/registrar/registrar-treino?data={DATA.isoformat()}&treino={ids["A"]}'
        html = client.get(url).get_data(as_text=True)
        assert 'Última: 32,5 kg × 8 · 3 séries' in html
        assert 'class="dash-badge">8x<' not in html and 'class="dash-badge">3 séries<' not in html
        with app.app_context():
            # séries diferentes entre si na sessão mais recente: maior carga
            from models import ExercicioUsuario, User, VersaoGlobal
            _sessao(db.session.get(User, uid), db.session.get(VersaoGlobal, vid), ids['B'],
                    db.session.get(ExercicioUsuario, exid), DATA - timedelta(days=1), series=((30, 10), (35, 8)))
        html = client.get(url).get_data(as_text=True)
        assert 'Última: até 35 kg · 2 séries' in html
        with app.app_context():
            # mesma carga, repetições diferentes: faixa de repetições
            from models import ExercicioUsuario, User, VersaoGlobal
            _sessao(db.session.get(User, uid), db.session.get(VersaoGlobal, vid), ids['C'],
                    db.session.get(ExercicioUsuario, exid), DATA, series=((32.5, 8), (32.5, 12), (32.5, 10)))
        amanha = f'/registrar/registrar-treino?data={(DATA + timedelta(days=1)).isoformat()}&treino={ids["A"]}'
        assert 'Última: 32,5 kg × 8–12 · 3 séries' in client.get(amanha).get_data(as_text=True)

    def test_selo_sem_carga_mostra_repeticoes(self, client, app):
        casos = (('selo_corporal', ((0, 12), (0, 10), (0, 8)), 'Última: 8–12 reps · 3 séries'),
                 ('selo_sem_carga', ((None, 15), (None, 15)), 'Última: 15 reps · 2 séries'))
        for nome, series, esperado in casos:
            with app.app_context():
                u, v, ids, ex = _ficha_abc(nome)
                _sessao(u, v, ids['A'], ex, DATA - timedelta(days=2), series=series)
            _login(client, nome)
            html = client.get(f'/registrar/registrar-treino?data={DATA.isoformat()}&treino={ids["A"]}'
                              ).get_data(as_text=True)
            assert esperado in html and 'Última: ·' not in html and '0 kg ×' not in html
            client.get('/auth/logout')

    def test_cancelar_discreto_e_nome_em_duas_linhas(self, client, app):
        with app.app_context():
            _u, _v, ids, _ex = _ficha_abc('cancelar_discreto')
        _login(client, 'cancelar_discreto')
        html = client.get(f'/registrar/registrar-treino?data={DATA.isoformat()}&treino={ids["A"]}').get_data(as_text=True)
        assert 'aria-label="Cancelar treino"' in html and 'class="btn-cancel-texto"' in html
        assert '-webkit-line-clamp: 2' in html

    def test_busca_do_seletor_tem_apelidos(self, client, app):
        with app.app_context():
            _u, _v, ids, _ex = _ficha_abc('busca_apelidos')
            db.session.add(ExercicioSistema(id_original='7777', nome='Extensão de perna na máquina',
                                            nicknames=['Cadeira extensora', 'Extensora'], grupo_muscular='Quadríceps'))
            db.session.commit()
        _login(client, 'busca_apelidos')
        html = client.get(f'/registrar/registrar-treino?data={DATA.isoformat()}&treino={ids["A"]}').get_data(as_text=True)
        assert 'data-apelidos="cadeira extensora extensora"' in html
        assert "normalize('NFD')" in html


class TestAvisos:
    def test_avisos_embaixo_e_tipo_danger_vermelho(self):
        with open('static/js/fitlog-utils.js', encoding='utf-8') as f:
            js = f.read()
        assert "if (type === 'danger') type = 'error';" in js
        assert 'bottom: 24px;' in js and 'top: 20px;\n                right: 20px;' not in js.replace('\r\n', '\n')
        assert 'body.fl-modo-treino-ativo #toast-container' in js