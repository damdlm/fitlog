"""
Testes de integração da tela "Cadastrar Treinos" (fluxo unificado que
substitui as antigas telas de "Nova Versão" + "Adicionar Treino à
Versão"): services/versao_service.py (create_livre, adicionar_treino_livre,
salvar_treino_livre, remover_treino_livre, finalizar_livre) e as rotas
em routes/aluno/cadastro_treinos.py.

Foco em regras de consistência e segurança (IDOR, posse, limites),
não em cobertura visual/HTML.
"""

import pytest
from datetime import date, timedelta

from models import db, User, VersaoGlobal, TreinoVersao, ExercicioUsuario


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


class TestCriarVersaoLivre:
    def test_get_sem_versao_ativa_mostra_estado_vazio(self, aluno_client):
        resp = aluno_client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 200
        assert 'Comece uma nova vers' in resp.get_data(as_text=True)

    def test_criar_versao_define_data_inicio_hoje_sem_data_fim(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Foco em hipertrofia'})
        with app.app_context():
            versao = VersaoGlobal.query.filter_by(user_id=aluno).first()
            assert versao is not None
            assert versao.descricao == 'Foco em hipertrofia'
            assert versao.data_inicio == date.today()
            assert versao.data_fim is None
            assert versao.divisao == 'LIVRE'
            assert versao.numero_versao == 1

    def test_nao_aceita_data_inicio_do_cliente(self, aluno_client, app, aluno):
        """O form novo nem tem campo de data -- mas mesmo que alguém forje
        um POST com data_inicio, o service ignora e usa a data do servidor."""
        data_forjada = (date.today() + timedelta(days=365)).isoformat()
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={
            'descricao': 'Tentando forjar data',
            'data_inicio': data_forjada,
        })
        with app.app_context():
            versao = VersaoGlobal.query.filter_by(user_id=aluno).first()
            assert versao.data_inicio == date.today()

    def test_descricao_vazia_e_rejeitada(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': '   '})
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_bloqueia_segunda_versao_ativa(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v1'})
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v2'})
        with app.app_context():
            versoes = VersaoGlobal.query.filter_by(user_id=aluno).all()
            assert len(versoes) == 1
            assert versoes[0].descricao == 'v1'


class TestAdicionarTreinoLivre:
    def _criar_versao(self, client):
        client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Minha versão'})

    def test_primeiro_treino_recebe_codigo_a(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao = VersaoGlobal.query.filter_by(user_id=aluno).first()
            versao_id = versao.id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': 'Peito e Tríceps', 'descricao_treino': ''
        })
        with app.app_context():
            tv = TreinoVersao.query.filter_by(versao_id=versao_id).first()
            assert tv is not None
            assert tv.nome_treino == 'Peito e Tríceps'
            assert tv.codigo == 'A'

    def test_codigos_sequenciais_para_multiplos_treinos(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        for nome in ['Treino 1', 'Treino 2', 'Treino 3']:
            aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
                'nome_treino': nome, 'descricao_treino': ''
            })
        with app.app_context():
            codigos = sorted(
                tv.codigo for tv in TreinoVersao.query.filter_by(versao_id=versao_id).all()
            )
            assert codigos == ['A', 'B', 'C']

    def test_respeita_limite_maximo_de_treinos(self, aluno_client, app, aluno):
        from services.versao_service import VersaoService
        self._criar_versao(aluno_client)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        for i in range(VersaoService.MAX_TREINOS_POR_VERSAO + 2):
            aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
                'nome_treino': f'Treino {i}', 'descricao_treino': ''
            })
        with app.app_context():
            total = TreinoVersao.query.filter_by(versao_id=versao_id).count()
            assert total == VersaoService.MAX_TREINOS_POR_VERSAO

    def test_nome_vazio_e_rejeitado(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': '   ', 'descricao_treino': ''
        })
        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_id).count() == 0

    def test_idor_nao_permite_adicionar_treino_em_versao_de_outro_usuario(
        self, aluno_client, app, aluno, outro_aluno
    ):
        with app.app_context():
            versao_outro = VersaoGlobal(
                numero_versao=1, descricao='Versão do outro usuário', divisao='LIVRE',
                data_inicio=date.today(), user_id=outro_aluno
            )
            db.session.add(versao_outro)
            db.session.commit()
            versao_outro_id = versao_outro.id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_outro_id}/treino', data={
            'nome_treino': 'Invasão', 'descricao_treino': ''
        })
        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_outro_id).count() == 0

    def test_nao_permite_adicionar_treino_em_versao_finalizada(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao = VersaoGlobal.query.filter_by(user_id=aluno).first()
            versao.data_fim = date.today()
            db.session.commit()
            versao_id = versao.id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': 'Depois de arquivada', 'descricao_treino': ''
        })
        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_id).count() == 0


class TestSalvarExerciciosEIdor:
    def _preparar_versao_com_treino(self, client, app, user_id):
        client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v'})
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=user_id).first().id
        client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': 'Treino A', 'descricao_treino': ''
        })
        with app.app_context():
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id
        return versao_id, tv_id

    def test_apenas_exercicios_do_proprio_usuario_sao_salvos(
        self, aluno_client, app, aluno, outro_aluno
    ):
        with app.app_context():
            ex_proprio = ExercicioUsuario(usuario_id=aluno, nome='Supino')
            ex_de_outro = ExercicioUsuario(usuario_id=outro_aluno, nome='Exercício alheio')
            db.session.add_all([ex_proprio, ex_de_outro])
            db.session.commit()
            ex_proprio_id, ex_de_outro_id = ex_proprio.id, ex_de_outro.id

        versao_id, tv_id = self._preparar_versao_com_treino(aluno_client, app, aluno)

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino/{tv_id}', data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{ex_proprio_id}', f'u_{ex_de_outro_id}'],
        })

        with app.app_context():
            tv = db.session.get(TreinoVersao, tv_id)
            ids_salvos = {ve.exercicio_usuario_id for ve in tv.exercicios}
            assert ids_salvos == {ex_proprio_id}

    def test_idor_nao_permite_salvar_treino_de_outra_versao(
        self, aluno_client, app, aluno, outro_aluno
    ):
        with app.app_context():
            versao_outro = VersaoGlobal(
                numero_versao=1, descricao='Do outro', divisao='LIVRE',
                data_inicio=date.today(), user_id=outro_aluno
            )
            db.session.add(versao_outro)
            db.session.commit()
            tv_outro = TreinoVersao(versao_id=versao_outro.id, codigo='A', nome_treino='X')
            db.session.add(tv_outro)
            db.session.commit()
            versao_outro_id, tv_outro_id = versao_outro.id, tv_outro.id

        resp = aluno_client.post(
            f'/aluno/cadastrar-treinos/{versao_outro_id}/treino/{tv_outro_id}',
            data={'nome_treino': 'Invadido', 'descricao_treino': ''}
        )
        assert resp.status_code in (302, 200)
        with app.app_context():
            tv = db.session.get(TreinoVersao, tv_outro_id)
            assert tv.nome_treino == 'X'  # não foi alterado


class TestEditarVersaoLivre:
    def _criar_versao(self, client):
        client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Original'})

    def test_edita_descricao_com_sucesso(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/editar', data={
            'descricao': 'Foco em hipertrofia - Setembro'
        })

        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.descricao == 'Foco em hipertrofia - Setembro'

    def test_descricao_vazia_e_rejeitada(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/editar', data={'descricao': '   '})

        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.descricao == 'Original'

    def test_idor_nao_permite_editar_versao_de_outro_usuario(
        self, aluno_client, app, aluno, outro_aluno
    ):
        with app.app_context():
            versao_outro = VersaoGlobal(
                numero_versao=1, descricao='Do outro', divisao='LIVRE',
                data_inicio=date.today(), user_id=outro_aluno
            )
            db.session.add(versao_outro)
            db.session.commit()
            versao_outro_id = versao_outro.id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_outro_id}/editar', data={
            'descricao': 'Invadido'
        })

        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_outro_id)
            assert versao.descricao == 'Do outro'

    def test_nao_permite_editar_versao_finalizada(self, aluno_client, app, aluno):
        self._criar_versao(aluno_client)
        with app.app_context():
            versao = VersaoGlobal.query.filter_by(user_id=aluno).first()
            versao.data_fim = date.today()
            db.session.commit()
            versao_id = versao.id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/editar', data={
            'descricao': 'Tentando editar finalizada'
        })

        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.descricao == 'Original'


class TestFinalizarVersaoLivre:
    def _preparar(self, client, app, user_id, com_exercicio=True):
        client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v'})
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=user_id).first().id
        client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': 'Treino A', 'descricao_treino': ''
        })
        with app.app_context():
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id
        if com_exercicio:
            with app.app_context():
                ex = ExercicioUsuario(usuario_id=user_id, nome='Supino')
                db.session.add(ex)
                db.session.commit()
                ex_id = ex.id
            client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino/{tv_id}', data={
                'nome_treino': 'Treino A', 'descricao_treino': '', 'exercicios[]': [f'u_{ex_id}']
            })
        return versao_id

    def test_nao_finaliza_sem_nenhum_treino(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v'})
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/finalizar')
        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.data_fim is None

    def test_nao_finaliza_com_treino_sem_exercicio(self, aluno_client, app, aluno):
        versao_id = self._preparar(aluno_client, app, aluno, com_exercicio=False)
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/finalizar')
        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.data_fim is None

    def test_finaliza_com_sucesso_e_grava_data_de_hoje(self, aluno_client, app, aluno):
        versao_id = self._preparar(aluno_client, app, aluno, com_exercicio=True)
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/finalizar')
        with app.app_context():
            versao = db.session.get(VersaoGlobal, versao_id)
            assert versao.data_fim == date.today()

    def test_apos_finalizar_permite_criar_nova_versao(self, aluno_client, app, aluno):
        self._preparar(aluno_client, app, aluno, com_exercicio=True)
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/finalizar')
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v2'})
        with app.app_context():
            versoes = VersaoGlobal.query.filter_by(user_id=aluno).order_by(VersaoGlobal.numero_versao).all()
            assert len(versoes) == 2
            assert versoes[1].descricao == 'v2'
            assert versoes[1].data_fim is None


class TestRemoverTreinoLivre:
    def test_remove_treino_da_versao(self, aluno_client, app, aluno):
        aluno_client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'v'})
        with app.app_context():
            versao_id = VersaoGlobal.query.filter_by(user_id=aluno).first().id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino', data={
            'nome_treino': 'Treino A', 'descricao_treino': ''
        })
        with app.app_context():
            tv_id = TreinoVersao.query.filter_by(versao_id=versao_id).first().id
        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_id}/treino/{tv_id}/remover')
        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is None

    def test_idor_nao_permite_remover_treino_de_outro_usuario(self, aluno_client, app, aluno, outro_aluno):
        with app.app_context():
            versao_outro = VersaoGlobal(
                numero_versao=1, descricao='Do outro', divisao='LIVRE',
                data_inicio=date.today(), user_id=outro_aluno
            )
            db.session.add(versao_outro)
            db.session.commit()
            tv_outro = TreinoVersao(versao_id=versao_outro.id, codigo='A', nome_treino='X')
            db.session.add(tv_outro)
            db.session.commit()
            versao_outro_id, tv_outro_id = versao_outro.id, tv_outro.id

        aluno_client.post(f'/aluno/cadastrar-treinos/{versao_outro_id}/treino/{tv_outro_id}/remover')
        with app.app_context():
            assert db.session.get(TreinoVersao, tv_outro_id) is not None


class TestAcessoNaoAutenticado:
    def test_get_sem_login_redireciona(self, client):
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code in (302, 401)

    def test_post_sem_login_redireciona(self, client):
        resp = client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'x'})
        assert resp.status_code in (302, 401)