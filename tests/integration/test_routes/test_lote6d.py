"""Lote 6d da análise de UX.

T2: uma tela só para ver e editar a ficha. "Cadastrar treinos" com ficha
ativa, "Minhas fichas" > ficha e a ficha do aluno vista pelo professor
usam aluno/ver_versao.html. Na ficha ativa, "Editar ficha" liga o modo
edição (ficha-modo-edicao.js); fora dele os controles ficam escondidos.
Os links antigos continuam valendo. O catálogo do editor não é mais
carregado pelas rotas (vem à parte, por catalogo_url).
"""
from datetime import date
from unittest import mock

from models import db, VersaoGlobal
from tests.integration.test_routes.test_lote5 import _professor, _vincular
from tests.integration.test_routes.test_observacao_exercicio_treino import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)


def _ficha(app, username):
    with app.app_context():
        u = _criar_usuario(username)
        _ex, v, tv = _montar_versao_com_treino_e_exercicio(u)
        return u.id, v.id, tv.id


def _sem_catalogo():
    """As telas da ficha não podem depender do catálogo completo."""
    return mock.patch('services.exercicio_service.ExercicioService.get_exercicios_completos',
                      side_effect=AssertionError('catálogo carregado pela rota'))


class TestFichaAtiva:
    def test_cadastrar_treinos_mostra_a_tela_da_ficha(self, client, app):
        _uid, vid, tid = _ficha(app, 't2_ativa')
        _login(client, 't2_ativa')
        with _sem_catalogo():
            html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'id="ctFicha"' in html and 'data-editavel="1"' in html
        assert 'class="ct-ficha" id="ctFicha"' in html  # abre para leitura
        assert 'id="btnModoEdicao" aria-pressed="false"' in html
        assert '>Editar ficha</span>' in html
        # ações voltam para "Cadastrar treinos"
        assert f'/aluno/cadastrar-treinos/{vid}/treino/{tid}"' in html
        assert f'/aluno/cadastrar-treinos/{vid}/editar"' in html
        assert '<i class="bi bi-layers"></i> Ver Fichas' in html
        # catálogo à parte, com a grade em lotes
        assert 'class="etv-grid etv-grid-static" id="etvGrid"' in html
        assert 'data-catalogo-url="/aluno/catalogo-exercicios/cards"' in html

    def test_controles_so_aparecem_no_modo_edicao(self, client, app):
        _ficha(app, 't2_controles')
        _login(client, 't2_controles')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'ct-btn-editar-exercicios ct-so-edicao"' in html
        assert 'ct-btn-excluir-treino ct-so-edicao"' in html
        assert 'class="ct-add-treino-btn ct-btn-editar-exercicios ct-so-edicao"' in html
        assert 'ct-hero-desc-edit ct-so-edicao"' in html
        assert '.ct-ficha:not(.is-editando) .ct-so-edicao { display: none !important; }' in html
        assert '/static/js/ficha-modo-edicao.' in html

    def test_modal_do_treino_fecha_com_confirmacao(self, client, app):
        _ficha(app, 't2_modal')
        _login(client, 't2_modal')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        modal = html.split('id="modalExercicios"')[1].split('id="modalCriarExercicio"')[0]
        assert 'data-bs-backdrop="static" data-bs-keyboard="false"' in modal
        assert 'data-bs-dismiss="modal"' not in modal
        assert modal.count('data-etv-cancelar') == 2

    def test_ficha_sem_treino_ja_abre_em_edicao(self, client, app):
        with app.app_context():
            u = _criar_usuario('t2_vazia')
            db.session.add(VersaoGlobal(numero_versao=1, descricao='Nova', divisao='LIVRE',
                                        data_inicio=date(2026, 1, 1), user_id=u.id))
            db.session.commit()
        _login(client, 't2_vazia')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'class="ct-ficha is-editando" id="ctFicha"' in html
        assert 'Adicionar treino (0/' in html

    def test_salvar_treino_volta_para_cadastrar_treinos(self, client, app):
        _uid, vid, tid = _ficha(app, 't2_salvar')
        _login(client, 't2_salvar')
        resp = client.post(f'/aluno/cadastrar-treinos/{vid}/treino/{tid}',
                           data={'nome_treino': 'Peito', 'exercicios[]': []})
        assert resp.status_code == 302 and resp.headers['Location'].endswith('/aluno/cadastrar-treinos')


class TestMinhasFichas:
    def test_ficha_ativa_pelo_link_antigo(self, client, app):
        _uid, vid, tid = _ficha(app, 't2_link')
        _login(client, 't2_link')
        with _sem_catalogo():
            html = client.get(f'/aluno/versao/{vid}').get_data(as_text=True)
        assert 'id="btnModoEdicao"' in html
        assert f'/aluno/versao/{vid}/treino/{tid}"' in html  # ações voltam para a própria ficha
        assert 'Voltar para Minhas Fichas' in html and 'Ver Fichas' not in html

    def test_ficha_encerrada_so_leitura(self, client, app):
        with app.app_context():
            u = _criar_usuario('t2_encerrada')
            _ex, v, _tv = _montar_versao_com_treino_e_exercicio(u)
            v.data_fim = date(2026, 2, 1)
            db.session.commit()
            vid = v.id
        _login(client, 't2_encerrada')
        html = client.get(f'/aluno/versao/{vid}').get_data(as_text=True)
        assert 'data-editavel="0"' in html
        assert 'id="btnModoEdicao"' not in html
        assert 'class="btn btn-sm ct-btn-treino ct-btn-excluir-treino' not in html
        assert 'Sim, clonar' in html
        assert "sessionStorage.getItem('fitlog:ficha-editando" not in html


class TestProfessor:
    def test_professor_ve_a_mesma_tela(self, client, app):
        with app.app_context():
            prof = _professor('t2_prof')
            aluno = _criar_usuario('t2_prof_aluno')
            _vincular(aluno, prof)
            _ex, v, tv = _montar_versao_com_treino_e_exercicio(aluno)
            aid, vid, tid = aluno.id, v.id, tv.id
        _login(client, 't2_prof')
        with _sem_catalogo():
            html = client.get(f'/professor/aluno/{aid}/versao/{vid}').get_data(as_text=True)
        assert 'id="btnModoEdicao"' in html
        assert f'/professor/aluno/{aid}/versao/{vid}/treino/{tid}"' in html
        assert 'class="etv-grid etv-grid-static" id="etvGrid"' in html
        assert 'data-contexto="professor"' in html


class TestSemFicha:
    def test_tela_sem_ficha_nao_carrega_o_editor(self, client, app):
        with app.app_context():
            _criar_usuario('t2_sem')
        _login(client, 't2_sem')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'class="ct-empty-form' in html
        assert 'modalExercicios' not in html and 'ctFicha' not in html
        assert 'editar-treino-versao.js' not in html and 'cadastrar-treinos-tour.' in html


class TestScripts:
    def test_modo_edicao_lembra_por_ficha(self):
        with open('static/js/ficha-modo-edicao.js', encoding='utf-8') as f:
            js = f.read()
        assert "'fitlog:ficha-editando:'" in js and 'sessionStorage' in js
        assert 'window.FitLogFicha' in js

    def test_tutorial_da_ficha_mostra_o_modo_edicao(self):
        with open('static/js/ver-versao-tour.js', encoding='utf-8') as f:
            js = f.read()
        assert "element: '#btnModoEdicao'" in js
        assert 'ficha.definir(true, { lembrar: false })' in js and 'aoEncerrar' in js

    def test_tutorial_de_cadastrar_so_tem_a_tela_sem_ficha(self):
        with open('static/js/cadastrar-treinos-tour.js', encoding='utf-8') as f:
            js = f.read()
        assert 'passos: { semversao: passosSemVersao }' in js
        assert 'btnTourCadastrarLista' not in js and 'passosModal' not in js


class TestRevisaoLote6d:
    """Revisão depois do commit do 6d."""

    def test_titulo_para_leitor_de_tela(self, client, app):
        _ficha(app, 't2_h1')
        _login(client, 't2_h1')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert '<h1 class="visually-hidden">V1</h1>' in html

    def test_botao_de_modo_com_contraste_e_toque(self, client, app):
        _ficha(app, 't2_botao')
        _login(client, 't2_botao')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'min-height: 44px;' in html.split('.ct-modo-btn {')[1].split('}')[0]
        assert '.ct-ficha.is-editando .ct-modo-btn { background: #fff1e3; border-color: #a8560c; }' in html