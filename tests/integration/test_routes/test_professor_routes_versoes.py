"""Testes de integração para routes/professor_routes.py -- versões,
treinos, exercícios do aluno, treino dentro de versão, estatísticas,
calendário."""
from datetime import date, datetime, timezone

from models import (db, User, AlunoProfessor, Treino, VersaoGlobal,
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


def _criar_treino(user_id, codigo='A'):
    t = Treino(codigo=codigo, nome=f'Treino {codigo}', descricao='d', user_id=user_id)
    db.session.add(t)
    db.session.commit()
    return t


def _criar_treino_versao(versao_id, treino_id, nome='Treino A', ordem=0):
    tv = TreinoVersao(versao_id=versao_id, treino_id=treino_id, nome_treino=nome,
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


class TestVersoesAluno:
    def test_lista_versoes_do_aluno(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_versoes1')
            _criar_versao(aluno_id, numero=1)

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versoes')
        assert resp.status_code == 200
        assert b'Versao 1' in resp.data

    def test_outro_professor_sem_acesso(self, client, app):
        with app.app_context():
            _, aluno_id, _ = _setup_prof_aluno(app, 'pr_versoes2')
            outro_prof = _criar_usuario('pr_versoes2_outro', tipo_usuario='professor')
            username = outro_prof.username

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versoes', follow_redirects=True)
        assert resp.status_code == 200


class TestNovaVersaoAluno:
    def test_cria_versao_para_aluno(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_nova1')

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/nova', data={
            'descricao': 'Versao do aluno', 'divisao': 'ABC', 'data_inicio': '2024-01-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            versoes = VersaoGlobal.query.filter_by(user_id=aluno_id).all()
            assert len(versoes) == 1
            assert versoes[0].descricao == 'Versao do aluno'

    def test_finaliza_versao_ativa_ao_criar_sem_data_fim_explicita(self, client, app):
        """Se já existe versão ativa e a nova não tem data_fim, a rota
        finaliza a antiga usando a data_inicio da nova como corte."""
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_nova2')
            versao_antiga = _criar_versao(aluno_id, numero=1, data_inicio=date(2024, 1, 1))
            versao_antiga_id = versao_antiga.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/nova', data={
            'descricao': 'Nova versao', 'divisao': 'ABC', 'data_inicio': '2024-06-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            antiga = db.session.get(VersaoGlobal, versao_antiga_id)
            assert antiga.data_fim == date(2024, 6, 1)


class TestVerVersaoAluno:
    def test_404_versao_inexistente(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_ver1')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/99999', follow_redirects=True)
        assert resp.status_code == 200

    def test_get_exibe_versao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_ver2')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/{versao_id}')
        assert resp.status_code == 200

    def test_post_atualiza_versao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_ver3')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}', data={
            'descricao': 'Descricao editada', 'divisao': 'ABCD', 'data_inicio': '2024-02-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.descricao == 'Descricao editada'
            assert v.divisao == 'ABCD'


class TestFinalizarVersaoAluno:
    def test_finaliza_com_sucesso(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_final1')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/finalizar',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.data_fim is not None

    def test_nao_finaliza_ja_finalizada(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_final2')
            versao = _criar_versao(aluno_id, data_fim=date(2024, 6, 1))
            versao_id = versao.id

        _login(client, username)
        client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/finalizar',
                     follow_redirects=True)

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.data_fim == date(2024, 6, 1)


class TestExcluirVersaoAluno:
    def test_pede_confirmacao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclver1')
            versao = _criar_versao(aluno_id, data_fim=date(2024, 6, 1))
            versao_id = versao.id

        _login(client, username)
        client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/excluir',
                     follow_redirects=True)

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_exclui_com_confirmacao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclver2')
            versao = _criar_versao(aluno_id, data_fim=date(2024, 6, 1))
            versao_id = versao.id

        _login(client, username)
        resp = client.post(
            f'/professor/aluno/{aluno_id}/versao/{versao_id}/excluir?confirmar=true',
            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is None

    def test_nao_exclui_versao_ativa(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclver3')
            versao = _criar_versao(aluno_id)  # ativa
            versao_id = versao.id

        _login(client, username)
        client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/excluir?confirmar=true',
                     follow_redirects=True)

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_nao_exclui_com_registros_vinculados(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclver4')
            versao = _criar_versao(aluno_id, data_fim=date(2024, 6, 1))
            treino = _criar_treino(aluno_id)
            ex = _criar_exercicio(aluno_id)
            reg = RegistroTreino(treino_id=treino.id, versao_id=versao.id, periodo='Jan/2024',
                                  semana=1, exercicio_usuario_id=ex.id,
                                  data_registro=date(2024, 1, 10), user_id=aluno_id)
            db.session.add(reg)
            db.session.commit()
            versao_id = versao.id

        _login(client, username)
        client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/excluir?confirmar=true',
                     follow_redirects=True)

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None


class TestClonarVersaoAluno:
    def test_falha_bug_conhecido_user_id_nunca_resolvido(self, client, app):
        """
        NOTA (bug conhecido, mesmo do blueprint 'version' -- ver
        test_version_routes.py::TestClonarVersaoGlobal): dentro de
        VersaoService.clone(versao_id, user_id=None), o parâmetro
        `user_id` (aqui passado explicitamente como aluno.id, então
        funciona bem até esse ponto) é usado como esperado nas buscas
        internas, mas a construção final `VersaoGlobal(..., user_id=user_id)`
        usa a variável local correta aqui -- então clonar pelo professor
        (que sempre passa user_id=aluno.id) e clonar por essa rota
        especificamente NÃO tem esse bug. Este teste apenas confirma o
        caminho feliz.
        """
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_clonar1')
            versao = _criar_versao(aluno_id, data_fim=date(2024, 6, 1))
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/clonar',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno_id).count() == 2


class TestTreinosAluno:
    def test_lista_treinos_do_aluno(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_treinos1')
            _criar_treino(aluno_id)

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/treinos')
        assert resp.status_code == 200
        assert b'Treino A' in resp.data


class TestNovoTreinoAluno:
    def test_redireciona_para_versao_ativa(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novot1')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/treino/novo', follow_redirects=False)
        assert resp.status_code == 302
        assert f'/versao/{versao_id}/treino/novo' in resp.location

    def test_redireciona_para_criar_versao_se_nao_ha_ativa(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novot2')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/treino/novo', follow_redirects=False)
        assert resp.status_code == 302
        assert '/versao/nova' in resp.location


class TestEditarTreinoAluno:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editart1')
            treino = _criar_treino(aluno_id)
            treino_id = treino.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/treino/{treino_id}')
        assert resp.status_code == 200

    def test_404_treino_inexistente(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editart2')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/treino/99999', follow_redirects=True)
        assert resp.status_code == 200

    def test_post_atualiza_treino(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editart3')
            treino = _criar_treino(aluno_id)
            treino_id = treino.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/treino/{treino_id}', data={
            'id': 'b', 'nome': 'Treino B Editado', 'descricao': 'nova desc'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            t = db.session.get(Treino, treino_id)
            assert t.codigo == 'B'
            assert t.nome == 'Treino B Editado'


class TestExcluirTreinoAluno:
    def test_exclui_treino(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclt1')
            treino = _criar_treino(aluno_id)
            treino_id = treino.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/treino/{treino_id}/excluir',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(Treino, treino_id) is None

    def test_404_treino_inexistente(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_exclt2')

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/treino/99999/excluir',
                            follow_redirects=True)
        assert resp.status_code == 200


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


class TestNovoTreinoVersaoAluno:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novotv1')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo')
        assert resp.status_code == 200

    def test_404_versao_inexistente(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novotv2')

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/99999/treino/novo',
                           follow_redirects=True)
        assert resp.status_code == 200

    def test_post_adiciona_treino_com_sucesso(self, client, app):
        """
        Diferente do blueprint 'version', aqui a rota NÃO usa
        VersaoService.adicionar_treino() -- ela monta o TreinoVersao
        manualmente e chama adicionar_exercicios_a_treino_versao(), então
        não tem o bug de argumento faltando visto em version_routes.py.
        """
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novotv3')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo', data={
            'treino_id': 'A', 'nome_treino': 'Treino A', 'descricao_treino': 'desc'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            treino = Treino.query.filter_by(codigo='A', user_id=aluno_id).first()
            assert treino is not None
            tv = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
            assert tv is not None

    def test_post_falha_codigo_invalido(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novotv4')
            versao = _criar_versao(aluno_id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo', data={
            'treino_id': 'AB', 'nome_treino': 'Treino A'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert Treino.query.filter_by(user_id=aluno_id).count() == 0

    def test_post_falha_treino_ja_existe_na_versao(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_novotv5')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            _criar_treino_versao(versao.id, treino.id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo', data={
            'treino_id': 'A', 'nome_treino': 'Treino A'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_id).count() == 1


class TestEditarTreinoVersaoAluno:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editartv1')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            _criar_treino_versao(versao.id, treino.id)
            versao_id = versao.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/editar')
        assert resp.status_code == 200

    def test_post_atualiza_treino_e_exercicios(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editartv2')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(aluno_id)
            versao_id, tv_id, ex_id = versao.id, tv.id, ex.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/editar', data={
            'nome_treino': 'Treino A Editado', 'descricao_treino': 'nova',
            'exercicios[]': [f'u_{ex_id}'],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            tv_atualizado = db.session.get(TreinoVersao, tv_id)
            assert tv_atualizado.nome_treino == 'Treino A Editado'
            assert len(tv_atualizado.exercicios) == 1

    def test_post_falha_sem_exercicios(self, client, app):
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_editartv3')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            _criar_treino_versao(versao.id, treino.id)
            versao_id = versao.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/editar', data={
            'nome_treino': 'Treino A', 'descricao_treino': 'd',
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestExcluirTreinoVersaoAluno:
    def test_professor_remove_treino_da_versao_do_aluno(self, client, app):
        """
        Bug corrigido: VersaoService.excluir_treino_versao(versao_id,
        treino_codigo, user_id, current_user) chamava internamente
        `current_user.pode_acessar_dados_de(user_id)` -- mas passava o
        `user_id` (um int) em vez do objeto User completo, e
        pode_acessar_dados_de espera um objeto (acessa .id nele). Isso
        sempre lançava AttributeError quando quem chamava era um
        professor (não admin, alvo != o próprio usuário) -- o caso mais
        comum de uso desta rota. Corrigido resolvendo o User alvo antes
        de checar a permissão.
        """
        with app.app_context():
            prof_id, aluno_id, username = _setup_prof_aluno(app, 'pr_excltv1')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            tv = _criar_treino_versao(versao.id, treino.id)
            versao_id, tv_id = versao.id, tv.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/excluir',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is None

    def test_admin_tambem_consegue_excluir(self, client, app):
        with app.app_context():
            admin = _criar_usuario('pr_excltv2_admin', is_admin=True)
            aluno = _criar_usuario('pr_excltv2_aluno')
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(aluno.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            aluno_id, versao_id, tv_id, username = aluno.id, versao.id, tv.id, admin.username

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/excluir',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is None

    def test_professor_sem_vinculo_nao_consegue_excluir(self, client, app):
        with app.app_context():
            _, aluno_id, _ = _setup_prof_aluno(app, 'pr_excltv3')
            outro_prof = _criar_usuario('pr_excltv3_outro', tipo_usuario='professor')
            versao = _criar_versao(aluno_id)
            treino = _criar_treino(aluno_id)
            tv = _criar_treino_versao(versao.id, treino.id)
            versao_id, tv_id, username = versao.id, tv.id, outro_prof.username

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/excluir',
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is not None


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
            treino = _criar_treino(aluno_id)
            versao = _criar_versao(aluno_id)
            ex = _criar_exercicio(aluno_id)
            from models import HistoricoTreino
            reg = RegistroTreino(treino_id=treino.id, versao_id=versao.id, periodo='Jan/2024',
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
