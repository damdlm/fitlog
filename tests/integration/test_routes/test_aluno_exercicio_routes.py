"""
Testes de regressão para routes/aluno/exercicio.py (CRUD de exercícios
customizados do aluno). Tinha 54% de cobertura.
"""
from datetime import datetime, timezone

from models import db, User, Musculo, ExercicioCustomizado, ExercicioSistema, Treino, RegistroTreino, HistoricoTreino
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


class TestListarExercicios:
    def test_lista_vazia(self, client, app):
        with app.app_context():
            _criar_usuario('ae_list_1')
        _login(client, 'ae_list_1')

        resp = client.get('/aluno/exercicios')
        assert resp.status_code == 200

    def test_lista_exercicio_customizado(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_list_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()

        _login(client, 'ae_list_2')
        resp = client.get('/aluno/exercicios')

        assert resp.status_code == 200
        assert 'Supino' in resp.get_data(as_text=True)

    def test_mostra_ultima_carga_registrada(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_list_3')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            from services.versao_service import VersaoService
            from datetime import date
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()

            reg = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='agosto/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=datetime.now(timezone.utc), user_id=u.id
            )
            db.session.add(reg)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=reg.id, carga=77.5, repeticoes=8, ordem=1))
            db.session.commit()

        _login(client, 'ae_list_3')
        resp = client.get('/aluno/exercicios')

        assert resp.status_code == 200
        assert '77.5' in resp.get_data(as_text=True) or '77,5' in resp.get_data(as_text=True)

    def test_nao_mistura_carga_de_exercicio_sistema_com_id_colidente(self, client, app):
        """
        A rota agrupa 'ultimas_cargas' por RegistroTreino.exercicio_id
        (hybrid property = COALESCE(exercicio_usuario_id, exercicio_base_id)),
        sem discriminar tipo. Se um ExercicioCustomizado e um
        ExercicioSistema tiverem o MESMO id numérico (sequências
        independentes -- perfeitamente possível), e ambos tiverem
        registros, o dict fica ambíguo: a última chave escrita "vence"
        para os dois, mesmo sendo exercícios diferentes.
        """
        with app.app_context():
            u = _criar_usuario('ae_colisao')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            from services.versao_service import VersaoService
            from datetime import date
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)

            ex_custom = ExercicioCustomizado(usuario_id=u.id, nome='Supino Custom', musculo_id=musc.id)
            db.session.add(ex_custom)
            db.session.commit()

            ex_sistema = ExercicioSistema(id_original='sis-colisao', nome='Agachamento Sistema', grupo_muscular='Pernas')
            db.session.add(ex_sistema)
            db.session.commit()

            # Força a colisão de ID manualmente via SQL bruto, já que as
            # duas tabelas têm sequências AUTOINCREMENT independentes e
            # normalmente não colidem no SQLite de teste (mas podem
            # colidir de verdade ao longo do tempo em produção).
            id_alvo = ex_custom.id
            db.session.execute(
                db.text("UPDATE exercicios_sistema SET id = :novo_id WHERE id = :id_atual"),
                {"novo_id": id_alvo, "id_atual": ex_sistema.id}
            )
            db.session.commit()

            reg_custom = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='agosto/2026', semana=1,
                exercicio_usuario_id=id_alvo, data_registro=datetime(2026, 1, 1, tzinfo=timezone.utc), user_id=u.id
            )
            db.session.add(reg_custom)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=reg_custom.id, carga=10, repeticoes=10, ordem=1))
            db.session.commit()

            reg_sistema = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='agosto/2026', semana=1,
                exercicio_base_id=id_alvo, data_registro=datetime(2026, 1, 2, tzinfo=timezone.utc), user_id=u.id
            )
            db.session.add(reg_sistema)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=reg_sistema.id, carga=999, repeticoes=1, ordem=1))
            db.session.commit()

        _login(client, 'ae_colisao')
        resp = client.get('/aluno/exercicios')
        body = resp.get_data(as_text=True)

        # Correto: 10.0 (carga do Supino Custom). Se aparecer 999.0 (carga
        # do exercício de sistema colidente), confirma o bug de agrupamento
        # sem discriminador de tipo -- corrigido em routes/aluno/exercicio.py.
        assert '999.0' not in body
        assert '10.0' in body

    def test_requer_login(self, client):
        resp = client.get('/aluno/exercicios')
        assert resp.status_code == 302


class TestNovoExercicio:
    def test_cria_exercicio_customizado(self, client, app):
        with app.app_context():
            _criar_usuario('ae_novo_1')
        _login(client, 'ae_novo_1')

        resp = client.post('/aluno/exercicio/novo', data={
            'nome': 'Supino Reto', 'musculo': 'Peito', 'descricao': 'd'
        })

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='ae_novo_1').first()
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id, nome='Supino Reto').first() is not None

    def test_sem_nome_nao_cria(self, client, app):
        with app.app_context():
            _criar_usuario('ae_novo_2')
        _login(client, 'ae_novo_2')

        resp = client.post('/aluno/exercicio/novo', data={'musculo': 'Peito'})

        assert resp.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='ae_novo_2').first()
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id).count() == 0


class TestEditarExercicio:
    def test_edita_exercicio_customizado(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_edit_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_edit_1')

        resp = client.post(f'/aluno/exercicio/{ex_id}', data={
            'nome': 'Supino Inclinado', 'musculo': 'Peito', 'descricao': ''
        })

        assert resp.status_code == 302
        with app.app_context():
            atualizado = db.session.get(ExercicioCustomizado, ex_id)
            assert atualizado.nome == 'Supino Inclinado'

    def test_exercicio_inexistente_redireciona(self, client, app):
        with app.app_context():
            _criar_usuario('ae_edit_2')
        _login(client, 'ae_edit_2')

        resp = client.get('/aluno/exercicio/999999')
        assert resp.status_code == 302

    def test_nao_edita_exercicio_de_outro_usuario(self, client, app):
        with app.app_context():
            a = _criar_usuario('ae_edit_a')
            b = _criar_usuario('ae_edit_b')
            musc = Musculo(nome=f'm_{b.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercicio do B', musculo_id=musc.id)
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'ae_edit_a')

        resp = client.post(f'/aluno/exercicio/{ex_b_id}', data={'nome': 'Hackeado', 'musculo': 'Peito'})
        assert resp.status_code == 302

        with app.app_context():
            ex_b_depois = db.session.get(ExercicioCustomizado, ex_b_id)
            assert ex_b_depois.nome == 'Exercicio do B'


class TestExcluirExercicio:
    def test_sem_confirmar_nao_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_excl_1')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_excl_1')

        resp = client.post(f'/aluno/exercicio/{ex_id}/excluir')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_id) is not None

    def test_confirmado_exclui(self, client, app):
        with app.app_context():
            u = _criar_usuario('ae_excl_2')
            musc = Musculo(nome=f'm_{u.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex = ExercicioCustomizado(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            ex_id = ex.id
        _login(client, 'ae_excl_2')

        resp = client.post(f'/aluno/exercicio/{ex_id}/excluir?confirmar=true')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_id) is None

    def test_nao_exclui_exercicio_de_outro_usuario(self, client, app):
        with app.app_context():
            a = _criar_usuario('ae_excl_a')
            b = _criar_usuario('ae_excl_b')
            musc = Musculo(nome=f'm_{b.id}', nome_exibicao='Peito')
            db.session.add(musc)
            db.session.commit()
            ex_b = ExercicioCustomizado(usuario_id=b.id, nome='Exercicio do B', musculo_id=musc.id)
            db.session.add(ex_b)
            db.session.commit()
            ex_b_id = ex_b.id
        _login(client, 'ae_excl_a')

        resp = client.post(f'/aluno/exercicio/{ex_b_id}/excluir?confirmar=true')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(ExercicioCustomizado, ex_b_id) is not None
