"""Lote 6c da análise de UX.

E2: fichas prontas (data/fichas_prontas.py) criadas em um toque pelo aluno
sem ficha ativa e pelo professor para um aluno. Junto: data de início e de
fim da ficha pela data de Brasília (em UTC, das 21h à meia-noite a ficha
nascia "amanhã" e o registro da noite não a encontrava).
"""
import json
from datetime import date, datetime, timezone
from unittest import mock

import pytest

from data.fichas_prontas import FICHAS_POR_SLUG, FICHAS_PRONTAS
from models import db, ExercicioSistema, TreinoVersao, VersaoExercicio, VersaoGlobal
from services.versao_service import VersaoService
from tests.integration.test_routes.test_lote5 import _professor, _vincular
from tests.integration.test_routes.test_observacao_exercicio_treino import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)
from utils.meta_treino import SERIES_MAX, normalizar_meta

with open('data/exercises.json', encoding='utf-8') as _f:
    CATALOGO_JSON = {e['id']: e for e in json.load(_f)}

IDS_MODELOS = sorted({e[0] for f in FICHAS_PRONTAS for t in f['treinos'] for e in t['exercicios']})


def _semear_catalogo(pular=()):
    """Cria em exercicios_sistema os exercícios usados pelos modelos."""
    for o in IDS_MODELOS:
        if o in pular:
            continue
        e = CATALOGO_JSON[o]
        db.session.add(ExercicioSistema(
            id_original=o, nome=e['name'],
            modo_registro='tempo' if e.get('record_mode') == 'time' else 'carga',
        ))
    db.session.commit()


# Noite de 17/11 em São Paulo = madrugada de 18/11 em UTC
NOITE_UTC = datetime(2026, 11, 18, 1, 30, tzinfo=timezone.utc)


class _Noite(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOITE_UTC if tz is None or tz == timezone.utc else NOITE_UTC.astimezone(tz)


def _a_noite():
    return mock.patch('utils.format_utils.datetime', _Noite)


class TestModelos:
    def test_ids_existem_no_catalogo_e_nenhum_e_cardio(self):
        for o in IDS_MODELOS:
            assert o in CATALOGO_JSON, o
            assert CATALOGO_JSON[o].get('record_mode') != 'time', o

    def test_slugs_unicos_e_limites(self):
        assert len(FICHAS_POR_SLUG) == len(FICHAS_PRONTAS) == 4
        for f in FICHAS_PRONTAS:
            assert f['nome'] and f['detalhe'] and f['resumo']
            assert len(f['nome']) <= 200
            assert 1 <= len(f['treinos']) <= VersaoService.MAX_TREINOS_POR_VERSAO
            for t in f['treinos']:
                assert len(t['nome']) <= 100
                assert 1 <= len(t['exercicios']) <= VersaoService.MAX_EXERCICIOS_POR_TREINO
                ids = [e[0] for e in t['exercicios']]
                assert len(ids) == len(set(ids)), (f['slug'], t['nome'])
                for _o, s, rmin, rmax in t['exercicios']:
                    # meta já válida: normalizar não muda nada
                    assert normalizar_meta(s, rmin, rmax) == (s, rmin, rmax)
                    assert 1 <= s <= SERIES_MAX


class TestCriarDeModelo:
    def test_cria_ficha_completa_com_metas(self, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_completa')
            v = VersaoService.criar_de_modelo('hipertrofia-abc', user_id=u.id)
            assert v.descricao == 'Hipertrofia ABC' and v.data_fim is None and v.numero_versao == 1
            treinos = TreinoVersao.query.filter_by(versao_id=v.id).order_by(TreinoVersao.ordem).all()
            assert [t.codigo for t in treinos] == ['A', 'B', 'C']
            assert [t.nome_treino for t in treinos] == ['Peito, ombro e tríceps', 'Costas e bíceps', 'Pernas']
            primeiro = VersaoExercicio.query.filter_by(treino_versao_id=treinos[0].id).order_by(VersaoExercicio.ordem).first()
            assert primeiro.exercicio_base.id_original == '0025'
            assert (primeiro.meta_series, primeiro.meta_reps_min, primeiro.meta_reps_max) == (4, 8, 10)
            assert sum(len(t.exercicios) for t in treinos) == 21

    def test_exercicio_fora_do_catalogo_e_pulado(self, app):
        with app.app_context():
            _semear_catalogo(pular={'0025'})
            u = _criar_usuario('fp_pula')
            v = VersaoService.criar_de_modelo('hipertrofia-abc', user_id=u.id)
            a = TreinoVersao.query.filter_by(versao_id=v.id, codigo='A').one()
            assert len(a.exercicios) == 6

    def test_catalogo_vazio_nao_cria_nada(self, app):
        with app.app_context():
            u = _criar_usuario('fp_vazio')
            with pytest.raises(ValueError, match='montar do zero'):
                VersaoService.criar_de_modelo('iniciante-abc', user_id=u.id)
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 0

    def test_modelo_inexistente(self, app):
        with app.app_context():
            u = _criar_usuario('fp_inexistente')
            with pytest.raises(ValueError, match='não encontrada'):
                VersaoService.criar_de_modelo('nao-existe', user_id=u.id)

    def test_com_ficha_ativa_recusa(self, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_ativa')
            _montar_versao_com_treino_e_exercicio(u)
            with pytest.raises(ValueError, match='Finalize-a'):
                VersaoService.criar_de_modelo('em-casa', user_id=u.id)
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 1

    def test_erro_no_meio_desfaz_tudo(self, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_atomico')
            original = db.session.add

            def add_que_falha(obj, *a, **k):
                if isinstance(obj, VersaoExercicio) and obj.ordem == 2:
                    raise RuntimeError('falha simulada')
                return original(obj, *a, **k)

            with mock.patch.object(db.session, 'add', side_effect=add_que_falha):
                with pytest.raises(ValueError, match='Não foi possível criar a ficha'):
                    VersaoService.criar_de_modelo('full-body', user_id=u.id)
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 0
            assert TreinoVersao.query.count() == 0

    def test_criada_a_noite_comeca_hoje_no_brasil(self, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_noite')
            with _a_noite():
                v = VersaoService.criar_de_modelo('em-casa', user_id=u.id)
            assert v.data_inicio == date(2026, 11, 17)

    def test_previa_tem_nomes_e_metas(self, app):
        with app.app_context():
            _semear_catalogo()
            fichas = VersaoService.fichas_prontas_para_tela()
            assert [f['slug'] for f in fichas] == ['iniciante-abc', 'hipertrofia-abc', 'em-casa', 'full-body']
            a = fichas[1]['treinos'][0]
            assert a['codigo'] == 'A' and a['exercicios'][0] == {'nome': 'Supino reto com barra', 'meta': '4 × 8–10'}

    def test_previa_sem_catalogo_fica_vazia(self, app):
        with app.app_context():
            assert VersaoService.fichas_prontas_para_tela() == []


class TestTelaDoAluno:
    def test_sem_ficha_mostra_os_modelos_e_o_montar_do_zero(self, client, app):
        with app.app_context():
            _semear_catalogo()
            _criar_usuario('fp_tela')
        _login(client, 'fp_tela')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert html.count('class="fp-card"') == 4
        assert 'Comece com uma ficha pronta' in html and '<h2>Montar do zero</h2>' in html
        assert 'name="modelo" value="iniciante-abc"' in html
        assert '4 × 8–10' in html  # prévia com meta
        assert 'required autofocus' not in html  # teclado não abre por cima dos modelos

    def test_usar_ficha_cria_e_volta_para_a_ficha(self, client, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_usar')
            uid = u.id
        _login(client, 'fp_usar')
        resp = client.post('/aluno/cadastrar-treinos/ficha-pronta', data={'modelo': 'iniciante-abc'},
                           follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert 'Ficha &#34;Iniciante ABC&#34; criada!' in html or 'Ficha "Iniciante ABC" criada!' in html
        assert 'class="fp-card"' not in html  # já tem ficha: modelos somem
        assert '<span class="ct-ex-meta" title="Meta">3 × 12</span>' in html
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=uid, data_fim=None).count() == 1

    def test_segundo_envio_nao_duplica(self, client, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_duplo')
            uid = u.id
        _login(client, 'fp_duplo')
        client.post('/aluno/cadastrar-treinos/ficha-pronta', data={'modelo': 'em-casa'})
        html = client.post('/aluno/cadastrar-treinos/ficha-pronta', data={'modelo': 'em-casa'},
                           follow_redirects=True).get_data(as_text=True)
        assert 'Finalize-a antes de criar outra' in html
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=uid).count() == 1

    def test_registro_usa_a_meta_do_modelo(self, client, app):
        with app.app_context():
            _semear_catalogo()
            u = _criar_usuario('fp_registro')
            v = VersaoService.criar_de_modelo('hipertrofia-abc', user_id=u.id)
            tid = TreinoVersao.query.filter_by(versao_id=v.id, codigo='A').one().id
        _login(client, 'fp_registro')
        html = client.get(f'/registrar/registrar-treino?treino={tid}').get_data(as_text=True)
        assert 'Meta: 4 × 8–10</span>' in html
        assert '<option value="4" selected>4 séries</option>' in html

    def test_tutorial_tem_o_passo_das_fichas_prontas(self):
        with open('static/js/cadastrar-treinos-tour.js', encoding='utf-8') as f:
            src = f.read()
        assert "element: '#fichasProntas .fp-card'" in src


class TestTelaDoProfessor:
    def test_professor_ve_os_modelos_e_cria_para_o_aluno(self, client, app):
        with app.app_context():
            _semear_catalogo()
            prof = _professor('fp_prof')
            aluno = _criar_usuario('fp_prof_aluno')
            _vincular(aluno, prof)
            aid = aluno.id
        _login(client, 'fp_prof')
        html = client.get(f'/professor/aluno/{aid}/versao/nova').get_data(as_text=True)
        assert html.count('class="fp-card"') == 4
        assert 'Escolha um modelo para Fp_Prof_Aluno' in html
        resp = client.post(f'/professor/aluno/{aid}/versao/ficha-pronta', data={'modelo': 'full-body'})
        assert resp.status_code == 302
        with app.app_context():
            v = VersaoGlobal.query.filter_by(user_id=aid, data_fim=None).one()
            assert v.descricao == 'Full body'
            assert f'/professor/aluno/{aid}/versao/{v.id}' in resp.headers['Location']

    def test_professor_sem_vinculo_nao_cria(self, client, app):
        with app.app_context():
            _semear_catalogo()
            _professor('fp_prof_estranho')
            aluno = _criar_usuario('fp_aluno_de_outro')
            aid = aluno.id
        _login(client, 'fp_prof_estranho')
        client.post(f'/professor/aluno/{aid}/versao/ficha-pronta', data={'modelo': 'full-body'})
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aid).count() == 0


class TestDataDoBrasil:
    def test_ficha_criada_a_noite_comeca_hoje(self, app):
        with app.app_context():
            u = _criar_usuario('br_criar')
            with _a_noite():
                v = VersaoService.create_livre('Noite', user_id=u.id)
            assert v.data_inicio == date(2026, 11, 17)
            assert VersaoService.get_ativa_por_data('2026-11-17', user_id=u.id).id == v.id

    def test_finalizar_a_noite_termina_hoje(self, app):
        with app.app_context():
            u = _criar_usuario('br_finalizar')
            _ex, versao, _tv = _montar_versao_com_treino_e_exercicio(u)
            with _a_noite():
                v = VersaoService.finalizar_livre(versao.id, user_id=u.id)
            assert v.data_fim == date(2026, 11, 17)

    def test_dias_para_expirar_pela_data_do_brasil(self, app):
        with app.app_context():
            u = _criar_usuario('br_expirar')
            v = VersaoGlobal(numero_versao=1, descricao='x', divisao='LIVRE', user_id=u.id,
                             data_inicio=date(2026, 10, 17), validade_meses=1)
            with _a_noite():
                assert v.dias_para_expirar == 0  # vence 17/11, que ainda é hoje no Brasil
