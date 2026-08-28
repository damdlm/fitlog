"""
Testes de integração da tela "Minhas Versões" (routes/aluno/versao.py):
listar histórico, ver/editar uma versão específica -- inclusive já
finalizada -- e clonar/excluir versões.

Diferente de tests/integration/test_cadastrar_treinos.py (que só cobre a
versão ATIVA), aqui o foco é justamente confirmar que editar/adicionar/
salvar/remover treino continuam funcionando numa versão já finalizada,
e as regras novas de clonar_versao/excluir_versao.
"""

import pytest
from datetime import date, timedelta

from models import db, User, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioUsuario


def _criar_aluno(username='aluno1', email='aluno1@teste.com'):
    user = User(username=username, email=email, tipo_usuario='aluno')
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username, password='123456'):
    return client.post('/auth/login', data={'username': username, 'password': password})


@pytest.fixture
def aluno(app):
    with app.app_context():
        user = _criar_aluno()
        return user.id


@pytest.fixture
def outro_aluno(app):
    with app.app_context():
        user = _criar_aluno(username='aluno2', email='aluno2@teste.com')
        return user.id


@pytest.fixture
def aluno_client(client, app, aluno):
    with app.app_context():
        user = db.session.get(User, aluno)
        _login(client, user.username)
    return client


def _criar_versao_finalizada(user_id, descricao='v1', numero_versao=1, com_treino=True):
    """Cria diretamente no banco uma versão já finalizada, com um treino
    e um exercício -- para testar o histórico sem depender do fluxo de
    criação (que só cria versões ativas)."""
    versao = VersaoGlobal(
        numero_versao=numero_versao, descricao=descricao, divisao='LIVRE',
        data_inicio=date.today() - timedelta(days=30),
        data_fim=date.today() - timedelta(days=1),
        user_id=user_id,
    )
    db.session.add(versao)
    db.session.commit()
    if com_treino:
        ex = ExercicioUsuario(usuario_id=user_id, nome='Supino')
        db.session.add(ex)
        db.session.commit()
        tv = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A', ordem=0)
        db.session.add(tv)
        db.session.commit()
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0))
        db.session.commit()
    return versao.id


class TestListarVersoes:
    def test_lista_vazia_quando_nao_ha_versoes(self, aluno_client):
        resp = aluno_client.get('/aluno/versoes')
        assert resp.status_code == 200
        assert 'Nenhuma versão ainda' in resp.get_data(as_text=True)

    def test_lista_versao_ativa_e_finalizada(self, aluno_client, app, aluno):
        with app.app_context():
            _criar_versao_finalizada(aluno, descricao='Antiga', numero_versao=1)
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Atual'})

        resp = aluno_client.get('/aluno/versoes')
        html = resp.get_data(as_text=True)
        assert 'Antiga' in html
        assert 'Atual' in html
        assert 'Finalizada' in html
        assert 'Ativa' in html

    def test_nao_mostra_versao_de_outro_usuario(self, aluno_client, app, outro_aluno):
        with app.app_context():
            _criar_versao_finalizada(outro_aluno, descricao='Não é minha')
        resp = aluno_client.get('/aluno/versoes')
        assert 'Não é minha' not in resp.get_data(as_text=True)


class TestVerVersao:
    def test_idor_nao_mostra_versao_de_outro_usuario(self, aluno_client, app, outro_aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(outro_aluno)
        resp = aluno_client.get(f'/aluno/versao/{versao_id}', follow_redirects=True)
        assert 'Versão não encontrada' in resp.get_data(as_text=True)

    def test_versao_inexistente_redireciona_com_flash(self, aluno_client):
        resp = aluno_client.get('/aluno/versao/99999', follow_redirects=True)
        assert 'Versão não encontrada' in resp.get_data(as_text=True)

    def test_mostra_treinos_e_exercicios_de_versao_finalizada(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)
        resp = aluno_client.get(f'/aluno/versao/{versao_id}')
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Treino A' in html
        assert 'Supino' in html


class TestEditarVersaoFinalizada:
    """A principal diferença desta tela pra "Cadastrar Treinos": aqui
    editar uma versão finalizada é permitido."""

    def test_edita_descricao_de_versao_finalizada(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno, descricao='Original')

        resp = aluno_client.post(
            f'/aluno/versao/{versao_id}/editar', data={'descricao': 'Corrigida'},
            follow_redirects=True
        )
        assert 'Versão atualizada' in resp.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id).descricao == 'Corrigida'

    def test_adiciona_treino_em_versao_finalizada(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno, com_treino=False)

        resp = aluno_client.post(
            f'/aluno/versao/{versao_id}/treino',
            data={'nome_treino': 'Treino B', 'descricao_treino': ''},
            follow_redirects=True
        )
        assert 'Treino adicionado' in resp.get_data(as_text=True)
        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            assert tv is not None
            assert tv.codigo == 'A'  # primeira letra, mesmo em versão finalizada

    def test_edita_exercicios_de_treino_em_versao_finalizada(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id
            novo_ex = ExercicioUsuario(usuario_id=aluno, nome='Rosca direta')
            db.session.add(novo_ex)
            db.session.commit()
            novo_ex_id = novo_ex.id

        resp = aluno_client.post(
            f'/aluno/versao/{versao_id}/treino/{tv_id}',
            data={
                'nome_treino': 'Treino A renomeado',
                'descricao_treino': '',
                'exercicios[]': [f'u_{novo_ex_id}'],
            },
            follow_redirects=True
        )
        assert 'Treino salvo' in resp.get_data(as_text=True)
        with app.app_context():
            tv = db.session.get(TreinoVersao, tv_id)
            assert tv.nome_treino == 'Treino A renomeado'
            assert {ve.exercicio_usuario_id for ve in tv.exercicios} == {novo_ex_id}

    def test_idor_nao_permite_editar_treino_de_outro_usuario(self, aluno_client, app, outro_aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(outro_aluno)
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id

        aluno_client.post(
            f'/aluno/versao/{versao_id}/treino/{tv_id}',
            data={'nome_treino': 'Invadido', 'descricao_treino': ''}
        )
        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id).nome_treino == 'Treino A'

    def test_nao_remove_treino_com_registros_mesmo_finalizada(self, aluno_client, app, aluno):
        from models import RegistroTreino, ExercicioSistema
        from datetime import datetime, timezone

        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            tv_id = tv.id
            ex = ExercicioSistema(id_original='reg-hist-1', nome='Agachamento', grupo_muscular='Pernas')
            db.session.add(ex)
            db.session.commit()
            db.session.add(RegistroTreino(
                treino_versao_id=tv_id, versao_id=versao_id, periodo='Agosto/2026', semana=1,
                exercicio_base_id=ex.id, data_registro=datetime.now(timezone.utc), user_id=aluno,
            ))
            db.session.commit()

        resp = aluno_client.post(
            f'/aluno/versao/{versao_id}/treino/{tv_id}/remover', follow_redirects=True
        )
        assert 'não pode ser removido' in resp.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is not None


class TestClonarVersao:
    def test_clona_treinos_e_exercicios(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno, descricao='Original')

        resp = aluno_client.post(f'/aluno/versao/{versao_id}/clonar', follow_redirects=True)
        assert 'clonada' in resp.get_data(as_text=True)

        with app.app_context():
            versoes = VersaoGlobal.query.filter_by(user_id=aluno).order_by(VersaoGlobal.id).all()
            assert len(versoes) == 2
            clone = versoes[-1]
            assert clone.data_fim is None
            assert clone.descricao == 'Original (cópia)'
            treinos_clone = TreinoVersao.query.filter_by(versao_id=clone.id).all()
            assert len(treinos_clone) == 1
            assert treinos_clone[0].nome_treino == 'Treino A'
            assert len(treinos_clone[0].exercicios) == 1

    def test_bloqueia_clonar_se_ja_existe_versao_ativa(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Já ativa'})

        resp = aluno_client.post(f'/aluno/versao/{versao_id}/clonar', follow_redirects=True)
        assert 'Já existe uma versão ativa' in resp.get_data(as_text=True)
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 2

    def test_idor_nao_permite_clonar_versao_de_outro_usuario(self, aluno_client, app, outro_aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(outro_aluno)
        aluno_client.post(f'/aluno/versao/{versao_id}/clonar')
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=outro_aluno).count() == 1


class TestExcluirVersao:
    def test_exclui_versao_finalizada_sem_historico(self, aluno_client, app, aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)

        resp = aluno_client.post(f'/aluno/versao/{versao_id}/excluir', follow_redirects=True)
        assert 'excluída' in resp.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is None

    def test_bloqueia_excluir_versao_ativa(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Ativa'})
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id

        resp = aluno_client.post(f'/aluno/versao/{versao_id}/excluir', follow_redirects=True)
        assert 'Finalize-a primeiro' in resp.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_bloqueia_excluir_versao_com_registro_de_treino(self, aluno_client, app, aluno):
        from models import RegistroTreino, ExercicioSistema
        from datetime import datetime, timezone

        with app.app_context():
            versao_id = _criar_versao_finalizada(aluno)
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id
            ex = ExercicioSistema(id_original='reg-hist-2', nome='Levantamento terra', grupo_muscular='Costas')
            db.session.add(ex)
            db.session.commit()
            db.session.add(RegistroTreino(
                treino_versao_id=tv_id, versao_id=versao_id, periodo='Agosto/2026', semana=1,
                exercicio_base_id=ex.id, data_registro=datetime.now(timezone.utc), user_id=aluno,
            ))
            db.session.commit()

        resp = aluno_client.post(f'/aluno/versao/{versao_id}/excluir', follow_redirects=True)
        assert 'não pode ser excluída' in resp.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_idor_nao_permite_excluir_versao_de_outro_usuario(self, aluno_client, app, outro_aluno):
        with app.app_context():
            versao_id = _criar_versao_finalizada(outro_aluno)
        aluno_client.post(f'/aluno/versao/{versao_id}/excluir')
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None


class TestAcessoNaoAutenticado:
    def test_get_versoes_sem_login_redireciona(self, client):
        resp = client.get('/aluno/versoes')
        assert resp.status_code == 302

    def test_get_ver_versao_sem_login_redireciona(self, client):
        resp = client.get('/aluno/versao/1')
        assert resp.status_code == 302

    def test_post_excluir_sem_login_redireciona(self, client):
        resp = client.post('/aluno/versao/1/excluir')
        assert resp.status_code == 302
