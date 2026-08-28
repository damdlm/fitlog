"""Testes de integração para routes/professor_routes.py -- exercícios do
aluno, estatísticas, calendário.

As classes de teste de versão/treino com divisão fixa (Nova Versão,
gerenciamento de treino avulso do aluno, treino dentro de versão) foram
removidas junto com essas telas, que ficaram obsoletas depois que a tela
"Cadastrar Treinos" passou a ser o único fluxo de criação de
versão/treino.
"""
from datetime import date, datetime, timezone

from models import (db, User, AlunoProfessor, VersaoGlobal,
                     TreinoVersao, VersaoExercicio, ExercicioUsuario, RegistroTreino)


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario=tipo_usuario, is_admin=is_admin,
              nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _associar(aluno_id, professor_id):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=True,
                            data_associacao=datetime.now(timezone.utc))
    db.session.add(assoc)
    db.session.commit()
    return assoc


def _criar_versao(user_id, numero=1, data_inicio=date(2024, 1, 1), data_fim=None):
    v = VersaoGlobal(numero_versao=numero, descricao=f'Versao {numero}', divisao='ABC',
                      data_inicio=data_inicio, data_fim=data_fim, user_id=user_id)
    db.session.add(v)
    db.session.commit()
    return v


def _criar_treino_versao(versao_id, codigo='A', nome='Treino A', ordem=0):
    tv = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=nome,
                       descricao_treino='desc', ordem=ordem)
    db.session.add(tv)
    db.session.commit()
    return tv


def _criar_exercicio(user_id, nome='Supino'):
    ex = ExercicioUsuario(usuario_id=user_id, nome=nome)
    db.session.add(ex)
    db.session.commit()
    return ex


def _setup_prof_aluno(app, prefix):
    """Helper: cria professor + aluno vinculados, retorna (prof_id, aluno_id, username)."""
    prof = _criar_usuario(f'{prefix}_prof', tipo_usuario='professor')
    aluno = _criar_usuario(f'{prefix}_aluno')
    _associar(aluno.id, prof.id)
    return prof.id, aluno.id, prof.username


class TestExerciciosAluno:
    def test_lista_exercicios(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_listaex1')
            _criar_exercicio(aluno_id, nome='Supino Reto')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/exercicios')
        assert resp.status_code == 200
        assert b'Supino Reto' in resp.data


class TestNovoExercicioAluno:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novoex1')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/exercicio/novo')
        assert resp.status_code == 200

    def test_post_cria_exercicio_com_sucesso(self, client, app):
        """
        Bug corrigido: a rota chamava
        ExercicioService.criar_exercicio_customizado(..., treino_id=treino_id),
        mas a assinatura do serviço não aceita esse parâmetro -- sempre
        lançava TypeError. Corrigido removendo o argumento inválido da
        chamada (o vínculo com um treino específico não fazia parte do
        que o serviço de fato implementa).
        """
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novoex2')

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/exercicio/novo', data={
            'nome': 'Supino', 'musculo': 'Peito', 'descricao': 'd'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            ex = ExercicioUsuario.query.filter_by(usuario_id=aluno_id, nome='Supino').first()
            assert ex is not None

    def test_post_falha_sem_nome(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novoex3')

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/exercicio/novo', data={
            'nome': '', 'musculo': 'Peito'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert ExercicioUsuario.query.filter_by(usuario_id=aluno_id).count() == 0


class TestEditarExercicioAluno:
    def test_get_exibe_formulario_para_customizado(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editex1')
            ex = _criar_exercicio(aluno_id)
            ex_id = ex.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/exercicio/{ex_id}')
        assert resp.status_code == 200

    def test_404_exercicio_inexistente(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editex2')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/exercicio/99999', follow_redirects=True)
        assert resp.status_code == 200

    def test_post_atualiza_exercicio(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editex3')
            ex = _criar_exercicio(aluno_id)
            ex_id = ex.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/exercicio/{ex_id}', data={
            'nome': 'Supino Editado', 'musculo': 'Peito', 'descricao': 'nova'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            ex_atualizado = db.session.get(ExercicioUsuario, ex_id)
            assert ex_atualizado.nome == 'Supino Editado'


class TestExcluirExercicioAluno:
    def test_pede_confirmacao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclex1')
            ex = _criar_exercicio(aluno_id)
            ex_id = ex.id

        _login(client, username)
        client.post(f'/professor/aluno/{aluno_id}/exercicio/{ex_id}/excluir',
                     follow_redirects=True)

        with app.app_context():
            assert db.session.get(ExercicioUsuario, ex_id) is not None

    def test_exclui_com_confirmacao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclex2')
            ex = _criar_exercicio(aluno_id)
            ex_id = ex.id

        _login(client, username)
        resp = client.post(
            f'/professor/aluno/{aluno_id}/exercicio/{ex_id}/excluir?confirmar=true',
            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(ExercicioUsuario, ex_id) is None




class TestEstatisticasAluno:
    def test_exibe_estatisticas_sem_registros(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_estat1')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas')
        assert resp.status_code == 200

    def test_exibe_estatisticas_com_registros(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_estat2')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino_versao(versao.id)
            ex = _criar_exercicio(aluno_id)
            from models import HistoricoTreino
            reg = RegistroTreino(treino_versao_id=treino.id, versao_id=versao.id, periodo='Jan/2024',
                                  semana=1, exercicio_usuario_id=ex.id,
                                  data_registro=date(2024, 1, 10), user_id=aluno_id)
            db.session.add(reg)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=reg.id, carga=50, repeticoes=10, ordem=1))
            db.session.commit()

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas')
        assert resp.status_code == 200


class TestCalendarioAluno:
    def test_exibe_calendario(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_calend1')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/calendario')
        assert resp.status_code == 200

    def test_outro_professor_sem_acesso(self, client, app):
        with app.app_context():
            _, aluno_id, _ = _setup_prof_aluno(app, 'pr_calend2')
            outro_prof = _criar_usuario('pr_calend2_outro', tipo_usuario='professor')
            username = outro_prof.username

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/calendario', follow_redirects=True)
        assert resp.status_code == 200
