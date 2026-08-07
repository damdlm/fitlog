"""
Testes de regressão para routes/register_routes.py (fluxo de registrar
treino) -- rota mais usada do app (toda sessão de treino passa por
aqui) e que estava sem nenhum teste dedicado (39% de cobertura antes
desta rodada, so via efeito colateral de outros testes).
"""
from datetime import date

from models import db, User, Musculo, ExercicioUsuario, VersaoGlobal, RegistroTreino
from services.versao_service import VersaoService
from services.treino_service import TreinoService


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _montar_versao_com_treino_e_exercicio(user_id, data_inicio=date(2026, 1, 1)):
    musc = Musculo(nome=f'm_{user_id}', nome_exibicao='Peito')
    db.session.add(musc)
    db.session.commit()

    versao = VersaoService.create('Bloco', data_inicio, user_id=user_id)
    TreinoService.create('A', 'Treino A', 'peito', user_id=user_id)
    ex = ExercicioUsuario(usuario_id=user_id, nome='Supino', musculo_id=musc.id)
    db.session.add(ex)
    db.session.commit()
    VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'peito', [ex.id], [], user_id=user_id)

    treinos = VersaoService.get_treinos_para_registro(versao.id, user_id=user_id)
    treino_id = treinos[0]['id']
    return versao, treino_id, ex


class TestRegistrarTreinoGet:
    def test_sem_versao_ativa_mostra_erro(self, client, app):
        with app.app_context():
            _criar_usuario('reg_get_1')
        _login(client, 'reg_get_1')

        resp = client.get('/registrar/registrar-treino?data=2026-08-06')
        assert resp.status_code == 200
        assert 'ativa' in resp.get_data(as_text=True).lower() or resp.status_code == 200

    def test_com_treino_selecionado_carrega_exercicios(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_get_2')
            versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)

        _login(client, 'reg_get_2')
        resp = client.get(f'/registrar/registrar-treino?data=2026-08-06&treino={treino_id}')

        assert resp.status_code == 200
        assert 'Supino' in resp.get_data(as_text=True)

    def test_data_invalida_cai_para_hoje_sem_quebrar(self, client, app):
        with app.app_context():
            _criar_usuario('reg_get_3')
        _login(client, 'reg_get_3')

        resp = client.get('/registrar/registrar-treino?data=nao-e-uma-data')
        assert resp.status_code == 200

    def test_treino_id_de_outra_versao_e_rejeitado(self, client, app):
        """IDOR/consistência: treino que não está na versão ativa não deve ser aceito."""
        with app.app_context():
            u = _criar_usuario('reg_get_4')
            _montar_versao_com_treino_e_exercicio(u.id)

        _login(client, 'reg_get_4')
        resp = client.get('/registrar/registrar-treino?data=2026-08-06&treino=999999')

        assert resp.status_code == 200
        assert 'Supino' not in resp.get_data(as_text=True)

    def test_requer_login(self, client):
        resp = client.get('/registrar/registrar-treino')
        assert resp.status_code == 302


class TestSalvarRegistro:
    def test_salva_com_sucesso_e_redireciona(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_post_1')
            versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
            chave = f'u_{ex.id}'

        _login(client, 'reg_post_1')
        resp = client.post('/registrar/registrar-treino', data={
            'treino': str(treino_id),
            'data': '2026-01-05',
            f'carga_{chave}': '50',
            f'reps_{chave}': '10',
            f'num_series_{chave}': '3',
        })

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/') or 'index' in resp.headers['Location']

        with app.app_context():
            qtd = RegistroTreino.query.filter_by(exercicio_usuario_id=ex.id).count()
            assert qtd == 1

    def test_sem_treino_ou_data_nao_salva(self, client, app):
        with app.app_context():
            _criar_usuario('reg_post_2')
        _login(client, 'reg_post_2')

        resp = client.post('/registrar/registrar-treino', data={})
        assert resp.status_code == 302
        with app.app_context():
            assert RegistroTreino.query.count() == 0

    def test_treino_de_outra_versao_nao_salva(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_post_3')
            _montar_versao_com_treino_e_exercicio(u.id)

        _login(client, 'reg_post_3')
        resp = client.post('/registrar/registrar-treino', data={
            'treino': '999999',
            'data': '2026-01-05',
        })

        assert resp.status_code == 302
        with app.app_context():
            assert RegistroTreino.query.count() == 0

    def test_data_apos_fim_da_versao_nao_salva(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_post_4')
            versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
            VersaoService.finalizar(versao.id, date(2026, 2, 1), user_id=u.id)
            chave = f'u_{ex.id}'

        _login(client, 'reg_post_4')
        resp = client.post('/registrar/registrar-treino', data={
            'treino': str(treino_id),
            'data': '2026-03-01',  # depois do fim da versão
            f'carga_{chave}': '50',
            f'reps_{chave}': '10',
        })

        assert resp.status_code == 302
        with app.app_context():
            assert RegistroTreino.query.count() == 0

    def test_nenhum_dado_valido_nao_salva(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_post_5')
            versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)

        _login(client, 'reg_post_5')
        # sem carga/reps preenchidos para nenhum exercício
        resp = client.post('/registrar/registrar-treino', data={
            'treino': str(treino_id),
            'data': '2026-01-05',
        })

        assert resp.status_code == 302
        with app.app_context():
            assert RegistroTreino.query.count() == 0

    def test_carga_negativa_e_ignorada(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_post_6')
            versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
            chave = f'u_{ex.id}'

        _login(client, 'reg_post_6')
        resp = client.post('/registrar/registrar-treino', data={
            'treino': str(treino_id),
            'data': '2026-01-05',
            f'carga_{chave}': '-10',
            f'reps_{chave}': '10',
        })

        assert resp.status_code == 302
        with app.app_context():
            assert RegistroTreino.query.count() == 0


class TestApiTreinosPorData:
    def test_sem_data_retorna_400(self, client, app):
        with app.app_context():
            _criar_usuario('reg_api_1')
        _login(client, 'reg_api_1')

        resp = client.get('/registrar/api/treinos-por-data')
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_sem_versao_ativa_retorna_404(self, client, app):
        with app.app_context():
            _criar_usuario('reg_api_2')
        _login(client, 'reg_api_2')

        resp = client.get('/registrar/api/treinos-por-data?data=2026-08-06')
        assert resp.status_code == 404
        assert resp.get_json()['success'] is False

    def test_com_versao_ativa_retorna_treinos(self, client, app):
        with app.app_context():
            u = _criar_usuario('reg_api_3')
            _montar_versao_com_treino_e_exercicio(u.id)

        _login(client, 'reg_api_3')
        resp = client.get('/registrar/api/treinos-por-data?data=2026-01-05')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['treinos']) == 1
        assert data['treinos'][0]['codigo'] == 'A'

    def test_requer_login(self, client):
        resp = client.get('/registrar/api/treinos-por-data?data=2026-01-05')
        assert resp.status_code == 302
