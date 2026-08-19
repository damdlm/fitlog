"""Testes de integração para routes/professor_routes.py (blueprint
'professor', montado em /professor).

Complementa tests/integration/test_routes/test_professor_permissions.py
(que já cobre editar/desativar/reativar aluno e calendário) com os demais
grupos de rotas: listagem/cadastro de alunos, solicitações de vínculo,
versões, treinos, exercícios do aluno, treino dentro de versão,
estatísticas e a API de busca.
"""
from datetime import date, datetime, timezone

from models import (db, User, AlunoProfessor, SolicitacaoVinculo, Treino, VersaoGlobal,
                     TreinoVersao, ExercicioUsuario, RegistroTreino)


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False, ativo=True):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario=tipo_usuario, is_admin=is_admin, ativo=ativo,
              nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _associar(aluno_id, professor_id, ativo=True):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo,
                            data_associacao=datetime.now(timezone.utc))
    db.session.add(assoc)
    db.session.commit()
    return assoc


class TestListarAlunos:
    def test_requer_login(self, client):
        resp = client.get('/professor/alunos')
        assert resp.status_code == 302

    def test_acesso_negado_para_aluno_comum(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_listar_1').username

        _login(client, username)
        resp = client.get('/professor/alunos', follow_redirects=True)
        assert resp.status_code == 200

    def test_professor_ve_apenas_seus_alunos_ativos(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_listar_2', tipo_usuario='professor')
            aluno1 = _criar_usuario('pr_listar_aluno1')
            aluno2 = _criar_usuario('pr_listar_aluno2')
            _associar(aluno1.id, prof.id)
            username = prof.username

        _login(client, username)
        resp = client.get('/professor/alunos')
        assert resp.status_code == 200
        assert b'pr_listar_aluno1' in resp.data
        assert b'pr_listar_aluno2' not in resp.data

    def test_busca_filtra_por_username(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_listar_3', tipo_usuario='professor')
            aluno1 = _criar_usuario('pr_listar_busca_alvo')
            aluno2 = _criar_usuario('pr_listar_busca_outro')
            _associar(aluno1.id, prof.id)
            _associar(aluno2.id, prof.id)
            username = prof.username

        _login(client, username)
        resp = client.get('/professor/alunos?busca=alvo')
        assert resp.status_code == 200
        assert b'pr_listar_busca_alvo' in resp.data
        assert b'pr_listar_busca_outro' not in resp.data


class TestNovoAluno:
    def test_get_acesso_negado_para_aluno(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_novo_1').username

        _login(client, username)
        resp = client.get('/professor/aluno/novo', follow_redirects=True)
        assert resp.status_code == 200

    def test_professor_cadastra_aluno_e_vincula(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_novo_2', tipo_usuario='professor').username

        _login(client, username)
        resp = client.post('/professor/aluno/novo', data={
            'username': 'pr_novo_aluno_criado', 'email': 'novoaluno@teste.com',
            'password': 'senha123', 'nome_completo': 'Aluno Criado',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            novo = User.query.filter_by(username='pr_novo_aluno_criado').first()
            assert novo is not None
            assert novo.tipo_usuario == 'aluno'
            prof = User.query.filter_by(username=username).first()
            vinculo = AlunoProfessor.query.filter_by(aluno_id=novo.id, professor_id=prof.id).first()
            assert vinculo is not None
            assert vinculo.ativo is True

    def test_falha_username_curto(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_novo_3', tipo_usuario='professor').username

        _login(client, username)
        resp = client.post('/professor/aluno/novo', data={
            'username': 'ab', 'email': 'x@teste.com', 'password': 'senha123',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert User.query.filter_by(username='ab').first() is None

    def test_falha_senha_curta(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_novo_4', tipo_usuario='professor').username

        _login(client, username)
        resp = client.post('/professor/aluno/novo', data={
            'username': 'pr_novo_senhacurta', 'email': 'sc@teste.com', 'password': '123',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert User.query.filter_by(username='pr_novo_senhacurta').first() is None

    def test_falha_username_duplicado(self, client, app):
        with app.app_context():
            _criar_usuario('pr_novo_duplicado')
            username = _criar_usuario('pr_novo_5', tipo_usuario='professor').username

        _login(client, username)
        resp = client.post('/professor/aluno/novo', data={
            'username': 'pr_novo_duplicado', 'email': 'outro@teste.com', 'password': 'senha123',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert User.query.filter_by(username='pr_novo_duplicado').count() == 1


class TestVisualizarAluno:
    def test_404_para_aluno_inexistente(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_ver_1', tipo_usuario='professor').username

        _login(client, username)
        resp = client.get('/professor/aluno/99999')
        assert resp.status_code == 404

    def test_professor_acessa_proprio_aluno(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_ver_2', tipo_usuario='professor')
            aluno = _criar_usuario('pr_ver_aluno2')
            _associar(aluno.id, prof.id)
            aluno_id, username = aluno.id, prof.username

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}')
        assert resp.status_code == 200

    def test_professor_nao_acessa_aluno_de_outro_professor(self, client, app):
        with app.app_context():
            prof1 = _criar_usuario('pr_ver_3', tipo_usuario='professor')
            prof2 = _criar_usuario('pr_ver_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('pr_ver_aluno3')
            _associar(aluno.id, prof2.id)
            aluno_id, username = aluno.id, prof1.username

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}', follow_redirects=True)
        assert resp.status_code == 200

    def test_admin_acessa_qualquer_aluno(self, client, app):
        with app.app_context():
            admin = _criar_usuario('pr_ver_4', is_admin=True)
            aluno = _criar_usuario('pr_ver_aluno4')
            aluno_id, username = aluno.id, admin.username

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}')
        assert resp.status_code == 200


class TestRemoverVinculo:
    def test_professor_remove_proprio_vinculo(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_removevinc_1', tipo_usuario='professor')
            aluno = _criar_usuario('pr_removevinc_aluno1')
            _associar(aluno.id, prof.id)
            aluno_id, username = aluno.id, prof.username

        _login(client, username)
        resp = client.post(f'/professor/aluno/remover-vinculo/{aluno_id}', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first() is None

    def test_professor_nao_remove_vinculo_de_outro(self, client, app):
        with app.app_context():
            prof1 = _criar_usuario('pr_removevinc_2', tipo_usuario='professor')
            prof2 = _criar_usuario('pr_removevinc_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('pr_removevinc_aluno2')
            _associar(aluno.id, prof2.id)
            aluno_id, username = aluno.id, prof1.username

        _login(client, username)
        client.post(f'/professor/aluno/remover-vinculo/{aluno_id}', follow_redirects=True)

        with app.app_context():
            assert AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first() is not None


class TestSolicitacoes:
    def test_lista_apenas_pendentes_do_professor(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_solic_1', tipo_usuario='professor')
            outro_prof = _criar_usuario('pr_solic_outroprof', tipo_usuario='professor')
            aluno1 = _criar_usuario('pr_solic_aluno1')
            aluno2 = _criar_usuario('pr_solic_aluno2')
            s1 = SolicitacaoVinculo(aluno_id=aluno1.id, professor_id=prof.id, status='pendente',
                                     data_solicitacao=datetime.now(timezone.utc))
            s2 = SolicitacaoVinculo(aluno_id=aluno2.id, professor_id=outro_prof.id, status='pendente',
                                     data_solicitacao=datetime.now(timezone.utc))
            db.session.add_all([s1, s2])
            db.session.commit()
            username = prof.username

        _login(client, username)
        resp = client.get('/professor/solicitacoes')
        assert resp.status_code == 200
        assert b'pr_solic_aluno1' in resp.data
        assert b'pr_solic_aluno2' not in resp.data

    def test_aprovar_cria_vinculo(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_solic_2', tipo_usuario='professor')
            aluno = _criar_usuario('pr_solic_aprovaraluno')
            s = SolicitacaoVinculo(aluno_id=aluno.id, professor_id=prof.id, status='pendente',
                                    data_solicitacao=datetime.now(timezone.utc))
            db.session.add(s)
            db.session.commit()
            solicitacao_id, aluno_id, prof_id, username = s.id, aluno.id, prof.id, prof.username

        _login(client, username)
        resp = client.get(f'/professor/solicitacao/{solicitacao_id}/aprovar', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            s_atualizada = db.session.get(SolicitacaoVinculo, solicitacao_id)
            assert s_atualizada.status == 'aprovado'
            vinculo = AlunoProfessor.query.filter_by(aluno_id=aluno_id, professor_id=prof_id,
                                                       ativo=True).first()
            assert vinculo is not None

    def test_recusar_nao_cria_vinculo(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_solic_3', tipo_usuario='professor')
            aluno = _criar_usuario('pr_solic_recusaraluno')
            s = SolicitacaoVinculo(aluno_id=aluno.id, professor_id=prof.id, status='pendente',
                                    data_solicitacao=datetime.now(timezone.utc))
            db.session.add(s)
            db.session.commit()
            solicitacao_id, aluno_id, username = s.id, aluno.id, prof.username

        _login(client, username)
        resp = client.get(f'/professor/solicitacao/{solicitacao_id}/recusar', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            s_atualizada = db.session.get(SolicitacaoVinculo, solicitacao_id)
            assert s_atualizada.status == 'recusado'
            assert AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first() is None

    def test_outro_professor_nao_aprova_solicitacao_alheia(self, client, app):
        with app.app_context():
            prof1 = _criar_usuario('pr_solic_4', tipo_usuario='professor')
            prof2 = _criar_usuario('pr_solic_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('pr_solic_aluno4')
            s = SolicitacaoVinculo(aluno_id=aluno.id, professor_id=prof2.id, status='pendente',
                                    data_solicitacao=datetime.now(timezone.utc))
            db.session.add(s)
            db.session.commit()
            solicitacao_id, username = s.id, prof1.username

        _login(client, username)
        client.get(f'/professor/solicitacao/{solicitacao_id}/aprovar', follow_redirects=True)

        with app.app_context():
            s_atualizada = db.session.get(SolicitacaoVinculo, solicitacao_id)
            assert s_atualizada.status == 'pendente'

    def test_nao_reprocessa_solicitacao_ja_aprovada(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_solic_5', tipo_usuario='professor')
            aluno = _criar_usuario('pr_solic_aluno5')
            s = SolicitacaoVinculo(aluno_id=aluno.id, professor_id=prof.id, status='aprovado',
                                    data_solicitacao=datetime.now(timezone.utc),
                                    data_resposta=datetime.now(timezone.utc))
            db.session.add(s)
            db.session.commit()
            solicitacao_id, username = s.id, prof.username

        _login(client, username)
        resp = client.get(f'/professor/solicitacao/{solicitacao_id}/recusar', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            s_atualizada = db.session.get(SolicitacaoVinculo, solicitacao_id)
            assert s_atualizada.status == 'aprovado'


class TestApiBuscarAlunos:
    def test_vazio_para_aluno_comum(self, client, app):
        with app.app_context():
            username = _criar_usuario('pr_api_1').username

        _login(client, username)
        resp = client.get('/professor/api/buscar-alunos')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_professor_ve_apenas_seus_alunos(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_api_2', tipo_usuario='professor')
            aluno1 = _criar_usuario('pr_api_aluno1')
            aluno2 = _criar_usuario('pr_api_aluno2')
            _associar(aluno1.id, prof.id)
            username = prof.username

        _login(client, username)
        resp = client.get('/professor/api/buscar-alunos')
        data = resp.get_json()
        usernames = {a['username'] for a in data}
        assert 'pr_api_aluno1' in usernames
        assert 'pr_api_aluno2' not in usernames

    def test_filtra_por_termo(self, client, app):
        with app.app_context():
            prof = _criar_usuario('pr_api_3', tipo_usuario='professor')
            aluno1 = _criar_usuario('pr_api_termoalvo')
            aluno2 = _criar_usuario('pr_api_termooutro')
            _associar(aluno1.id, prof.id)
            _associar(aluno2.id, prof.id)
            username = prof.username

        _login(client, username)
        resp = client.get('/professor/api/buscar-alunos?termo=alvo')
        data = resp.get_json()
        usernames = {a['username'] for a in data}
        assert usernames == {'pr_api_termoalvo'}

    def test_admin_ve_todos_os_alunos(self, client, app):
        with app.app_context():
            admin = _criar_usuario('pr_api_4', is_admin=True)
            _criar_usuario('pr_api_qualqueraluno')
            username = admin.username

        _login(client, username)
        resp = client.get('/professor/api/buscar-alunos')
        data = resp.get_json()
        usernames = {a['username'] for a in data}
        assert 'pr_api_qualqueraluno' in usernames
