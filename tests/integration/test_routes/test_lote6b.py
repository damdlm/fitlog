"""Lote 6b da análise de UX.

T4: meta de séries × repetições por exercício da ficha (versao_exercicios
.meta_series / meta_reps_min / meta_reps_max), editada junto com a
observação, mostrada na ficha e na tela de registro, e usada pela dica de
progressão (R3). R2: séries uma a uma dentro do card no celular (a seta ›
abre a tabela no próprio card; o modal de séries saiu).
"""
import glob
import importlib.util
from datetime import date

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from models import db, AlunoProfessor, ExercicioSistema, TreinoVersao, VersaoExercicio, VersaoGlobal
from services.versao_service import VersaoService
from tests.integration.test_routes.test_lote5 import _professor
from tests.integration.test_routes.test_observacao_exercicio_treino import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)
from tests.integration.test_routes.test_registro_ux_lote2 import _ficha_abc, _sessao
from utils.meta_treino import formatar_meta, normalizar_meta, parse_meta_form, sugestao_progressao

MIGRACAO = glob.glob('migrations/versions/*_meta_series_repeticoes_ficha.py')[0]


class S:
    def __init__(self, carga, repeticoes):
        self.carga, self.repeticoes = carga, repeticoes


class TestMetaUtil:
    @pytest.mark.parametrize('entrada, esperado', [
        (('4', '10', '12'), (4, 10, 12)),
        (('4', '10', ''), (4, 10, 10)),        # número fixo
        (('', '', '12'), (None, 12, 12)),       # só o máximo também vira fixo
        (('3', '15', '12'), (3, 12, 15)),       # faixa invertida
        (('0', '0', '200'), (None, None, None)),  # fora dos limites
        (('11', 'abc', None), (None, None, None)),
        ((' 5 ', ' 8 ', ' 10 '), (5, 8, 10)),
    ])
    def test_normalizar(self, entrada, esperado):
        assert normalizar_meta(*entrada) == esperado

    def test_parse_form_so_devolve_quem_tem_meta(self):
        form = {'meta_series_b_1': '4', 'meta_reps_min_b_1': '10', 'meta_reps_max_b_1': '12',
                'meta_series_u_2': '', 'meta_reps_min_u_2': '', 'meta_reps_max_u_2': ''}
        assert parse_meta_form(form, ['b_1', 'u_2', 'b_3']) == {'b_1': (4, 10, 12)}

    @pytest.mark.parametrize('meta, texto', [
        ((4, 10, 12), '4 × 10–12'), ((4, 10, 10), '4 × 10'), ((1, None, None), '1 série'),
        ((3, None, None), '3 séries'), ((None, 8, 12), '8–12 reps'), ((None, None, None), ''),
    ])
    def test_formatar(self, meta, texto):
        assert formatar_meta(*meta) == texto

    def test_sugestao_de_progressao(self):
        assert sugestao_progressao([S(40, 12), S(40, 12), S(40, 13)], 10, 12) == 2.5
        assert sugestao_progressao([S(40, 12), S(40, 11)], 10, 12) is None       # uma série abaixo do topo
        assert sugestao_progressao([S(8, 15)], 12, 15) == 1.0                     # carga leve: +1 kg
        assert sugestao_progressao([S(0, 20)], 10, 12) is None                    # peso corporal
        assert sugestao_progressao([S(40, 12)], None, None) is None               # sem meta
        assert sugestao_progressao([], 10, 12) is None
        assert sugestao_progressao([{'carga': 30, 'repeticoes': 8}], 8, 8) == 2.5  # dict também


class TestMigracao:
    def test_cria_e_remove_as_tres_colunas(self, app):
        spec = importlib.util.spec_from_file_location('mig_meta', MIGRACAO)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert mig.down_revision == '0aa93ffc7a76'
        with app.app_context():
            def colunas():
                return {c['name'] for c in inspect(db.engine).get_columns('versao_exercicios')}

            def rodar(f):
                with db.engine.begin() as conn:
                    with Operations.context(MigrationContext.configure(conn)):
                        f()
            # o create_all dos testes já cria as colunas: desce, confere, sobe de novo
            assert {'meta_series', 'meta_reps_min', 'meta_reps_max'} <= colunas()
            rodar(mig.downgrade)
            assert not ({'meta_series', 'meta_reps_min', 'meta_reps_max'} & colunas())
            rodar(mig.upgrade)
            assert {'meta_series', 'meta_reps_min', 'meta_reps_max'} <= colunas()


class TestSalvarMeta:
    def _post(self, client, versao_id, tv_id, chave, **meta):
        data = {'nome_treino': 'Treino A', 'descricao_treino': '', 'exercicios[]': [chave],
                f'observacao_{chave}': 'pegada aberta'}
        for campo, valor in meta.items():
            data[f'{campo}_{chave}'] = valor
        return client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino/{tv_id}', data=data)

    def test_aluno_salva_meta_e_ela_aparece_na_ficha_e_no_editor(self, client, app):
        with app.app_context():
            user = _criar_usuario('meta_aluno')
            ex, versao, tv = _montar_versao_com_treino_e_exercicio(user)
            chave, vid, tid = f'u_{ex.id}', versao.id, tv.id
        _login(client, 'meta_aluno')
        resp = self._post(client, vid, tid, chave, meta_series='4', meta_reps_min='12', meta_reps_max='10')
        assert resp.status_code == 302
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=tid).one()
            assert (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max) == (4, 10, 12)
            assert ve.observacao == 'pegada aberta' and ve.meta_texto == '4 × 10–12'
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert '<span class="ct-ex-meta" title="Meta">4 × 10–12</span>' in html
        assert f'"{chave}": {{"max": 12, "min": 10, "s": 4}}' in html  # window.CT_TREINO_METAS

    def test_salvar_sem_meta_limpa_a_meta(self, client, app):
        with app.app_context():
            user = _criar_usuario('meta_limpa')
            ex, versao, tv = _montar_versao_com_treino_e_exercicio(user)
            chave, vid, tid = f'u_{ex.id}', versao.id, tv.id
        _login(client, 'meta_limpa')
        self._post(client, vid, tid, chave, meta_series='3', meta_reps_min='8')
        self._post(client, vid, tid, chave, meta_series='', meta_reps_min='', meta_reps_max='')
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=tid).one()
            assert (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max) == (None, None, None)

    def test_professor_salva_meta_na_ficha_do_aluno(self, client, app):
        with app.app_context():
            prof = _professor('meta_prof')
            aluno = _criar_usuario('meta_prof_aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            db.session.commit()
            ex, versao, tv = _montar_versao_com_treino_e_exercicio(aluno)
            chave, vid, tid, aid = f'u_{ex.id}', versao.id, tv.id, aluno.id
        _login(client, 'meta_prof')
        resp = client.post(f'/professor/aluno/{aid}/versao/{vid}/treino/{tid}', data={
            'nome_treino': 'Treino A', 'descricao_treino': '', 'exercicios[]': [chave],
            f'meta_series_{chave}': '5', f'meta_reps_min_{chave}': '6', f'meta_reps_max_{chave}': '8'})
        assert resp.status_code == 302
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=tid).one()
            assert (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max) == (5, 6, 8)

    def test_clonar_ficha_leva_a_meta(self, app):
        with app.app_context():
            prof = _professor('meta_clone_prof')
            aluno = _criar_usuario('meta_clone_aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            base = ExercicioSistema(nome='Supino', id_original='meta-clone-1')
            origem = VersaoGlobal(numero_versao=1, descricao='Modelo', divisao='LIVRE',
                                  data_inicio=date(2026, 1, 1), user_id=prof.id)
            db.session.add_all([base, origem])
            db.session.flush()
            tv = TreinoVersao(versao_id=origem.id, codigo='A', nome_treino='A')
            db.session.add(tv)
            db.session.flush()
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=base.id, ordem=0,
                                           meta_series=4, meta_reps_min=10, meta_reps_max=12))
            db.session.commit()

            def meta_da(versao):
                ve = VersaoExercicio.query.join(TreinoVersao).filter(TreinoVersao.versao_id == versao.id).one()
                return (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max)

            assert meta_da(VersaoService.clonar_versao_de_professor(origem.id, prof.id, aluno.id)) == (4, 10, 12)
            # clonar a própria ficha: só depois de encerrar a ativa
            origem.data_fim = date(2026, 2, 1)
            db.session.commit()
            assert meta_da(VersaoService.clonar_versao(origem.id, user_id=prof.id)) == (4, 10, 12)


class TestMetaNoRegistro:
    def _registro(self, app, client, username, meta, series_ultima):
        with app.app_context():
            u, v, ids, ex = _ficha_abc(username)
            ve = VersaoExercicio.query.filter_by(treino_versao_id=ids['A']).one()
            ve.meta_series, ve.meta_reps_min, ve.meta_reps_max = meta
            db.session.commit()
            if series_ultima:
                _sessao(u, v, ids['A'], ex, date(2026, 1, 5), series=series_ultima)
            tid = ids['A']
        _login(client, username)
        return client.get(f'/registrar/registrar-treino?treino={tid}').get_data(as_text=True)

    def test_selo_de_meta_e_dica_de_progressao(self, app, client):
        html = self._registro(app, client, 'meta_reg_1', (3, 8, 12), ((40, 12), (40, 12), (40, 12)))
        assert 'Meta: 3 × 8–12</span>' in html
        assert 'Bateu a meta: tente +2,5 kg</span>' in html
        assert 'placeholder="8–12"' in html
        assert 'data-meta-texto="3 × 8–12"' in html

    def test_sem_bater_a_meta_nao_ha_dica(self, app, client):
        html = self._registro(app, client, 'meta_reg_2', (3, 8, 12), ((40, 12), (40, 10), (40, 12)))
        assert 'Meta: 3 × 8–12</span>' in html
        assert 'Bateu a meta' not in html

    def test_sem_historico_a_meta_define_as_series(self, app, client):
        html = self._registro(app, client, 'meta_reg_3', (5, 10, 10), None)
        assert 'Meta: 5 × 10</span>' in html
        assert '<option value="5" selected>5 séries</option>' in html
        assert 'Bateu a meta' not in html

    def test_sem_meta_nada_muda(self, app, client):
        html = self._registro(app, client, 'meta_reg_4', (None, None, None), ((40, 10),))
        assert 'dash-badge--meta' not in html.split('</style>')[-1]
        assert 'data-meta-texto=""' in html


class TestSeriesNoCard:
    def test_seta_abre_a_tabela_no_card_e_o_modal_saiu(self, app, client):
        with app.app_context():
            _u, _v, ids, _ex = _ficha_abc('r2_card')
            tid = ids['A']
        _login(client, 'r2_card')
        html = client.get(f'/registrar/registrar-treino?treino={tid}').get_data(as_text=True)
        assert 'class="btn-abrir-series-modal btn-series-toggle"' in html
        assert 'aria-expanded="false"' in html
        assert 'modalSeriesIndividuais' not in html
        assert 'detalhe-series' not in html
        assert 'window.FitLogSeries = (function () {' in html
        assert 'inicializarSeriesNoCard();' in html
        # o modo tela cheia do desktop usa a mesma tabela
        assert html.count('window.FitLogSeries.montarTabela(row') == 2

    def test_tutorial_aponta_para_a_seta_nova(self):
        with open('static/js/registrar-treino-tour.js', encoding='utf-8') as f:
            src = f.read()
        assert "'#registroForm .btn-series-toggle'" in src

    def test_tutorial_explica_o_cardio(self):
        with open('static/js/registrar-treino-tour.js', encoding='utf-8') as f:
            src = f.read()
        assert "element: '#btnAdicionarCardio'" in src and "title: 'Cardio'" in src
        # logo depois do exercício avulso (o botão fica ao lado dele)
        assert src.index("title: 'Exercício avulso'") < src.index("title: 'Cardio'") \
            < src.index("title: 'Descanso entre séries'")


class TestRevisaoLote6b:
    """Revisão depois do commit do 6b."""

    @pytest.mark.parametrize('meta, texto', [
        ((4, 15, 10), '4 × 10–15'),   # invertida no banco (fora do formulário)
        ((3, None, 12), '3 × 12'),    # só o máximo
        ((None, 12, 8), '8–12 reps'),
    ])
    def test_formatar_se_protege_de_valores_do_banco(self, meta, texto):
        assert formatar_meta(*meta) == texto

    def test_progressao_com_faixa_invertida_usa_o_topo(self):
        assert sugestao_progressao([S(40, 12)] * 3, 12, 8) == 2.5
        assert sugestao_progressao([S(40, 10)] * 3, 12, 8) is None
        assert sugestao_progressao([S(40, 12)] * 3, None, 12) == 2.5

    def test_meta_acima_de_6_series_cabe_no_seletor(self, app, client):
        html = TestMetaNoRegistro()._registro(app, client, 'meta_reg_8', (8, 6, 6),
                                             ((40, 6), (40, 6), (40, 6)))
        assert '<option value="3" selected>3 séries</option>' in html  # histórico manda
        assert '<option value="8" >8 séries</option>' in html
        assert 'name="carga_' in html and '_8"' in html  # campo oculto da série 8

    def test_cardio_nao_recebe_meta(self, client, app):
        with app.app_context():
            user = _criar_usuario('meta_cardio')
            ex, versao, tv = _montar_versao_com_treino_e_exercicio(user)
            ex.modo_registro = 'tempo'
            db.session.commit()
            chave, vid, tid = f'u_{ex.id}', versao.id, tv.id
        _login(client, 'meta_cardio')
        TestSalvarMeta()._post(client, vid, tid, chave, meta_series='3', meta_reps_min='10')
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=tid).one()
            assert (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max) == (None, None, None)
            assert ve.observacao == 'pegada aberta'
            ve.meta_series = 3  # mesmo que chegue ao banco por outro caminho
            assert ve.meta_texto == ''
        cards = client.get('/aluno/catalogo-exercicios/cards').get_data(as_text=True)
        card = cards.split(f'data-valor="{chave}"')[1].split('</label>')[0]
        assert card.startswith(' data-cardio="1">')
        assert '>Observação <i class="bi bi-chevron-down">' in card

    def test_exercicio_de_carga_segue_com_meta_e_obs(self, client, app):
        with app.app_context():
            user = _criar_usuario('meta_carga_card')
            ex, _v, _t = _montar_versao_com_treino_e_exercicio(user)
            chave = f'u_{ex.id}'
        _login(client, 'meta_carga_card')
        cards = client.get('/aluno/catalogo-exercicios/cards').get_data(as_text=True)
        card = cards.split(f'data-valor="{chave}"')[1].split('</label>')[0]
        assert 'data-cardio' not in card and '>Meta e obs. <i' in card

    def test_js_nao_cria_meta_para_cardio(self):
        with open('static/js/editar-treino-versao.js', encoding='utf-8') as f:
            src = f.read()
        assert 'if (card.dataset.cardio) return null;' in src