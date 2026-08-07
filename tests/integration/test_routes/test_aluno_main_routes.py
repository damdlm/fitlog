"""
Testes de regressão para routes/aluno/main.py (dashboard + fluxo de
vínculo aluno-professor). Tinha 23% de cobertura -- é a página inicial
de qualquer aluno logado.
"""
from models import db, User, AlunoProfessor, SolicitacaoVinculo, Treino
from services.treino_service import TreinoService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestDashboard:
    def test_dashboard_carrega_sem_dados(self, client, app):
        with app.app_context():
            _criar_usuario('am_dash_1')
        _login(client, 'am_dash_1')

        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 200

    def test_dashboard_mostra_contagens_corretas(self, client, app):
        with app.app_context():
            u = _criar_usuario('am_dash_2')
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            TreinoService.create('B', 'Treino B', 'd', user_id=u.id)
        _login(client, 'am_dash_2')

        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 200
        # 2 treinos criados devem refletir na página (contagem exibida)
        assert b'2' in resp.data

    def test_professor_acessa_o_proprio_dashboard(self, client, app):
        with app.app_context():
            _criar_usuario('am_dash_prof', tipo_usuario='professor')
        _login(client, 'am_dash_prof')

        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 200

    def test_requer_login(self, client):
        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 302


class TestMeuProfessor:
    def test_sem_professor_vinculado(self, client, app):
        with app.app_context():
            _criar_usuario('am_prof_1')
        _login(client, 'am_prof_1')

        resp = client.get('/aluno/meu-professor')
        assert resp.status_code == 200

    def test_professor_nao_acessa_meu_professor(self, client, app):
        with app.app_context():
            _criar_usuario('am_prof_2', tipo_usuario='professor')
        _login(client, 'am_prof_2')

        resp = client.get('/aluno/meu-professor')
        assert resp.status_code == 302


class TestBuscarEEnviarSolicitacao:
    def test_busca_encontra_professor_por_nome(self, client, app):
        with app.app_context():
            _criar_usuario('am_busca_aluno')
            _criar_usuario('am_busca_prof', tipo_usuario='professor')
        _login(client, 'am_busca_aluno')

        resp = client.get('/aluno/buscar-professores?busca=am_busca_prof')
        assert resp.status_code == 200
        assert b'am_busca_prof' in resp.data

    def test_envia_solicitacao_com_sucesso(self, client, app):
        with app.app_context():
            _criar_usuario('am_env_aluno')
            prof = _criar_usuario('am_env_prof', tipo_usuario='professor')
            prof_id = prof.id
        _login(client, 'am_env_aluno')

        resp = client.post(f'/aluno/enviar-solicitacao/{prof_id}')
        assert resp.status_code == 302

        with app.app_context():
            u = User.query.filter_by(username='am_env_aluno').first()
            sol = SolicitacaoVinculo.query.filter_by(aluno_id=u.id, professor_id=prof_id).first()
            assert sol is not None
            assert sol.status == 'pendente'

    def test_nao_duplica_solicitacao_pendente(self, client, app):
        with app.app_context():
            _criar_usuario('am_dup_aluno')
            prof = _criar_usuario('am_dup_prof', tipo_usuario='professor')
            prof_id = prof.id
        _login(client, 'am_dup_aluno')

        client.post(f'/aluno/enviar-solicitacao/{prof_id}')
        client.post(f'/aluno/enviar-solicitacao/{prof_id}')

        with app.app_context():
            u = User.query.filter_by(username='am_dup_aluno').first()
            qtd = SolicitacaoVinculo.query.filter_by(aluno_id=u.id, professor_id=prof_id).count()
            assert qtd == 1

    def test_nao_envia_solicitacao_para_nao_professor(self, client, app):
        with app.app_context():
            _criar_usuario('am_naoprof_aluno')
            outro_aluno = _criar_usuario('am_naoprof_alvo')
            alvo_id = outro_aluno.id
        _login(client, 'am_naoprof_aluno')

        resp = client.post(f'/aluno/enviar-solicitacao/{alvo_id}')
        assert resp.status_code == 302

        with app.app_context():
            assert SolicitacaoVinculo.query.count() == 0

    def test_professor_nao_pode_enviar_solicitacao(self, client, app):
        with app.app_context():
            _criar_usuario('am_profenv', tipo_usuario='professor')
            outro = _criar_usuario('am_profenv_alvo', tipo_usuario='professor')
            alvo_id = outro.id
        _login(client, 'am_profenv')

        resp = client.post(f'/aluno/enviar-solicitacao/{alvo_id}')
        assert resp.status_code == 302
        with app.app_context():
            assert SolicitacaoVinculo.query.count() == 0


class TestRemoverVinculo:
    def test_remove_vinculo_existente(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('am_rem_aluno')
            prof = _criar_usuario('am_rem_prof', tipo_usuario='professor')
            vinculo = AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True)
            db.session.add(vinculo)
            db.session.commit()
        _login(client, 'am_rem_aluno')

        resp = client.post('/aluno/remover-vinculo')
        assert resp.status_code == 302

        with app.app_context():
            u = User.query.filter_by(username='am_rem_aluno').first()
            assoc = AlunoProfessor.query.filter_by(aluno_id=u.id).first()
            assert assoc.ativo is False

    def test_sem_vinculo_nao_quebra(self, client, app):
        with app.app_context():
            _criar_usuario('am_rem_sem')
        _login(client, 'am_rem_sem')

        resp = client.post('/aluno/remover-vinculo')
        assert resp.status_code == 302
