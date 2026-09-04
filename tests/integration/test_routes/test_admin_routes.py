"""
Testes de regressão para routes/admin_routes.py.

Cobre principalmente admin.editar_exercicio, que tinha um bug real
encontrado na Fase 5: a rota sempre respondia com redirect() (HTML),
mas o JS de templates/admin/gerenciar_treinos.html chama a rota via
fetch() e faz response.json() -- ou seja, a edição de exercício pelo
modal parecia "não fazer nada" (o parse de JSON falhava silenciosamente
no browser). A correção faz a rota responder com JSON quando a chamada
vem via AJAX (header X-Requested-With, que o próprio JS já envia),
preservando redirect+flash para qualquer outro chamador.
"""
from models import db, User, ExercicioCustomizado, ExercicioUsuario, Musculo


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


HEADERS_AJAX = {'X-Requested-With': 'XMLHttpRequest'}


class TestEditarExercicioAjax:
    """A chamada real do template é sempre via fetch() -- deve responder JSON."""

    def test_edicao_bem_sucedida_retorna_json(self, client, app):
        with app.app_context():
            u = _criar_usuario('user_edit_ok')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_ok')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Reto',
                                  'musculo': 'Peito', 'descricao': ''},
                            headers=HEADERS_AJAX)

        assert resp.content_type == 'application/json'
        data = resp.get_json()
        assert data['success'] is True

        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Reto'

    def test_edicao_exercicio_usuario_base_retorna_json(self, client, app):
        """Personalização de exercício do catálogo (ExercicioUsuario), não custom."""
        with app.app_context():
            u = _criar_usuario('user_edit_base')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino base', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_base')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Personalizado',
                                  'musculo': 'Peito', 'descricao': 'nova descrição'},
                            headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is True
        with app.app_context():
            atualizado = db.session.get(ExercicioUsuario, ex_id)
            assert atualizado.nome == 'Supino Personalizado'

    def test_exercicio_inexistente_retorna_success_false_sem_500(self, client, app):
        with app.app_context():
            _criar_usuario('user_edit_404')
        _login(client, 'user_edit_404')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': '999999', 'nome': 'Fantasma'},
                            headers=HEADERS_AJAX)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False

    def test_dados_invalidos_retorna_success_false(self, client, app):
        with app.app_context():
            _criar_usuario('user_edit_invalido')
        _login(client, 'user_edit_invalido')

        resp = client.post('/admin/editar/exercicio', data={'id': ''}, headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is False

    def test_nao_edita_exercicio_de_outro_usuario(self, client, app):
        """IDOR: usuário A não deve conseguir editar exercício de B via essa rota."""
        with app.app_context():
            a = _criar_usuario('user_edit_a')
            b = _criar_usuario('user_edit_b')
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercício do B')
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'user_edit_a')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_b_id), 'nome': 'Hackeado'},
                            headers=HEADERS_AJAX)

        assert resp.get_json()['success'] is False
        with app.app_context():
            ex_b_depois = db.session.get(ExercicioCustomizado, ex_b_id)
            assert ex_b_depois.nome == 'Exercício do B'


class TestEditarExercicioSemAjax:
    """Sem o header X-Requested-With, mantém o comportamento antigo (redirect)."""

    def test_sem_header_ajax_faz_redirect(self, client, app):
        with app.app_context():
            u = _criar_usuario('user_edit_form')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_edit_form')

        resp = client.post('/admin/editar/exercicio',
                            data={'id': str(ex_id), 'nome': 'Supino Inclinado'})

        assert resp.status_code == 302
        assert '/admin/gerenciar' in resp.headers['Location']

        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Inclinado'


class TestEditarExercicioRequerLogin:
    def test_requer_autenticacao(self, client):
        resp = client.post('/admin/editar/exercicio', data={'id': '1', 'nome': 'x'})
        assert resp.status_code in (302, 401)


class TestExercicioDetalhes:
    """
    Bug corrigido: a rota renderizava "admin/exercicio_detalhes.html"
    (singular), mas o arquivo no disco é
    templates/admin/exercicios_detalhes.html (plural, com 's'). Toda
    visita a /admin/exercicio/detalhes/<id> sempre lançava
    TemplateNotFound. Corrigido ajustando o nome do template na chamada
    de render_template para bater com o arquivo real.
    """

    def test_exibe_detalhes_de_exercicio_do_usuario(self, client, app):
        with app.app_context():
            u = _criar_usuario('user_detalhes_1', tipo_usuario='aluno')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino Reto')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'user_detalhes_1')

        resp = client.get(f'/admin/exercicio/detalhes/{ex_id}')
        assert resp.status_code == 200
        assert 'Supino Reto'.encode() in resp.data

    def test_exibe_detalhes_de_exercicio_do_sistema(self, client, app):
        from models import ExercicioSistema
        with app.app_context():
            u = _criar_usuario('user_detalhes_2', tipo_usuario='aluno')
            ex_sistema = ExercicioSistema(id_original='9999', nome='Agachamento Livre',
                                           grupo_muscular='Quadríceps')
            db.session.add(ex_sistema)
            db.session.commit()
            ex_id = ex_sistema.id
        _login(client, 'user_detalhes_2')

        resp = client.get(f'/admin/exercicio/detalhes/{ex_id}')
        assert resp.status_code == 200

    def test_redireciona_se_exercicio_nao_encontrado(self, client, app):
        """
        Bug corrigido: faltava `exercicio = None` antes do bloco de
        busca, então quando o exercício não existia em nenhuma das duas
        tabelas, `if not exercicio:` lançava UnboundLocalError em vez de
        mostrar a mensagem de "não encontrado" e redirecionar.
        """
        with app.app_context():
            _criar_usuario('user_detalhes_3', tipo_usuario='aluno')
        _login(client, 'user_detalhes_3')

        resp = client.get('/admin/exercicio/detalhes/99999', follow_redirects=True)
        assert resp.status_code == 200

    def test_requer_login(self, client):
        resp = client.get('/admin/exercicio/detalhes/1')
        assert resp.status_code in (302, 401)


class TestTelasControladas:
    """/admin/telas-controladas -- admin escolhe quais telas exigem
    plano pago (ver services/tela_controlada_service.py)."""

    def _criar_admin(self, app, username='admin_telas'):
        u = _criar_usuario(username, tipo_usuario='admin')
        with app.app_context():
            from models import User
            User.query.filter_by(id=u.id).update({'is_admin': True})
            db.session.commit()
        return u

    def test_requer_admin(self, client, app):
        with app.app_context():
            _criar_usuario('aluno_sem_permissao')
        _login(client, 'aluno_sem_permissao')

        resp = client.get('/admin/telas-controladas')
        assert resp.status_code in (302, 403)

    def test_get_lista_as_telas_seedadas(self, client, app):
        self._criar_admin(app)
        _login(client, 'admin_telas')

        resp = client.get('/admin/telas-controladas')
        assert resp.status_code == 200
        corpo = resp.get_data(as_text=True)
        assert 'Estatísticas' in corpo
        assert 'FitBot' in corpo
        assert 'Calendário' in corpo

    def test_post_atualiza_quais_telas_bloqueiam(self, client, app):
        from models import TelaControlada
        self._criar_admin(app)
        _login(client, 'admin_telas')

        resp = client.post('/admin/telas-controladas', data={
            'bloqueia': ['fitbot', 'calendario'],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            bloqueadas = {t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=True).all()}
            assert bloqueadas == {'fitbot', 'calendario'}
            # estatisticas e tabela_progresso não vieram marcadas no
            # form -- devem ter sido desbloqueadas.
            assert TelaControlada.query.filter_by(chave='estatisticas').first().bloqueia_sem_plano is False

    def test_post_sem_nenhuma_marcada_libera_todas(self, client, app):
        from models import TelaControlada
        self._criar_admin(app)
        _login(client, 'admin_telas')

        resp = client.post('/admin/telas-controladas', data={}, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert all(not t.bloqueia_sem_plano for t in TelaControlada.query.all())


class TestGerenciar:
    """/admin/gerenciar -- acessível a qualquer usuário logado, cada
    um vendo só os próprios dados (treinos, exercícios, últimas
    cargas). Cobre os ramos que dependem de ter versão ativa e
    registros de treino, que os testes de editar/excluir não tocam."""

    def test_carrega_vazio_sem_nenhum_dado(self, client, app):
        with app.app_context():
            _criar_usuario('ger_vazio')
        _login(client, 'ger_vazio')

        resp = client.get('/admin/gerenciar')
        assert resp.status_code == 200

    def test_carrega_com_versao_ativa_treino_e_ultima_carga(self, client, app):
        from datetime import date, datetime, timezone
        from models import VersaoGlobal, TreinoVersao, VersaoExercicio, RegistroTreino, HistoricoTreino

        with app.app_context():
            u = _criar_usuario('ger_com_dados')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino Ger')
            db.session.add(ex)
            db.session.commit()

            versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                                   data_inicio=date.today(), user_id=u.id)
            db.session.add(versao)
            db.session.commit()
            tv = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A')
            db.session.add(tv)
            db.session.commit()
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.commit()

            registro = RegistroTreino(
                treino_versao_id=tv.id, versao_id=versao.id, periodo='2026-09',
                semana=1, data_registro=datetime.now(timezone.utc),
                user_id=u.id, exercicio_usuario_id=ex.id,
            )
            db.session.add(registro)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=registro.id, carga=42.5, repeticoes=10, ordem=1))
            db.session.commit()

        _login(client, 'ger_com_dados')
        resp = client.get('/admin/gerenciar')
        assert resp.status_code == 200
        assert b'Supino Ger' in resp.data


class TestSalvarExercicio:

    def test_cria_com_sucesso(self, client, app):
        with app.app_context():
            _criar_usuario('salvar_ex_1')
        _login(client, 'salvar_ex_1')

        resp = client.post('/admin/salvar/exercicio', data={
            'nome': 'Rosca Concentrada', 'musculo': 'Bíceps', 'descricao': 'teste',
        }, follow_redirects=True)

        assert resp.status_code == 200
        with app.app_context():
            assert ExercicioCustomizado.query.filter_by(nome='Rosca Concentrada').first() is not None

    def test_sem_nome_nao_cria_e_avisa(self, client, app):
        with app.app_context():
            _criar_usuario('salvar_ex_2')
        _login(client, 'salvar_ex_2')

        resp = client.post('/admin/salvar/exercicio', data={'musculo': 'Peito'}, follow_redirects=True)

        assert resp.status_code == 200
        with app.app_context():
            assert ExercicioCustomizado.query.count() == 0

    def test_musculo_nao_informado_e_auto_detectado(self, client, app):
        from models import ExercicioSistema
        with app.app_context():
            _criar_usuario('salvar_ex_3')
            db.session.add(ExercicioSistema(id_original='sys-salvar', nome='Supino Reto Auto', grupo_muscular='Peito'))
            db.session.commit()
        _login(client, 'salvar_ex_3')

        client.post('/admin/salvar/exercicio', data={'nome': 'Supino Reto Auto'}, follow_redirects=True)

        with app.app_context():
            criado = ExercicioCustomizado.query.filter_by(nome='Supino Reto Auto').first()
            assert criado is not None
            assert criado.musculo_ref.nome_exibicao == 'Peito'


class TestEditarExercicioUsuario:
    """ACHADO ao escrever este teste: como ExercicioCustomizado é
    literalmente um alias de ExercicioUsuario (`ExercicioCustomizado =
    ExercicioUsuario`, ver models.py), a query de
    ExercicioCustomizado.query.filter_by(id=...) na linha 199 SEMPRE
    encontra o registro primeiro -- é a mesma tabela. O bloco
    `if exercicio_usuario:` (linhas 220-236) que deveria ser um
    segundo caminho nunca executa de verdade. Não é um bug funcional
    (o primeiro bloco já faz exatamente a mesma coisa certa), só
    código morto inofensivo -- documentando aqui em vez de fingir que
    o segundo bloco é exercitado."""

    def test_edita_exercicio_usuario_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('editar_exu_1')
            ex = ExercicioUsuario(usuario_id=u.id, nome='Original')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'editar_exu_1')

        resp = client.post('/admin/editar/exercicio', data={
            'id': str(ex_id), 'nome': 'Editado', 'musculo': 'Costas', 'descricao': 'x',
        }, headers=HEADERS_AJAX)

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        with app.app_context():
            assert db.session.get(ExercicioUsuario, ex_id).nome == 'Editado'


class TestExcluirExercicio:

    def test_exclui_exercicio_customizado_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('excluir_ex_1')
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Pode excluir')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'excluir_ex_1')

        resp = client.post(f'/admin/excluir/exercicio/{ex_id}', follow_redirects=True)

        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_id) is None

    def test_exclui_exercicio_usuario_com_sucesso(self, client, app):
        """Cobre o segundo `try` -- quando não é ExercicioCustomizado,
        cai pra delete_exercicio_usuario."""
        with app.app_context():
            u = _criar_usuario('excluir_ex_2')
            ex = ExercicioUsuario(usuario_id=u.id, nome='Pode excluir tambem')
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'excluir_ex_2')

        resp = client.post(f'/admin/excluir/exercicio/{ex_id}', follow_redirects=True)

        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(ExercicioUsuario, ex_id) is None

    def test_exercicio_inexistente_avisa_sem_quebrar(self, client, app):
        with app.app_context():
            _criar_usuario('excluir_ex_3')
        _login(client, 'excluir_ex_3')

        resp = client.post('/admin/excluir/exercicio/999999', follow_redirects=True)
        assert resp.status_code == 200


class TestContas:

    def _criar_admin(self, app, username='admin_contas'):
        u = _criar_usuario(username, tipo_usuario='admin')
        with app.app_context():
            from models import User
            User.query.filter_by(id=u.id).update({'is_admin': True})
            db.session.commit()
        return u

    def test_requer_admin(self, client, app):
        with app.app_context():
            _criar_usuario('aluno_sem_permissao_contas')
        _login(client, 'aluno_sem_permissao_contas')

        resp = client.get('/admin/contas')
        assert resp.status_code in (302, 403)

    def test_lista_carrega_para_admin(self, client, app):
        self._criar_admin(app)
        _login(client, 'admin_contas')

        resp = client.get('/admin/contas')
        assert resp.status_code == 200

    def test_filtros_por_query_string_nao_quebram(self, client, app):
        self._criar_admin(app, 'admin_contas2')
        _login(client, 'admin_contas2')

        resp = client.get('/admin/contas?tipo=aluno&situacao=inadimplente&busca=x&plano=fit')
        assert resp.status_code == 200


class TestMonitoramento:

    def _criar_admin(self, app, username='admin_monitor'):
        u = _criar_usuario(username, tipo_usuario='admin')
        with app.app_context():
            from models import User
            User.query.filter_by(id=u.id).update({'is_admin': True})
            db.session.commit()
        return u

    def test_requer_admin(self, client, app):
        with app.app_context():
            _criar_usuario('aluno_sem_permissao_monitor')
        _login(client, 'aluno_sem_permissao_monitor')

        resp = client.get('/admin/monitoramento')
        assert resp.status_code in (302, 403)

    def test_pagina_carrega_para_admin(self, client, app):
        self._criar_admin(app)
        _login(client, 'admin_monitor')

        resp = client.get('/admin/monitoramento')
        assert resp.status_code == 200

    def test_api_retorna_json_com_as_quatro_fontes(self, client, app):
        self._criar_admin(app, 'admin_monitor2')
        _login(client, 'admin_monitor2')

        resp = client.get('/admin/api/monitoramento')
        assert resp.status_code == 200
        dados = resp.get_json()
        assert set(dados.keys()) == {'coletado_em', 'processo', 'banco', 'cache', 'negocio'}
