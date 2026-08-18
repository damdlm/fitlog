"""
Testes para a UI de "iniciar treino" na tela de registrar treino:
- o botão "Iniciar treino" (caixa .cronometro-actions) some da tela,
  substituído pelo ícone de play clicável do card "Tudo pronto!";
- o texto do card foi atualizado pra combinar com essa mudança;
- o overlay de animação "scanner" (carregando exercícios) está presente
  e é usado ao trocar de treino/data (submeterComScanner).
"""
from datetime import date

from models import db, User, Treino, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioUsuario, Musculo


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _montar_treino_com_exercicio(user):
    musculo = Musculo(nome='peito', nome_exibicao='Peito')
    db.session.add(musculo)
    db.session.flush()

    exercicio = ExercicioUsuario(usuario_id=user.id, nome='Supino Reto', musculo_id=musculo.id)
    db.session.add(exercicio)

    treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='Treino A')
    db.session.add(treino)

    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date(2026, 1, 1), user_id=user.id)
    db.session.add(versao)
    db.session.flush()

    treino_versao = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino='Treino A')
    db.session.add(treino_versao)
    db.session.flush()

    ve = VersaoExercicio(treino_versao_id=treino_versao.id, exercicio_usuario_id=exercicio.id, ordem=0)
    db.session.add(ve)
    db.session.commit()

    return treino


class TestBotaoIniciarTreinoSubstituidoPeloPlay:
    def test_icone_de_play_clicavel_presente(self, client, app):
        with app.app_context():
            user = _criar_usuario('ui_play_1')
            treino = _montar_treino_com_exercicio(user)
            treino_id = treino.id
        _login(client, 'ui_play_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'id="playIniciarTreino"' in html
        assert 'role="button"' in html

    def test_caixa_de_botoes_iniciar_zerar_fica_escondida(self, client, app):
        with app.app_context():
            user = _criar_usuario('ui_play_2')
            treino = _montar_treino_com_exercicio(user)
            treino_id = treino.id
        _login(client, 'ui_play_2')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        # O botão continua existindo no DOM (reaproveitado pela lógica de
        # cronômetro/wake lock/modo treino), só não aparece mais visualmente.
        assert 'id="cronoTreinoBtnIniciar"' in html
        assert 'cronometro-actions mt-0 mb-4 d-none" id="cronoTreinoBox"' in html

    def test_texto_do_card_nao_referencia_mais_o_botao_removido(self, client, app):
        with app.app_context():
            user = _criar_usuario('ui_play_3')
            treino = _montar_treino_com_exercicio(user)
            treino_id = treino.id
        _login(client, 'ui_play_3')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'Clique em <strong>Iniciar treino</strong>' not in html
        assert 'play acima' in html


class TestAnimacaoDeCarregamentoAoTrocarTreino:
    def test_overlay_de_scanner_presente_na_pagina(self, client, app):
        with app.app_context():
            user = _criar_usuario('ui_scan_1')
            treino = _montar_treino_com_exercicio(user)
            treino_id = treino.id
        _login(client, 'ui_scan_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'id="treinoScanOverlay"' in html
        assert 'fl-scan-line' in html
        # Reaproveita a película/posicionamento globais já usados na
        # transição entre páginas (page-transition.css).
        assert 'class="fl-loader-overlay"' in html

    def test_troca_de_treino_dispara_o_scanner_antes_do_submit(self, client, app):
        with app.app_context():
            user = _criar_usuario('ui_scan_2')
            treino = _montar_treino_com_exercicio(user)
            treino_id = treino.id
        _login(client, 'ui_scan_2')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'function submeterComScanner' in html
        assert "overlay.classList.add('fl-loader-visible')" in html