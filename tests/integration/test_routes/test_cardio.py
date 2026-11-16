"""Registro de CARDIO por tempo (services/cardio.py).

Exercícios com modo_registro='tempo' (esteira, bike, caminhada...) gravam
tempo/distância/intensidade em vez de carga/repetições. Cobre o parse dos
campos, o salvar pela tela de registro (linha da ficha, troca de tipo pelo
combo, cardio avulso pelo "+ Cardio"), a edição pelo calendário, o cartão
da página Progresso, o cadastro de exercício próprio como cardio e que nada
que soma volume/séries quebre ou conte o cardio como força.
"""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from models import (
    db, ExercicioSistema, ExercicioUsuario, HistoricoTreino, RegistroTreino, VersaoExercicio,
)
from services import cardio
from tests.integration.test_routes.test_register_routes import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)

DATA = '2026-01-05'  # segunda-feira


# ---------------------------------------------------------------- helpers

def _catalogo_cardio():
    """Esteira, Bike e Caminhada (cardio) + Supino do catálogo (força)."""
    itens = {}
    for id_original, nome, modo in (('9001', 'Esteira', 'tempo'), ('9002', 'Bicicleta ergométrica', 'tempo'),
                                    ('9005', 'Caminhada', 'tempo'), ('0025', 'Supino do catálogo', 'carga')):
        ex = ExercicioSistema.query.filter_by(id_original=id_original).first()
        if ex is None:
            ex = ExercicioSistema(id_original=id_original, nome=nome, modo_registro=modo, grupo_muscular='Cardio')
            db.session.add(ex)
            db.session.flush()
        itens[id_original] = ex
    db.session.commit()
    return itens


def _montar(username):
    """Usuário com treino A = Supino (próprio, força) + Esteira (catálogo)."""
    u = _criar_usuario(username)
    versao, treino_id, supino = _montar_versao_com_treino_e_exercicio(u.id)
    cat = _catalogo_cardio()
    db.session.add(VersaoExercicio(treino_versao_id=treino_id, exercicio_base_id=cat['9001'].id, ordem=1))
    db.session.commit()
    return {
        'user_id': u.id, 'treino_id': treino_id, 'versao_id': versao.id,
        'supino': f'u_{supino.id}', 'supino_id': supino.id,
        'esteira': f'b_{cat["9001"].id}', 'esteira_id': cat['9001'].id,
        'bike': f'b_{cat["9002"].id}', 'bike_id': cat['9002'].id,
        'caminhada': f'b_{cat["9005"].id}', 'caminhada_id': cat['9005'].id,
        'supino_catalogo': f'b_{cat["0025"].id}',
    }


def _series_do(user_id, base_id=None, usuario_id=None):
    q = RegistroTreino.query.filter_by(user_id=user_id)
    if base_id is not None:
        q = q.filter_by(exercicio_base_id=base_id)
    if usuario_id is not None:
        q = q.filter_by(exercicio_usuario_id=usuario_id)
    regs = q.all()
    return [s for r in regs for s in HistoricoTreino.query.filter_by(registro_id=r.id).all()]


# ---------------------------------------------------------------- parse

class TestLerCardioDoFormulario:
    def test_minutos_viram_segundos_e_campos_opcionais(self):
        form = MultiDict({'duracao_b_1': '25', 'distancia_b_1': '8,5', 'intensidade_b_1': 'Moderada'})
        assert cardio.ler_cardio_do_formulario(form, 'b_1') == {
            'duracao_segundos': 1500, 'distancia_km': 8.5, 'intensidade': 'moderada'}

    @pytest.mark.parametrize('duracao', ['', '0', '-5', 'abc', '601'])
    def test_sem_tempo_valido_a_linha_nao_conta(self, duracao):
        assert cardio.ler_cardio_do_formulario(MultiDict({'duracao_x': duracao}), 'x') is None

    def test_distancia_e_intensidade_invalidas_sao_ignoradas(self):
        form = MultiDict({'duracao_x': '10', 'distancia_x': '-3', 'intensidade_x': 'extrema'})
        assert cardio.ler_cardio_do_formulario(form, 'x') == {
            'duracao_segundos': 600, 'distancia_km': None, 'intensidade': None}

    def test_formatos_e_resumo(self):
        assert cardio.formatar_duracao(1500) == '25 min'
        assert cardio.formatar_duracao(5400) == '1h30'
        assert cardio.formatar_distancia(2.5) == '2,5 km'
        assert cardio.ritmo_e_velocidade(1500, 5) == ('5:00 /km', '12,0 km/h')
        assert cardio.ritmo_e_velocidade(1500, None) == (None, None)
        serie = SimpleNamespace(duracao_segundos=1500, distancia_km=8.5, intensidade='forte', carga=None, repeticoes=None)
        assert cardio.resumo_serie_cardio(serie) == '25 min · 8,5 km · Forte'
        assert cardio.volume_da_serie(serie) == 0
        assert cardio.serie_para_dict(serie)['cardio'] is True
        forca = SimpleNamespace(duracao_segundos=None, carga=40, repeticoes=10)
        assert cardio.volume_da_serie(forca) == 400
        assert cardio.serie_para_dict(forca) == {'carga': 40.0, 'repeticoes': 10}


# ---------------------------------------------------------------- tela de registro

class TestRegistrarCardio:
    def test_tela_mostra_linha_de_cardio_com_combo_e_modal(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_get')
        _login(client, 'cardio_get')
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}').get_data(as_text=True)
        assert 'exercise-row--cardio' in html
        assert f'name="cardio_tipo_{ctx["esteira"]}"' in html
        assert f'name="duracao_{ctx["esteira"]}"' in html
        assert f'name="intensidade_{ctx["esteira"]}"' in html
        assert 'id="modalCardio"' in html and 'id="tplCardioAvulso"' in html
        assert 'id="btnAdicionarCardio"' in html
        # a linha de força continua igual
        assert f'name="carga_{ctx["supino"]}"' in html
        assert f'name="carga_{ctx["esteira"]}"' not in html

    def test_salva_forca_e_cardio_da_ficha(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_post')
        _login(client, 'cardio_post')
        resp = client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'carga_{ctx["supino"]}': '40', f'reps_{ctx["supino"]}': '10', f'num_series_{ctx["supino"]}': '3',
            f'cardio_tipo_{ctx["esteira"]}': ctx['esteira'],
            f'duracao_{ctx["esteira"]}': '20', f'distancia_{ctx["esteira"]}': '3', f'intensidade_{ctx["esteira"]}': 'leve',
        })
        assert resp.status_code == 302
        with app.app_context():
            esteira = _series_do(ctx['user_id'], base_id=ctx['esteira_id'])
            assert [(s.carga, s.repeticoes, s.duracao_segundos, float(s.distancia_km), s.intensidade)
                    for s in esteira] == [(None, None, 1200, 3.0, 'leve')]
            assert len(_series_do(ctx['user_id'], usuario_id=ctx['supino_id'])) == 3

    def test_so_cardio_ja_e_um_treino_valido(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_so')
        _login(client, 'cardio_so')
        client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'carga_{ctx["supino"]}': '', f'reps_{ctx["supino"]}': '',
            f'duracao_{ctx["esteira"]}': '30',
        })
        with app.app_context():
            assert len(_series_do(ctx['user_id'], base_id=ctx['esteira_id'])) == 1
            assert _series_do(ctx['user_id'], usuario_id=ctx['supino_id']) == []

    def test_combo_troca_o_tipo_para_outro_cardio(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_troca')
        _login(client, 'cardio_troca')
        client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'cardio_tipo_{ctx["esteira"]}': ctx['bike'], f'duracao_{ctx["esteira"]}': '25',
        })
        with app.app_context():
            assert _series_do(ctx['user_id'], base_id=ctx['esteira_id']) == []
            assert [s.duracao_segundos for s in _series_do(ctx['user_id'], base_id=ctx['bike_id'])] == [1500]

    def test_combo_nao_aceita_exercicio_de_forca_nem_de_outro_usuario(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_idor')
            outro = _criar_usuario('cardio_idor_outro')
            alheio = ExercicioUsuario(usuario_id=outro.id, nome='Esteira do outro', modo_registro='tempo')
            db.session.add(alheio)
            db.session.commit()
            chave_alheia = f'u_{alheio.id}'
        _login(client, 'cardio_idor')
        for chave_tipo in (ctx['supino_catalogo'], chave_alheia, 'b_999999', 'lixo'):
            client.post('/registrar/registrar-treino', data={
                'treino': str(ctx['treino_id']), 'data': DATA,
                f'carga_{ctx["supino"]}': '40', f'reps_{ctx["supino"]}': '10', f'num_series_{ctx["supino"]}': '1',
                f'cardio_tipo_{ctx["esteira"]}': chave_tipo, f'duracao_{ctx["esteira"]}': '25',
            })
        with app.app_context():
            series = HistoricoTreino.query.join(RegistroTreino).filter(
                RegistroTreino.user_id == ctx['user_id'], HistoricoTreino.duracao_segundos.isnot(None)).count()
            assert series == 0

    def test_cardio_avulso_pelo_mais_cardio(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_avulso')
        _login(client, 'cardio_avulso')
        client.post('/registrar/registrar-treino', data=MultiDict([
            ('treino', str(ctx['treino_id'])), ('data', DATA),
            ('avulso_cardio[]', 'cardio1'), ('cardio_tipo_cardio1', ctx['caminhada']),
            ('duracao_cardio1', '15'), ('intensidade_cardio1', 'moderada'),
            # outra Esteira, além da da ficha
            ('avulso_cardio[]', 'cardio2'), ('cardio_tipo_cardio2', ctx['esteira']), ('duracao_cardio2', '10'),
            (f'duracao_{ctx["esteira"]}', '20'),
            # chaves inválidas são ignoradas
            ('avulso_cardio[]', 'u_1'), ('avulso_cardio[]', 'cardioX'),
        ]))
        with app.app_context():
            assert [(s.duracao_segundos, s.intensidade) for s in _series_do(ctx['user_id'], base_id=ctx['caminhada_id'])] \
                == [(900, 'moderada')]
            assert sorted(s.duracao_segundos for s in _series_do(ctx['user_id'], base_id=ctx['esteira_id'])) == [600, 1200]

    def test_carga_zero_peso_corporal_e_gravada(self, client, app):
        """Antes do cardio, carga 0 (barra fixa, flexão) sumia em silêncio."""
        with app.app_context():
            ctx = _montar('cardio_peso_corporal')
        _login(client, 'cardio_peso_corporal')
        client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'carga_{ctx["supino"]}': '0', f'reps_{ctx["supino"]}': '12', f'num_series_{ctx["supino"]}': '2',
        })
        with app.app_context():
            series = _series_do(ctx['user_id'], usuario_id=ctx['supino_id'])
            assert [(float(s.carga), s.repeticoes) for s in series] == [(0.0, 12), (0.0, 12)]

    def test_tela_reabre_com_o_cardio_salvo_e_historico_nao_quebra(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_reabre')
        _login(client, 'cardio_reabre')
        client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'carga_{ctx["supino"]}': '40', f'reps_{ctx["supino"]}': '10', f'num_series_{ctx["supino"]}': '3',
            f'duracao_{ctx["esteira"]}': '20', f'distancia_{ctx["esteira"]}': '3', f'intensidade_{ctx["esteira"]}': 'forte',
        })
        # mesmo dia (edição) e dia seguinte (histórico "última")
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}').get_data(as_text=True)
        assert 'value="20"' in html and 'value="3"' in html
        assert '<option value="forte" selected>' in html
        html2 = client.get(f'/registrar/registrar-treino?data=2026-01-06&treino={ctx["treino_id"]}')
        assert html2.status_code == 200
        assert 'Última: 20 min · 3 km' in html2.get_data(as_text=True)
        assert 'None' not in html2.get_data(as_text=True).split('data-ultima-carga=')[1][:10]


    def test_reabrir_o_dia_traz_de_volta_o_cardio_fora_da_ficha(self, client, app):
        """Tipo trocado no combo e cardio avulso voltam na tela; senão um novo
        "Salvar" (que substitui a sessão) apagaria esses registros."""
        import json
        import re
        with app.app_context():
            ctx = _montar('cardio_reabre_fora')
        _login(client, 'cardio_reabre_fora')
        client.post('/registrar/registrar-treino', data=MultiDict([
            ('treino', str(ctx['treino_id'])), ('data', DATA),
            (f'cardio_tipo_{ctx["esteira"]}', ctx['bike']), (f'duracao_{ctx["esteira"]}', '25'),
            ('avulso_cardio[]', 'cardio1'), ('cardio_tipo_cardio1', ctx['caminhada']),
            ('duracao_cardio1', '15'), ('distancia_cardio1', '1,5'), ('intensidade_cardio1', 'leve'),
        ]))
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}').get_data(as_text=True)
        assert f'<option value="{ctx["bike"]}" selected>' in html
        assert f'name="duracao_{ctx["esteira"]}"' in html and 'value="25"' in html
        salvos = json.loads(re.search(r'id="cardiosSalvosJson">(.*?)</script>', html, re.S).group(1))
        assert salvos == [{'tipo': ctx['caminhada'], 'nome': 'Caminhada', 'duracao_min': 15.0,
                           'distancia_km': 1.5, 'intensidade': 'leve'}]


    def test_mais_cardio_vem_com_padrao_e_depois_com_o_ultimo_cardio(self, client, app):
        """O "+ Cardio" cria a linha já preenchida: Esteira 20 min / 2,5 km /
        moderada para quem nunca fez cardio; depois, o último cardio feito."""
        import json
        import re
        with app.app_context():
            ctx = _montar('cardio_inicial')
            assert cardio.ultimo_cardio(ctx['user_id']) is None
        _login(client, 'cardio_inicial')

        def inicial(data):
            html = client.get(f'/registrar/registrar-treino?data={data}&treino={ctx["treino_id"]}').get_data(as_text=True)
            return json.loads(re.search(r'id="cardioInicialJson">(.*?)</script>', html, re.S).group(1))

        padrao = inicial(DATA)
        assert (padrao['nome'], padrao['duracao_min'], padrao['distancia_km'], padrao['intensidade']) \
            == ('Esteira', 20, 2.5, 'moderada')
        assert padrao['tipo'] == ctx['esteira']

        client.post('/registrar/registrar-treino', data=MultiDict([
            ('treino', str(ctx['treino_id'])), ('data', DATA),
            ('avulso_cardio[]', 'cardio1'), ('cardio_tipo_cardio1', ctx['bike']),
            ('duracao_cardio1', '35'), ('distancia_cardio1', '12'), ('intensidade_cardio1', 'forte'),
        ]))
        assert inicial('2026-01-07') == {'tipo': ctx['bike'], 'nome': 'Bicicleta ergométrica',
                                         'duracao_min': 35.0, 'distancia_km': 12.0, 'intensidade': 'forte'}


# ---------------------------------------------------------------- calendário

class TestCalendarioCardio:
    def test_dados_edicao_e_detalhe_do_dia(self, client, app):
        with app.app_context():
            ctx = _montar('cardio_cal')
        _login(client, 'cardio_cal')
        client.post('/registrar/registrar-treino', data=MultiDict([
            ('treino', str(ctx['treino_id'])), ('data', DATA),
            (f'carga_{ctx["supino"]}', '40'), (f'reps_{ctx["supino"]}', '10'), (f'num_series_{ctx["supino"]}', '1'),
            (f'duracao_{ctx["esteira"]}', '20'),
            ('avulso_cardio[]', 'cardio1'), ('cardio_tipo_cardio1', ctx['bike']), ('duracao_cardio1', '15'),
        ]))
        resp = client.get(f'/calendar/api/evento/dados-edicao?data={DATA}&treino={ctx["treino_id"]}')
        assert resp.status_code == 200
        dados = resp.get_json()
        texto = str(dados)
        assert "'cardio': True" in texto
        assert "'duracao_min': 20" in texto and "'duracao_min': 15" in texto

        eventos = client.get('/calendar/api/eventos').get_json()
        assert eventos and eventos[0]['extendedProps']['volume'] == 400.0  # cardio fora do volume


# ---------------------------------------------------------------- progresso

class TestProgressoCardio:
    def test_resumo_da_semana(self, app):
        with app.app_context():
            ctx = _montar('cardio_semana_svc')
            assert cardio.resumo_cardio_semana(ctx['user_id'], hoje=date(2026, 1, 7)) is None
            for dia, base_id, seg, km in ((5, ctx['esteira_id'], 1200, 3), (7, ctx['bike_id'], 1500, 8),
                                          (2, ctx['bike_id'], 600, None)):  # dia 2 = semana anterior
                r = RegistroTreino(treino_versao_id=ctx['treino_id'], versao_id=ctx['versao_id'], periodo='p', semana=1,
                                   exercicio_base_id=base_id, data_registro=datetime(2026, 1, dia), user_id=ctx['user_id'])
                db.session.add(r)
                db.session.flush()
                db.session.add(HistoricoTreino(registro_id=r.id, duracao_segundos=seg, distancia_km=km))
            db.session.commit()

            resumo = cardio.resumo_cardio_semana(ctx['user_id'], hoje=date(2026, 1, 7))
            assert (resumo['minutos'], resumo['km'], resumo['sessoes']) == (45, 11.0, 2)
            assert [d['minutos'] for d in resumo['dias']] == [20, 0, 25, 0, 0, 0, 0]
            assert resumo['dias'][2]['hoje'] and resumo['dias'][2]['pct'] == 100
            assert [r['nome'] for r in resumo['recentes']] == ['Bicicleta ergométrica', 'Esteira', 'Bicicleta ergométrica']
            assert resumo['recentes'][0]['resumo'] == '25 min · 8 km'

    def test_cartao_aparece_so_pra_quem_tem_cardio(self, client, app):
        from services.billing_service import BillingService
        from models import User
        with app.app_context():
            ctx = _montar('cardio_progresso')
            BillingService.iniciar_trial(User.query.get(ctx['user_id']))  # tela premium
            db.session.commit()
        _login(client, 'cardio_progresso')
        resp = client.get('/aluno/estatisticas')
        assert resp.status_code == 200
        assert 'id="cardioSemana"' not in resp.get_data(as_text=True)

        client.post('/registrar/registrar-treino', data={
            'treino': str(ctx['treino_id']), 'data': DATA,
            f'duracao_{ctx["esteira"]}': '25', f'distancia_{ctx["esteira"]}': '8',
        })
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        assert 'id="cardioSemana"' in html
        assert 'Sessões recentes' in html and '25 min · 8 km' in html and '05/01' in html


# ---------------------------------------------------------------- exercício próprio

class TestExercicioProprioComoCardio:
    def test_criar_e_editar_com_modo_tempo(self, client, app):
        with app.app_context():
            _criar_usuario('cardio_ex_proprio')
        _login(client, 'cardio_ex_proprio')
        assert 'name="modo_registro"' in client.get('/aluno/exercicio/novo').get_data(as_text=True)
        client.post('/aluno/exercicio/novo', data={'nome': 'Corda', 'musculo': 'Cardio', 'modo_registro': 'tempo'})
        client.post('/aluno/exercicio/novo', data={'nome': 'Rosca', 'musculo': 'Bíceps', 'modo_registro': 'xx'})
        with app.app_context():
            corda = ExercicioUsuario.query.filter_by(nome='Corda').one()
            assert corda.modo_registro == 'tempo'
            assert ExercicioUsuario.query.filter_by(nome='Rosca').one().modo_registro == 'carga'
            corda_id = corda.id
        client.post(f'/aluno/exercicio/{corda_id}', data={'nome': 'Corda', 'musculo': 'Cardio', 'modo_registro': 'carga'})
        with app.app_context():
            assert ExercicioUsuario.query.get(corda_id).modo_registro == 'carga'
