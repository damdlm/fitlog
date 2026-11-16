"""Rota /registrar/linha-avulsa: devolve o card de UM exercício avulso para
o "+ Exercício" inserir na lista sem recarregar a página."""
from werkzeug.datastructures import MultiDict

from models import db, ExercicioUsuario
from tests.integration.test_routes.test_cardio import DATA, _criar_usuario, _login, _montar


def _url(ctx, chave, data=DATA, treino=None):
    return f'/registrar/linha-avulsa?treino={treino or ctx["treino_id"]}&data={data}&chave={chave}'


class TestLinhaAvulsa:
    def test_devolve_so_o_card_do_exercicio(self, client, app):
        with app.app_context():
            ctx = _montar('linha_avulsa_ok')
            rosca = ExercicioUsuario(usuario_id=ctx['user_id'], nome='Rosca martelo')
            db.session.add(rosca)
            db.session.commit()
            chave = f'u_{rosca.id}'
        _login(client, 'linha_avulsa_ok')
        resp = client.get(_url(ctx, chave))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert html.count('class="exercise-row-wrap"') == 1
        assert f'data-exercicio-id="{chave}"' in html
        assert 'Rosca martelo' in html and 'Avulso' in html
        assert f'name="carga_{chave}"' in html
        assert '<html' not in html and 'registroForm' not in html  # só o card

    def test_card_de_cardio_e_valores_ja_salvos_no_dia(self, client, app):
        with app.app_context():
            ctx = _montar('linha_avulsa_cardio')
        _login(client, 'linha_avulsa_cardio')
        client.post('/registrar/registrar-treino', data=MultiDict([
            ('treino', str(ctx['treino_id'])), ('data', DATA),
            ('avulso_exercicios[]', ctx['caminhada']), (f'duracao_{ctx["caminhada"]}', '18'),
        ]))
        html = client.get(_url(ctx, ctx['caminhada'])).get_data(as_text=True)
        assert 'exercise-row--cardio' in html and f'name="duracao_{ctx["caminhada"]}"' in html
        assert 'value="18"' in html

    def test_recusa_exercicio_de_outro_usuario_treino_alheio_e_data_invalida(self, client, app):
        with app.app_context():
            ctx = _montar('linha_avulsa_dono')
            outro = _criar_usuario('linha_avulsa_outro')
            alheio = ExercicioUsuario(usuario_id=outro.id, nome='Do outro')
            db.session.add(alheio)
            db.session.commit()
            chave_alheia = f'u_{alheio.id}'
        _login(client, 'linha_avulsa_dono')
        assert client.get(_url(ctx, chave_alheia)).status_code == 404
        assert client.get(_url(ctx, 'lixo')).status_code == 404
        assert client.get(_url(ctx, ctx['caminhada'], treino='999999')).status_code == 404
        assert client.get(_url(ctx, ctx['caminhada'], data='2026-99-99')).status_code == 400

    def test_exige_login(self, client, app):
        with app.app_context():
            ctx = _montar('linha_avulsa_anon')
        resp = client.get(_url(ctx, ctx['caminhada']))
        assert resp.status_code in (302, 401)

    def test_pagina_continua_trazendo_o_avulso_pela_url(self, client, app):
        """A chave segue indo para a URL (replaceState): atualizar a página
        mantém o card, pelo caminho antigo do ?avulso=."""
        with app.app_context():
            ctx = _montar('linha_avulsa_url')
        _login(client, 'linha_avulsa_url')
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}'
                          f'&avulso={ctx["caminhada"]}').get_data(as_text=True)
        assert f'data-exercicio-id="{ctx["caminhada"]}"' in html
        assert 'class="avulso-marker"' in html or 'avulso_exercicios[]' in html