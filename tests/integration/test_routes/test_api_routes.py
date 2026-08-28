"""
Testes de regressão para as rotas VIVAS de routes/api_routes.py.

Antes de escrever testes, foi feita uma triagem no frontend
(templates + JS): das rotas do arquivo, algumas não são chamadas por
nenhum template/JS (evolucao/<id>, e as de catalogo/*) -- ficaram de
fora aqui de propósito, por serem código morto (não vale testar o que
nunca roda). /debug/rotas é utilitário de dev, também fora do escopo.
/api/verificar-treino foi removida junto com a tela "Meus Treinos"
(treino deixou de ter um código único por usuário -- agora é só único
dentro da versão).
"""
from datetime import date

from models import db, User, Musculo, ExercicioUsuario, TreinoVersao, VersaoGlobal, VersaoExercicio, RegistroTreino, HistoricoTreino
from services.billing_service import BillingService


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()
    # Trial de 30 dias, igual ao que o cadastro de verdade concede --
    # sem isso o aluno cai bloqueado das telas premium (ver
    # utils/decorators.py:acesso_premium_required) e testes que não são
    # sobre cobrança quebram por um motivo alheio ao que testam.
    BillingService.iniciar_trial(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _criar_versao_com_treino(user_id, codigo='A', usuario_ids=None, base_ids=None):
    """Cria versão + treino (TreinoVersao) + associa exercícios, direto
    no banco -- equivalente ao que VersaoService.adicionar_treino_livre
    faz na tela "Cadastrar Treinos"."""
    versao = VersaoGlobal(numero_versao=1, descricao='Bloco', divisao='ABC',
                           data_inicio=date(2026, 1, 1), user_id=user_id)
    db.session.add(versao)
    db.session.commit()

    treino = TreinoVersao(versao_id=versao.id, codigo=codigo, nome_treino=f'Treino {codigo}', descricao_treino='d')
    db.session.add(treino)
    db.session.commit()

    for idx, ex_id in enumerate(usuario_ids or []):
        db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex_id, ordem=idx))
    for idx, ex_id in enumerate(base_ids or [], start=len(usuario_ids or [])):
        db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_base_id=ex_id, ordem=idx))
    db.session.commit()

    return versao, treino


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
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            versao, treino = _criar_versao_com_treino(u.id, usuario_ids=[ex.id])

            from datetime import datetime, timezone
            hoje = datetime.now(timezone.utc)
            reg = RegistroTreino(
                treino_versao_id=treino.id, versao_id=versao.id, periodo='agosto/2026', semana=1,
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


class TestApiVersaoExercicios:
    def test_retorna_exercicios_da_versao(self, client, app):
        with app.app_context():
            u = _criar_usuario('api_ve_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            versao, treino = _criar_versao_com_treino(u.id, usuario_ids=[ex.id])
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
            ex1 = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            ex2 = ExercicioUsuario(usuario_id=u.id, nome='Crucifixo', musculo_id=musc.id)
            db.session.add_all([ex1, ex2])
            db.session.commit()
            versao, treino = _criar_versao_com_treino(u.id, usuario_ids=[ex1.id, ex2.id])
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
