"""Testes de integração para routes/version_routes.py (blueprint 'version',
montado em /version)."""
from datetime import date

from models import db, User, VersaoGlobal, Treino, TreinoVersao, VersaoExercicio, ExercicioUsuario


def _criar_usuario(username):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario='aluno', nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _criar_versao(user_id, numero=1, data_inicio=date(2024, 1, 1), data_fim=None, divisao='ABC'):
    v = VersaoGlobal(numero_versao=numero, descricao=f'Versao {numero}', divisao=divisao,
                      data_inicio=data_inicio, data_fim=data_fim, user_id=user_id)
    db.session.add(v)
    db.session.commit()
    return v


def _criar_treino(user_id, codigo='A'):
    t = Treino(codigo=codigo, nome=f'Treino {codigo}', descricao='d', user_id=user_id)
    db.session.add(t)
    db.session.commit()
    return t


def _criar_treino_versao(versao_id, treino_id, nome='Treino A'):
    tv = TreinoVersao(versao_id=versao_id, treino_id=treino_id, nome_treino=nome,
                       descricao_treino='desc')
    db.session.add(tv)
    db.session.commit()
    return tv


def _criar_exercicio(user_id, nome='Supino'):
    ex = ExercicioUsuario(usuario_id=user_id, nome=nome)
    db.session.add(ex)
    db.session.commit()
    return ex


class TestGerenciarVersoesGlobal:
    def test_requer_login(self, client):
        resp = client.get('/version/gerenciar-versoes')
        assert resp.status_code == 302
        assert '/auth/login' in resp.location

    def test_lista_versoes_do_usuario(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_gerenciar_1')
            _criar_versao(u.id, numero=1)
            username = u.username

        _login(client, username)
        resp = client.get('/version/gerenciar-versoes')
        assert resp.status_code == 200
        assert b'Versao 1' in resp.data


class TestSalvarVersaoGlobal:
    def test_cria_versao_com_sucesso(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_salvar_1').username

        _login(client, username)
        resp = client.post('/version/salvar/versao', data={
            'descricao': 'Minha versao', 'divisao': 'ABC', 'data_inicio': '2024-01-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            versoes = VersaoGlobal.query.filter_by(user_id=u.id).all()
            assert len(versoes) == 1
            assert versoes[0].descricao == 'Minha versao'

    def test_bloqueia_criar_nova_se_ja_existe_ativa(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_salvar_2')
            _criar_versao(u.id, numero=1)  # sem data_fim -- ativa
            username = u.username

        _login(client, username)
        resp = client.post('/version/salvar/versao', data={
            'descricao': 'Outra versao', 'divisao': 'ABC', 'data_inicio': '2024-02-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 1

    def test_permite_criar_ja_finalizada_mesmo_com_ativa_existente(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_salvar_3')
            _criar_versao(u.id, numero=1)  # ativa
            username = u.username

        _login(client, username)
        resp = client.post('/version/salvar/versao', data={
            'descricao': 'Versao ja finalizada', 'divisao': 'ABC',
            'data_inicio': '2023-01-01', 'data_fim': '2023-06-01'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 2


class TestVerVersao:
    def test_requer_login(self, client):
        resp = client.get('/version/ver/1')
        assert resp.status_code == 302

    def test_404_para_versao_inexistente(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_ver_1').username

        _login(client, username)
        resp = client.get('/version/ver/99999', follow_redirects=True)
        assert resp.status_code == 200

    def test_isolamento_entre_usuarios(self, client, app):
        with app.app_context():
            dono = _criar_usuario('vr_ver_dono')
            outro = _criar_usuario('vr_ver_outro')
            versao = _criar_versao(dono.id)
            versao_id, outro_username = versao.id, outro.username

        _login(client, outro_username)
        resp = client.get(f'/version/ver/{versao_id}', follow_redirects=True)
        assert resp.status_code == 200
        assert 'n\u00e3o encontrada'.encode() in resp.data

    def test_get_exibe_versao(self, client, app):
        """
        Bug corrigido: a rota renderizava "version/ver_versao.html", mas
        esse arquivo não existia em templates/version/ (foi removido num
        refactor anterior; o equivalente hoje é templates/aluno/ver_versao.html,
        de outro blueprint). Criado um template consistente com o estilo
        dos demais em templates/version/.
        """
        with app.app_context():
            u = _criar_usuario('vr_ver_2')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.get(f'/version/ver/{versao_id}')
        assert resp.status_code == 200
        assert versao.descricao.encode() in resp.data

    def test_post_atualiza_versao(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_ver_3')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/ver/{versao_id}', data={
            'descricao': 'Descricao atualizada', 'divisao': 'ABCD',
            'data_inicio': '2024-01-15'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.descricao == 'Descricao atualizada'
            assert v.divisao == 'ABCD'


class TestFinalizarVersaoGlobal:
    def test_finaliza_versao_ativa(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_finalizar_1')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/finalizar/{versao_id}', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.data_fim is not None

    def test_nao_finaliza_versao_ja_finalizada(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_finalizar_2')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username, data_fim_original = versao.id, u.username, versao.data_fim

        _login(client, username)
        client.post(f'/version/finalizar/{versao_id}', follow_redirects=True)

        with app.app_context():
            v = db.session.get(VersaoGlobal, versao_id)
            assert v.data_fim == data_fim_original

    def test_404_para_versao_inexistente(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_finalizar_3').username

        _login(client, username)
        resp = client.post('/version/finalizar/99999', follow_redirects=True)
        assert resp.status_code == 200


class TestClonarVersaoGlobal:
    def test_clona_versao_com_sucesso(self, client, app):
        """
        Bug corrigido: dentro de clone(versao_id, user_id=None), o
        parâmetro user_id nunca era reatribuído a partir de
        BaseService.get_current_user_id() -- diferente de outros métodos
        do serviço, como get_by_id/get_ativa. Quando a rota chamava
        clone(versao_id) sem passar user_id, ele ficava None até a
        construção de `VersaoGlobal(..., user_id=user_id)`, violando a
        constraint NOT NULL e sempre revertendo com False. Corrigido
        resolvendo user_id no início do método, no mesmo padrão dos
        demais.
        """
        with app.app_context():
            u = _criar_usuario('vr_clonar_1')
            versao = _criar_versao(u.id, numero=1, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/clonar/{versao_id}', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 2

    def test_falha_se_ja_existe_versao_ativa(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_clonar_2')
            versao = _criar_versao(u.id, numero=1)  # ativa
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/clonar/{versao_id}', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            assert VersaoGlobal.query.filter_by(user_id=u.id).count() == 1


class TestApiCriarTreino:
    def test_cria_treino_com_sucesso(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_apicriar_1').username

        _login(client, username)
        resp = client.post('/version/api/criar-treino', json={
            'id': 'a', 'nome': 'Treino A', 'descricao': 'desc'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['codigo'] == 'A'

    def test_falha_sem_id_ou_nome(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_apicriar_2').username

        _login(client, username)
        resp = client.post('/version/api/criar-treino', json={'id': '', 'nome': ''})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_falha_treino_ja_existe(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_apicriar_3')
            _criar_treino(u.id, codigo='A')
            username = u.username

        _login(client, username)
        resp = client.post('/version/api/criar-treino', json={'id': 'a', 'nome': 'Outro nome'})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False


class TestSalvarExercicioGlobal:
    def test_cria_exercicio_com_sucesso(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_salvarex_1').username

        _login(client, username)
        resp = client.post('/version/salvar-exercicio-global', data={
            'nome': 'Supino Reto', 'musculo': 'Peito'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            ex = ExercicioUsuario.query.filter_by(usuario_id=u.id, nome='Supino Reto').first()
            assert ex is not None

    def test_falha_sem_nome(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_salvarex_2').username

        _login(client, username)
        resp = client.post('/version/salvar-exercicio-global', data={'nome': ''},
                            follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            assert ExercicioUsuario.query.filter_by(usuario_id=u.id).count() == 0


class TestNovoTreinoNaVersao:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_novotreino_1')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.get(f'/version/versao/{versao_id}/novo-treino')
        assert resp.status_code == 200

    def test_bloqueia_se_versao_arquivada(self, client, app):
        """Bloqueio funciona (redireciona) -- não segue o redirect porque
        o destino (version.ver_versao) tem um bug de template ausente
        (ver TestVerVersao.test_get_falha_bug_conhecido_template_ausente)."""
        with app.app_context():
            u = _criar_usuario('vr_novotreino_2')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.get(f'/version/versao/{versao_id}/novo-treino', follow_redirects=False)
        assert resp.status_code == 302
        assert f'/version/ver/{versao_id}' in resp.location

    def test_post_adiciona_treino_com_sucesso(self, client, app):
        """
        Bug corrigido: a rota chamava VersaoService.adicionar_treino(...)
        com 5 argumentos posicionais, mas a assinatura do serviço exige
        também 'bases_ids'. Isso lançava TypeError sempre. Corrigido
        passando bases_ids=[] explicitamente na chamada.

        NOTA: esta rota espera que o Treino já exista (criado antes via
        o endpoint AJAX /version/api/criar-treino, usado pelo frontend
        antes de submeter este formulário) -- ela só vincula um Treino
        já existente à versão, não cria um do zero.
        """
        with app.app_context():
            u = _criar_usuario('vr_novotreino_3')
            versao = _criar_versao(u.id)
            _criar_treino(u.id, codigo='A')
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/novo-treino', data={
            'treino_id': 'A', 'nome_treino': 'Treino A',
            'descricao_treino': 'desc', 'tipo_criacao': 'vazio'
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert f'/version/ver/{versao_id}' in resp.location

        with app.app_context():
            u = User.query.filter_by(username=username).first()
            treino = Treino.query.filter_by(codigo='A', user_id=u.id).first()
            assert treino is not None
            tv = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
            assert tv is not None

    def test_post_falha_se_treino_nao_foi_criado_antes(self, client, app):
        """Sem o Treino pré-criado (via /version/api/criar-treino), a
        rota não encontra o código e não vincula nada."""
        with app.app_context():
            u = _criar_usuario('vr_novotreino_4')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/novo-treino', data={
            'treino_id': 'A', 'nome_treino': 'Treino A',
            'descricao_treino': 'desc', 'tipo_criacao': 'vazio'
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            assert TreinoVersao.query.filter_by(versao_id=versao_id).count() == 0


class TestEditarTreinoNaVersao:
    def test_get_exibe_formulario(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_editar_1')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            _criar_treino_versao(versao.id, treino.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.get(f'/version/versao/{versao_id}/treino/A/editar')
        assert resp.status_code == 200

    def test_bloqueia_se_versao_arquivada(self, client, app):
        """Não segue o redirect -- destino tem o bug de template ausente
        documentado em TestVerVersao."""
        with app.app_context():
            u = _criar_usuario('vr_editar_2')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.get(f'/version/versao/{versao_id}/treino/A/editar', follow_redirects=False)
        assert resp.status_code == 302
        assert f'/version/ver/{versao_id}' in resp.location

    def test_post_atualiza_treino_e_exercicios(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_editar_3')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(u.id)
            versao_id, tv_id, ex_id, username = versao.id, tv.id, ex.id, u.username

        _login(client, username)
        # Não segue o redirect (sucesso também aponta para version.ver_versao,
        # que tem o bug de template ausente) -- a escrita já aconteceu antes
        # do redirect, então validamos o resultado direto no banco.
        resp = client.post(f'/version/versao/{versao_id}/treino/A/editar', data={
            'nome_treino': 'Treino A Editado',
            'descricao_treino': 'nova desc',
            'exercicios[]': [f'u_{ex_id}'],
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert f'/version/ver/{versao_id}' in resp.location

        with app.app_context():
            tv_atualizado = db.session.get(TreinoVersao, tv_id)
            assert tv_atualizado.nome_treino == 'Treino A Editado'
            assert len(tv_atualizado.exercicios) == 1

    def test_post_falha_sem_exercicios_selecionados(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_editar_4')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            _criar_treino_versao(versao.id, treino.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/editar', data={
            'nome_treino': 'Treino A', 'descricao_treino': 'd',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_post_ignora_exercicio_de_outro_usuario_idor(self, client, app):
        """Exercício customizado de outro usuário não pode ser referenciado
        (hardening de segurança citado no comentário da rota). Não segue o
        redirect (sucesso também aponta para version.ver_versao, que tem o
        bug de template ausente)."""
        with app.app_context():
            dono = _criar_usuario('vr_editar_idor_dono')
            u = _criar_usuario('vr_editar_idor_5')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex_de_outro = _criar_exercicio(dono.id)
            versao_id, tv_id, ex_id, username = versao.id, tv.id, ex_de_outro.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/editar', data={
            'nome_treino': 'Treino A', 'descricao_treino': 'd',
            'exercicios[]': [f'u_{ex_id}'],
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            tv_atualizado = db.session.get(TreinoVersao, tv_id)
            # O exercício alheio foi filtrado -- nenhum foi adicionado.
            assert len(tv_atualizado.exercicios) == 0


class TestExcluirTreinoDaVersao:
    def test_remove_treino_da_versao(self, client, app):
        """Não segue o redirect (sempre aponta para version.ver_versao, que
        tem o bug de template ausente -- ver TestVerVersao)."""
        with app.app_context():
            u = _criar_usuario('vr_excluirtreino_1')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            versao_id, tv_id, username = versao.id, tv.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/excluir', follow_redirects=False)
        assert resp.status_code == 302
        assert f'/version/ver/{versao_id}' in resp.location

        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is None

    def test_bloqueia_se_versao_arquivada(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_excluirtreino_2')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            versao_id, tv_id, username = versao.id, tv.id, u.username

        _login(client, username)
        client.post(f'/version/versao/{versao_id}/treino/A/excluir', follow_redirects=False)

        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id) is not None


class TestReordenarExercicios:
    def test_reordena_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_reordenar_1')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex1 = _criar_exercicio(u.id, nome='Ex1')
            ex2 = _criar_exercicio(u.id, nome='Ex2')
            ve1 = VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex1.id, ordem=0)
            ve2 = VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex2.id, ordem=1)
            db.session.add_all([ve1, ve2])
            db.session.commit()
            versao_id, ex1_id, ex2_id, username = versao.id, ex1.id, ex2.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/reordenar', json={
            'nova_ordem': [ex2_id, ex1_id]
        })
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            ex2_reload = VersaoExercicio.query.filter_by(exercicio_usuario_id=ex2_id).first()
            ex1_reload = VersaoExercicio.query.filter_by(exercicio_usuario_id=ex1_id).first()
            assert ex2_reload.ordem == 0
            assert ex1_reload.ordem == 1

    def test_404_versao_inexistente(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_reordenar_2').username

        _login(client, username)
        resp = client.post('/version/versao/99999/treino/A/reordenar', json={'nova_ordem': []})
        assert resp.status_code == 404

    def test_403_versao_arquivada(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_reordenar_3')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/reordenar', json={'nova_ordem': []})
        assert resp.status_code == 403


class TestAdicionarExercicioNaVersao:
    def test_adiciona_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_addex_1')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(u.id)
            versao_id, ex_id, username = versao.id, ex.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/exercicio/adicionar', json={
            'exercicio_id': ex_id
        })
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            assert VersaoExercicio.query.filter_by(exercicio_usuario_id=ex_id).count() == 1

    def test_falha_sem_exercicio_id(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_addex_2')
            versao = _criar_versao(u.id)
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/exercicio/adicionar', json={})
        assert resp.status_code == 400

    def test_nao_duplica_exercicio_ja_existente(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_addex_3')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(u.id)
            ve = VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0)
            db.session.add(ve)
            db.session.commit()
            versao_id, ex_id, username = versao.id, ex.id, u.username

        _login(client, username)
        resp = client.post(f'/version/versao/{versao_id}/treino/A/exercicio/adicionar', json={
            'exercicio_id': ex_id
        })
        assert resp.status_code == 200

        with app.app_context():
            assert VersaoExercicio.query.filter_by(exercicio_usuario_id=ex_id).count() == 1


class TestRemoverExercicioDaVersao:
    def test_remove_com_sucesso(self, client, app):
        """
        Bug corrigido: `exercicio_id` em VersaoExercicio era uma @property
        Python comum, sem expressão SQL, então filter_by(exercicio_id=...)
        nunca casava com nada no banco e a remoção nunca acontecia (sempre
        404). Corrigido transformando exercicio_id numa hybrid_property
        com expressão SQL equivalente (coalesce de exercicio_usuario_id e
        exercicio_base_id), que agora funciona tanto em acesso Python
        quanto em filtros de query.
        """
        with app.app_context():
            u = _criar_usuario('vr_removeex_1')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            tv = _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(u.id)
            ve = VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0)
            db.session.add(ve)
            db.session.commit()
            versao_id, ex_id, username = versao.id, ex.id, u.username

        _login(client, username)
        resp = client.post(
            f'/version/versao/{versao_id}/treino/A/exercicio/{ex_id}/remover')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            assert VersaoExercicio.query.filter_by(exercicio_usuario_id=ex_id).count() == 0

    def test_404_para_exercicio_nao_associado(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_removeex_2')
            versao = _criar_versao(u.id)
            treino = _criar_treino(u.id)
            _criar_treino_versao(versao.id, treino.id)
            ex = _criar_exercicio(u.id)
            versao_id, ex_id, username = versao.id, ex.id, u.username

        _login(client, username)
        resp = client.post(
            f'/version/versao/{versao_id}/treino/A/exercicio/{ex_id}/remover')
        assert resp.status_code == 404
        assert resp.get_json()['success'] is False


class TestExcluirVersaoGlobal:
    def test_pede_confirmacao_antes_de_excluir(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_excluirversao_1')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/excluir/{versao_id}', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_exclui_com_confirmacao(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_excluirversao_2')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/excluir/{versao_id}?confirmar=true', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is None

    def test_nao_exclui_versao_ativa(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_excluirversao_3')
            versao = _criar_versao(u.id)  # ativa (sem data_fim)
            versao_id, username = versao.id, u.username

        _login(client, username)
        client.post(f'/version/excluir/{versao_id}?confirmar=true', follow_redirects=True)

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_nao_exclui_versao_com_registros_vinculados(self, client, app):
        with app.app_context():
            u = _criar_usuario('vr_excluirversao_4')
            versao = _criar_versao(u.id, data_fim=date(2024, 6, 1))
            treino = _criar_treino(u.id)
            ex = _criar_exercicio(u.id)
            from models import RegistroTreino
            reg = RegistroTreino(treino_id=treino.id, versao_id=versao.id, periodo='Jan/2024',
                                  semana=1, exercicio_usuario_id=ex.id,
                                  data_registro=date(2024, 1, 10), user_id=u.id)
            db.session.add(reg)
            db.session.commit()
            versao_id, username = versao.id, u.username

        _login(client, username)
        resp = client.post(f'/version/excluir/{versao_id}?confirmar=true', follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id) is not None

    def test_404_versao_inexistente(self, client, app):
        with app.app_context():
            username = _criar_usuario('vr_excluirversao_5').username

        _login(client, username)
        resp = client.post('/version/excluir/99999?confirmar=true', follow_redirects=True)
        assert resp.status_code == 200
