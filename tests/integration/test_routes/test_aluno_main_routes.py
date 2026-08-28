"""
Testes de regressão para routes/aluno/main.py (dashboard + fluxo de
vínculo aluno-professor). Tinha 23% de cobertura -- é a página inicial
de qualquer aluno logado.
"""
from datetime import datetime, timezone, timedelta
from models import db, User, AlunoProfessor, SolicitacaoVinculo, TreinoVersao, \
    VersaoGlobal, RegistroTreino, HistoricoTreino, Musculo, ExercicioUsuario


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
            versao = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                                   data_inicio=datetime.now(timezone.utc).date(), user_id=u.id)
            db.session.add(versao)
            db.session.commit()
            db.session.add(TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A', descricao_treino='d'))
            db.session.add(TreinoVersao(versao_id=versao.id, codigo='B', nome_treino='Treino B', descricao_treino='d'))
            db.session.commit()
        _login(client, 'am_dash_2')

        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 200
        # 2 treinos criados devem refletir na página (contagem exibida)
        assert b'2' in resp.data

    def test_tempo_ultimo_treino_pega_a_sessao_mais_recente_no_mesmo_dia(self, client, app):
        """Regressão: data_registro só guarda o DIA (sem hora), então duas
        sessões diferentes registradas no mesmo dia empatavam nesse
        critério de ordenação. Sem um desempate (created_at), o dashboard
        podia mostrar o tempo de uma sessão antiga em vez da última salva
        de fato."""
        with app.app_context():
            u = _criar_usuario('am_dash_tempo')

            m = Musculo(nome='peito_am_dash', nome_exibicao='Peito')
            db.session.add(m)
            db.session.commit()

            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=m.id)
            db.session.add(ex)
            db.session.commit()

            versao = VersaoGlobal(
                numero_versao=1, descricao='v1', divisao='A',
                data_inicio=datetime.now(timezone.utc).date(),
                user_id=u.id
            )
            db.session.add(versao)
            db.session.commit()

            treino_a = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A', descricao_treino='d')
            treino_b = TreinoVersao(versao_id=versao.id, codigo='B', nome_treino='Treino B', descricao_treino='d')
            db.session.add_all([treino_a, treino_b])
            db.session.commit()

            hoje = datetime.now(timezone.utc).date()
            agora = datetime.now(timezone.utc)

            # A sessão MAIS RECENTE (created_at mais novo) é inserida
            # PRIMEIRO no banco (rowid menor) -- de propósito, pra
            # diferenciar do bug antigo. Sem um ORDER BY com desempate
            # explícito, o SQLite tende a devolver linhas empatadas em
            # data_registro na ordem física (rowid) por padrão, o que
            # bateria com a ordem de inserção abaixo e mascararia o bug
            # se a sessão "certa" também fosse a inserida por último.
            r_recente = RegistroTreino(
                treino_versao_id=treino_b.id, versao_id=versao.id, periodo='Julho/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=hoje, user_id=u.id,
                created_at=agora
            )
            db.session.add(r_recente)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=r_recente.id, carga=60, repeticoes=8, tempo_treino=2700))
            db.session.commit()

            # Sessão mais ANTIGA (created_at 2h atrás), inserida DEPOIS
            # (rowid maior) -- mesmo dia. Tempo de treino de 10 minutos.
            r_antiga = RegistroTreino(
                treino_versao_id=treino_a.id, versao_id=versao.id, periodo='Julho/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=hoje, user_id=u.id,
                created_at=agora - timedelta(hours=2)
            )
            db.session.add(r_antiga)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=r_antiga.id, carga=50, repeticoes=10, tempo_treino=600))
            db.session.commit()

        _login(client, 'am_dash_tempo')
        resp = client.get('/aluno/dashboard')
        assert resp.status_code == 200
        # 2700s = 00:45 -- deve mostrar o tempo da sessão mais recente
        assert b'00:45' in resp.data
        # Não deve mostrar o tempo da sessão antiga (00:10)
        assert b'00:10' not in resp.data

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