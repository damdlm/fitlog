"""
Testes para o popover de descrição do exercício na tela de registrar
treino: o badge de músculo fixo foi removido; ao clicar na região do
nome + valores do último treino, um popover mostra o nome completo do
exercício e os músculos trabalhados (principal + secundários) -- não
mais a descrição do exercício (data-descricao foi removido do HTML;
o JS lê o nome a partir do data-full-nome já usado pelo truncamento).
"""
from datetime import date

from models import (
    db, User, Treino, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, ExercicioSistema, Musculo,
)


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _montar_treino(user, ex_usuario=None, ex_base=None):
    treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='Treino A')
    db.session.add(treino)

    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date(2026, 1, 1), user_id=user.id)
    db.session.add(versao)
    db.session.flush()

    treino_versao = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino='Treino A')
    db.session.add(treino_versao)
    db.session.flush()

    ordem = 0
    if ex_usuario:
        db.session.add(VersaoExercicio(treino_versao_id=treino_versao.id,
                                        exercicio_usuario_id=ex_usuario.id, ordem=ordem))
        ordem += 1
    if ex_base:
        db.session.add(VersaoExercicio(treino_versao_id=treino_versao.id,
                                        exercicio_base_id=ex_base.id, ordem=ordem))
    db.session.commit()
    return treino


class TestBadgeDeMusculoRemovido:
    def test_badge_fixo_de_musculo_nao_aparece_mais(self, client, app):
        with app.app_context():
            user = _criar_usuario('tt_badge_1')
            musculo = Musculo(nome='peito', nome_exibicao='Peito')
            db.session.add(musculo)
            db.session.flush()
            ex = ExercicioUsuario(usuario_id=user.id, nome='Supino', musculo_id=musculo.id)
            db.session.add(ex)
            db.session.flush()
            treino = _montar_treino(user, ex_usuario=ex)
            treino_id = treino.id
        _login(client, 'tt_badge_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        # O ícone de link + nome do músculo que ficava sempre visível
        # não deve mais estar renderizado no corpo da página.
        assert 'bi-link-45deg' not in html
        assert '<span class="dash-registro-meta">' not in html


class TestPopoverDescricaoExercicioUsuario:
    def test_dados_do_exercicio_de_usuario_no_gatilho(self, client, app):
        with app.app_context():
            user = _criar_usuario('tt_pop_1')
            musculo = Musculo(nome='peito', nome_exibicao='Peito')
            db.session.add(musculo)
            db.session.flush()
            ex = ExercicioUsuario(usuario_id=user.id, nome='Supino Reto Livre', musculo_id=musculo.id,
                                   descricao='Deite no banco e empurre a barra.')
            db.session.add(ex)
            db.session.flush()
            treino = _montar_treino(user, ex_usuario=ex)
            treino_id = treino.id
        _login(client, 'tt_pop_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'exercicio-info-trigger' in html
        # O popover não mostra mais a descrição do exercício (nem o
        # atributo data-descricao é renderizado) -- só o nome + músculos.
        assert 'data-descricao=' not in html
        assert 'data-full-nome="Supino Reto Livre"' in html
        assert 'data-musculo-principal="Peito"' in html
        # Exercício de usuário não tem músculos secundários cadastrados.
        assert 'data-musculos-secundarios=""' in html


class TestPopoverDescricaoExercicioCatalogo:
    def test_dados_do_exercicio_de_catalogo_no_gatilho(self, client, app):
        with app.app_context():
            user = _criar_usuario('tt_pop_2')
            ex_base = ExercicioSistema(
                id_original='X001', nome='Remada Curvada',
                grupo_muscular='Costas',
                instrucao_pt='Incline o tronco e puxe a barra até o abdômen.',
                musculos_secundarios=['Bíceps', 'Trapézio'],
            )
            db.session.add(ex_base)
            db.session.flush()
            treino = _montar_treino(user, ex_base=ex_base)
            treino_id = treino.id
        _login(client, 'tt_pop_2')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'data-descricao=' not in html
        assert 'data-full-nome="Remada Curvada"' in html
        assert 'data-musculo-principal="Costas"' in html
        assert 'data-musculos-secundarios="Bíceps, Trapézio"' in html


class TestJsDeInicializacaoPresente:
    def test_funcao_de_inicializacao_do_popover_presente(self, client, app):
        with app.app_context():
            user = _criar_usuario('tt_pop_3')
            ex_base = ExercicioSistema(id_original='X002', nome='Agachamento', grupo_muscular='Pernas')
            db.session.add(ex_base)
            db.session.flush()
            treino = _montar_treino(user, ex_base=ex_base)
            treino_id = treino.id
        _login(client, 'tt_pop_3')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert 'function inicializarPopoverDescricaoExercicio' in html
        assert 'inicializarPopoverDescricaoExercicio();' in html