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


    def test_rascunho_guarda_e_recria_os_avulsos(self, client, app):
        """Reaberto pelo ícone, o app volta para /registrar-treino sem o
        ?avulso= e os avulsos sumiam (com o que já tinha sido digitado):
        o rascunho guarda as chaves e recria os cards antes de restaurar
        os valores, sem gravar por cima enquanto recria."""
        with app.app_context():
            ctx = _montar('linha_avulsa_rascunho')
        _login(client, 'linha_avulsa_rascunho')
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}').get_data(as_text=True)
        html = html.replace('\r\n', '\n')
        assert 'window.FitLogInserirLinhaAvulsa = inserirLinhaAvulsa;' in html
        assert "exerciciosAvulsos: Array.from(document.querySelectorAll('input[name=\"avulso_exercicios[]\"]'))" in html
        restaurar = html[html.index('    async function tentarRestaurar() {'):html.index('    // Se o treino terminar (salvo com sucesso)')]
        assert restaurar.index('await recriarAvulsos(estado.exerciciosAvulsos)') < restaurar.index('restaurarCampos(estado.campos)')
        assert 'restaurando = true;' in restaurar and 'if (!s || restaurando) return;' in html
        # o seletor do "+ Exercício" usa a mesma função
        assert 'const row = await inserirLinhaAvulsa(chave);' in html

    def test_video_da_demonstracao_pausa_o_video_invisivel(self, client, app):
        """O <video> invisível que mantém a tela acesa (sem Wake Lock nativo)
        e o MP4 da demonstração tocando juntos congelavam a página no iPhone."""
        with app.app_context():
            ctx = _montar('linha_avulsa_wake')
        _login(client, 'linha_avulsa_wake')
        html = client.get(f'/registrar/registrar-treino?data={DATA}&treino={ctx["treino_id"]}').get_data(as_text=True)
        html = html.replace('\r\n', '\n')
        assert "document.addEventListener('fitlog:midia-video', function (ev) {" in html
        fallback = html[html.index('    function iniciarFallbackVideo() {'):][:600]
        assert 'if (suspensoPorMidia) {' in fallback
        from pathlib import Path
        js = (Path(app.root_path) / 'static' / 'js' / 'modules' / 'exercicio-imagens.js').read_text(encoding='utf-8')
        assert "new CustomEvent('fitlog:midia-video', { detail: { aberto: aberto } })" in js
        # o MP4 só carrega depois que o modal abriu, num <video> novo a cada vez
        assert "modalEl.addEventListener('shown.bs.modal', aoMostrar, { once: true });" in js
        assert 'if (ehVideo) carregarVideo(els, url);' in js
        assert 'const v = els.video.cloneNode(false);' in js