"""Aviso de valor digitado errado na tela de registrar treino (nov/2026).

Um número muito fora do histórico (300 no lugar de 30) vira a "última
vez" do próximo treino e um recorde falso. A tela pergunta antes de
marcar o exercício como feito e antes de salvar; a regra fica em
static/js/modules/valor-suspeito.js e as referências vêm do servidor:
o recorde de carga e de reps de todo o histórico
(ExercicioService.get_recordes_em_lote) e a carga da última vez.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from models import db, HistoricoTreino, RegistroTreino, TreinoVersao, VersaoExercicio, VersaoGlobal
from services.exercicio_service import ExercicioService
from tests.unit.test_services.test_exercicio_service_extra import (
    _criar_exercicio_base, _criar_exercicio_usuario, _criar_usuario, _criar_versao_com_treino as _criar_versao_base,
)

RAIZ = Path(__file__).resolve().parents[3]


def _criar_versao_com_treino(usuario_id, codigo='A'):
    """Ficha que começou há 30 dias. O helper compartilhado usa date.today() (data UTC
    do servidor); entre 21h e meia-noite de Brasília ela já é "amanhã" para a tela
    de registro, que usa o dia de Brasília, e a ficha não aparecia."""
    versao, tv = _criar_versao_base(usuario_id, codigo)
    versao.data_inicio = versao.data_inicio - timedelta(days=30)
    db.session.commit()
    return versao, tv


def _ler(caminho):
    return (RAIZ / caminho).read_text(encoding='utf-8').replace('\r\n', '\n')


class _Ex:
    def __init__(self, id_, tipo):
        self.id = id_
        self.tipo = tipo
        self.prefixo = 'u_' if tipo == 'usuario' else 'b_'


def _registro(user, versao, tv, series, base_id=None, usuario_id=None, dias_atras=1):
    r = RegistroTreino(
        treino_versao_id=tv.id, versao_id=versao.id, periodo='2026-11', semana=1,
        data_registro=datetime.now(timezone.utc) - timedelta(days=dias_atras),
        user_id=user.id, exercicio_base_id=base_id, exercicio_usuario_id=usuario_id,
    )
    db.session.add(r)
    db.session.commit()
    for i, s in enumerate(series, start=1):
        db.session.add(HistoricoTreino(registro_id=r.id, ordem=i, **s))
    db.session.commit()
    return r


class TestRecordesEmLote:
    def test_maximo_de_carga_e_reps_em_todas_as_fichas(self, app, db):
        user = _criar_usuario('vs_rec_1')
        base = _criar_exercicio_base('Supino VS')
        v1, tv1 = _criar_versao_com_treino(user.id)
        v2 = VersaoGlobal(numero_versao=2, descricao='V2', divisao='AB', data_inicio=date.today(), user_id=user.id)
        db.session.add(v2)
        db.session.commit()
        tv2 = TreinoVersao(versao_id=v2.id, codigo='A', nome_treino='Treino A')
        db.session.add(tv2)
        db.session.commit()
        _registro(user, v1, tv1, [{'carga': 40, 'repeticoes': 8}, {'carga': 35, 'repeticoes': 12}], base_id=base.id, dias_atras=40)
        _registro(user, v2, tv2, [{'carga': 37.5, 'repeticoes': 10}], base_id=base.id)
        rec = ExercicioService.get_recordes_em_lote([_Ex(base.id, 'base')], user_id=user.id)
        # recorde vem da ficha antiga; reps é o maior número, de outra série
        assert rec == {f'b_{base.id}': {'carga': 40.0, 'reps': 12}}

    def test_cardio_e_outros_usuarios_ficam_de_fora(self, app, db):
        user = _criar_usuario('vs_rec_2')
        outro = _criar_usuario('vs_rec_2b')
        base = _criar_exercicio_base('Esteira VS')
        v, tv = _criar_versao_com_treino(user.id)
        vo, tvo = _criar_versao_com_treino(outro.id)
        _registro(user, v, tv, [{'carga': 0, 'repeticoes': None, 'duracao_segundos': 1800}], base_id=base.id)
        _registro(outro, vo, tvo, [{'carga': 200, 'repeticoes': 50}], base_id=base.id)
        assert ExercicioService.get_recordes_em_lote([_Ex(base.id, 'base')], user_id=user.id) == {}

    def test_chave_separa_exercicio_proprio_e_do_catalogo(self, app, db):
        user = _criar_usuario('vs_rec_3')
        base = _criar_exercicio_base('Remada VS')
        proprio = _criar_exercicio_usuario(user.id, nome='Remada minha')
        v, tv = _criar_versao_com_treino(user.id)
        _registro(user, v, tv, [{'carga': 50, 'repeticoes': 10}], base_id=base.id)
        _registro(user, v, tv, [{'carga': 20, 'repeticoes': 15}], usuario_id=proprio.id)
        rec = ExercicioService.get_recordes_em_lote([_Ex(base.id, 'base'), _Ex(proprio.id, 'usuario')], user_id=user.id)
        assert rec[f'b_{base.id}'] == {'carga': 50.0, 'reps': 10}
        assert rec[f'u_{proprio.id}'] == {'carga': 20.0, 'reps': 15}

    def test_lista_vazia(self, app, db):
        user = _criar_usuario('vs_rec_4')
        assert ExercicioService.get_recordes_em_lote([], user_id=user.id) == {}


class TestTelaDeRegistro:
    def test_card_leva_recorde_e_tela_carrega_o_aviso(self, client, app):
        with app.app_context():
            user = _criar_usuario('vs_tela')
            base = _criar_exercicio_base('Agachamento VS')
            v, tv = _criar_versao_com_treino(user.id)
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=base.id, ordem=0))
            db.session.commit()
            _registro(user, v, tv, [{'carga': 60, 'repeticoes': 8}], base_id=base.id, dias_atras=2)
            tid, bid = tv.id, base.id
        client.post('/auth/login', data={'username': 'vs_tela', 'password': 'SenhaForte123!'})
        html = client.get(f'/registrar/registrar-treino?treino={tid}').get_data(as_text=True)
        linha = html[html.index(f'data-exercicio-id="b_{bid}"'):][:600]
        assert 'data-recorde-carga="60.0"' in linha and 'data-recorde-reps="8"' in linha
        assert 'id="modalValorSuspeito"' in html
        assert 'js/modules/valor-suspeito.js' in html
        # acima do modo treino em tela cheia (1900), como os outros modais
        assert '#modalCardio,\n    #modalValorSuspeito {\n        z-index: 2000;' in html.replace('\r\n', '\n')
        # o salvar consulta o aviso antes de enviar
        assert 'window.FitLogValorSuspeito.conferirAntesDeSalvar(function () {\n                form.requestSubmit();' in html.replace('\r\n', '\n')


class TestRegraNoNavegador:
    def test_regras_e_pontos_de_parada(self):
        js = _ler('static/js/modules/valor-suspeito.js')
        assert 'v.carga > recC * 2 && v.carga - recC >= 10' in js
        assert 'v.carga > 0 && ultC !== null && v.carga < ultC / 2 && ultC - v.carga >= 10' in js
        assert 'v.reps > recR * 2 && v.reps - recR >= 10' in js
        # valor confirmado não é perguntado de novo enquanto não mudar
        assert "row.dataset.valorConfirmado === assinatura(row)" in js
        # cardio e exercício desligado não entram
        assert "row.classList.contains('exercise-row--cardio')" in js
        # ao marcar como feito, na captura (antes do handler do botão)
        assert "if (!btn || btn.classList.contains('is-ativo')) return;" in js
        assert 'evt.stopImmediatePropagation();' in js
