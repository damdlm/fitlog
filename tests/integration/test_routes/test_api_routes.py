"""
Testes de regressão para as rotas VIVAS de routes/api_routes.py.

Antes de escrever testes, foi feita uma triagem no frontend
(templates + JS): das 12 rotas do arquivo, 5 não são chamadas por
nenhum template/JS (evolucao/<id>, criar-exercicio, e as 3 de
catalogo/*) -- ficaram de fora aqui de propósito, por serem código
morto (não vale testar o que nunca roda). /debug/rotas é utilitário
de dev, também fora do escopo.
"""
from datetime import date

from models import db, User, Musculo, ExercicioUsuario, RegistroTreino, HistoricoTreino
from services.versao_service import VersaoService
from services.treino_service import TreinoService
from services.billing_service import BillingService


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()
    # Trial de 30 dias, igual ao que o cadastro de verdade concede --
    # sem isso o aluno cai bloqueado das telas premium (ver
    # utils/decorators.py:aluno_premium_required) e testes que não são
    # sobre cobrança quebram por um motivo alheio ao que testam.
    BillingService.iniciar_trial_aluno(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestApiProgresso:
    def test_sem_registros_retorna_listas_vazias(self, client, app):
        with app.app_context():
            _criar_usuario('api_prog_1')
        _login(client, 'api_prog_1')

        resp = client.get('/api/progresso')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"semanas": [], "volumes": [], "cargas_medias": []}

    def test_com_registro_recente_retorna_janela_de_30_dias(self, client, app):
        with app.app_context():
            u = _criar_usuario('api_prog_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()

            from datetime import datetime, timezone
            hoje = datetime.now(timezone.utc)
            reg = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='agosto/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=hoje, user_id=u.id
            )
            db.session.add(reg)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=reg.id, carga=50, repeticoes=10, ordem=1))
            db.session.commit()

        _login(client, 'api_prog_2')
        resp = client.get('/api/progresso')

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['semanas']) == 30
        assert len(data['volumes']) == 30
        assert len(data['cargas_medias']) == 30

    def test_requer_login(self, client):
        resp = client.get('/api/progresso')
        assert resp.status_code == 302


class TestApiBuscarMusculo:
    def test_sem_nome_retorna_encontrado_false(self, client, app):
        with app.app_context():
            _criar_usuario('api_musc_1')
        _login(client, 'api_musc_1')

        resp = client.get('/api/buscar-musculo')
        assert resp.get_json()['encontrado'] is False

    def test_nome_desconhecido_retorna_nao_encontrado(self, client, app):
        with app.app_context():
            _criar_usuario('api_musc_2')
        _login(client, 'api_musc_2')

        resp = client.get('/api/buscar-musculo?nome=xyzabc-nao-existe-123')
        assert resp.status_code == 200
        assert resp.get_json()['encontrado'] is False


class TestApiVerificarTreino:
    def test_codigo_inexistente(self, client, app):
        with app.app_context():
            _criar_usuario('api_verif_1')
        _login(client, 'api_verif_1')

        resp = client.get('/api/verificar-treino?id=Z')
        assert resp.get_json() == {"existe": False}

    def test_codigo_existente_do_proprio_usuario(self, client, app):
        with app.app_context():
            u = _criar_usuario('api_verif_2')
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
        _login(client, 'api_verif_2')

        resp = client.get('/api/verificar-treino?id=A')
        assert resp.get_json() == {"existe": True}

    def test_nao_ve_codigo_de_outro_usuario(self, client, app):
        """Isolamento: current_user implícito no TreinoService.get_by_codigo."""
        with app.app_context():
            _criar_usuario('api_verif_a')
            b = _criar_usuario('api_verif_b')
            TreinoService.create('A', 'Treino do B', 'd', user_id=b.id)
        _login(client, 'api_verif_a')

        resp = client.get('/api/verificar-treino?id=A')
        assert resp.get_json() == {"existe": False}

    def test_requer_login(self, client):
        resp = client.get('/api/verificar-treino?id=A')
        assert resp.status_code == 302


class TestApiVersaoExercicios:
    def test_retorna_exercicios_da_versao(self, client, app):
        with app.app_context():
            u = _criar_usuario('api_ve_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [ex.id], [], user_id=u.id)
            versao_id = versao.id

        _login(client, 'api_ve_1')
        resp = client.get(f'/api/versao-exercicios/{versao_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['nome'] == 'Supino'
        assert data[0]['musculo'] == 'Peito'
        assert 'treino' not in data[0]  # campo morto removido em rodada anterior

    def test_versao_inexistente_retorna_lista_vazia(self, client, app):
        with app.app_context():
            _criar_usuario('api_ve_2')
        _login(client, 'api_ve_2')

        resp = client.get('/api/versao-exercicios/999999')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_requer_login(self, client):
        resp = client.get('/api/versao-exercicios/1')
        assert resp.status_code == 302


class TestApiReordenarExercicios:
    def test_dados_incompletos_retorna_400(self, client, app):
        with app.app_context():
            _criar_usuario('api_reo_1')
        _login(client, 'api_reo_1')

        resp = client.post('/api/reordenar-exercicios', json={})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_reordena_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('api_reo_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            ex1 = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            ex2 = ExercicioUsuario(usuario_id=u.id, nome='Crucifixo', musculo_id=musc.id)
            db.session.add_all([ex1, ex2])
            db.session.commit()
            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [ex1.id, ex2.id], [], user_id=u.id)
            versao_id = versao.id
            nova_ordem = [f'u_{ex2.id}', f'u_{ex1.id}']

        _login(client, 'api_reo_2')
        resp = client.post('/api/reordenar-exercicios', json={
            'versao_id': versao_id, 'treino_codigo': 'A', 'nova_ordem': nova_ordem
        })

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_requer_login(self, client):
        resp = client.post('/api/reordenar-exercicios', json={
            'versao_id': 1, 'treino_codigo': 'A', 'nova_ordem': ['u_1']
        })
        assert resp.status_code == 302
