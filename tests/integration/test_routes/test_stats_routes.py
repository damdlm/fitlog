"""Testes de integração para routes/stats_routes.py (professor) --
alteradas recentemente ("correções tabela de progresso", "alteração na
tabela de progresso"), então sem nenhum teste até agora apesar do
risco de regressão. Foco na Tabela de Progresso (/visualizar/tabela),
que é a mais complexa: filtro por versão, renumeração de semana por
mês e agrupamento por treino.
"""
from datetime import date, datetime, timedelta, timezone

from models import (
    db, User, Musculo, ExercicioUsuario, TreinoVersao, VersaoGlobal,
    VersaoExercicio, RegistroTreino, HistoricoTreino,
)
from services.billing_service import BillingService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()
    # sem trial, as rotas caem bloqueadas por acesso_premium_required
    BillingService.iniciar_trial(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _criar_versao_com_treino(user_id, numero_versao=1, codigo='A', data_inicio=None):
    versao = VersaoGlobal(numero_versao=numero_versao, descricao=f'V{numero_versao}',
                           divisao='ABC', data_inicio=data_inicio or date(2026, 1, 1),
                           user_id=user_id)
    db.session.add(versao)
    db.session.commit()
    treino = TreinoVersao(versao_id=versao.id, codigo=codigo, nome_treino=f'Treino {codigo}')
    db.session.add(treino)
    db.session.commit()
    return versao, treino


def _criar_exercicio(user_id, nome, musculo_id=None):
    ex = ExercicioUsuario(usuario_id=user_id, nome=nome, musculo_id=musculo_id)
    db.session.add(ex)
    db.session.commit()
    return ex


def _registrar_treino(user_id, treino, versao, exercicio, data_registro, carga=40, repeticoes=10):
    from utils.date_utils import data_para_periodo, data_para_semana
    registro = RegistroTreino(
        treino_versao_id=treino.id, versao_id=versao.id,
        periodo=data_para_periodo(data_registro.date()),
        semana=data_para_semana(data_registro.date()),
        data_registro=data_registro, user_id=user_id,
        exercicio_usuario_id=exercicio.id,
    )
    db.session.add(registro)
    db.session.commit()
    db.session.add(HistoricoTreino(registro_id=registro.id, carga=carga, repeticoes=repeticoes, ordem=1))
    db.session.commit()
    return registro


class TestEstatisticas:

    def test_carrega_sem_registro_nenhum(self, client, app):
        with app.app_context():
            _criar_usuario('stats_prof_vazio', tipo_usuario='professor')
        _login(client, 'stats_prof_vazio')

        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200

    def test_musculo_destaque_e_o_de_maior_volume(self, client, app):
        with app.app_context():
            u = _criar_usuario('stats_prof_destaque', tipo_usuario='professor')
            musc_peito = Musculo(nome=f'peito_{u.id}', nome_exibicao='Peito')
            musc_costas = Musculo(nome=f'costas_{u.id}', nome_exibicao='Costas')
            db.session.add_all([musc_peito, musc_costas])
            db.session.commit()

            ex_peito = _criar_exercicio(u.id, 'Supino', musc_peito.id)
            ex_costas = _criar_exercicio(u.id, 'Remada', musc_costas.id)
            versao, treino = _criar_versao_com_treino(u.id)
            db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex_peito.id, ordem=0))
            db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex_costas.id, ordem=1))
            db.session.commit()

            agora = datetime.now(timezone.utc)
            # Peito com volume bem maior (carga x reps x séries)
            _registrar_treino(u.id, treino, versao, ex_peito, agora, carga=100, repeticoes=10)
            _registrar_treino(u.id, treino, versao, ex_costas, agora, carga=10, repeticoes=5)

        _login(client, 'stats_prof_destaque')
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200
        assert b'Peito' in resp.data


class TestVisualizarTabelaProgresso:

    def test_carrega_sem_registro_nenhum(self, client, app):
        with app.app_context():
            _criar_usuario('tab_prog_vazio', tipo_usuario='professor')
        _login(client, 'tab_prog_vazio')

        resp = client.get('/estatisticas/visualizar/tabela')
        assert resp.status_code == 200

    def test_mostra_exercicio_com_registro_recente(self, client, app):
        with app.app_context():
            u = _criar_usuario('tab_prog_1', tipo_usuario='professor')
            ex = _criar_exercicio(u.id, 'Agachamento Livre')
            versao, treino = _criar_versao_com_treino(u.id)
            db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.commit()
            _registrar_treino(u.id, treino, versao, ex, datetime.now(timezone.utc), carga=80, repeticoes=8)

        _login(client, 'tab_prog_1')
        resp = client.get('/estatisticas/visualizar/tabela')
        assert resp.status_code == 200
        assert 'Agachamento Livre'.encode() in resp.data

    def test_registro_fora_da_janela_de_90_dias_nao_aparece(self, client, app):
        with app.app_context():
            u = _criar_usuario('tab_prog_janela', tipo_usuario='professor')
            ex = _criar_exercicio(u.id, 'Exercicio Antigo Demais')
            versao, treino = _criar_versao_com_treino(
                u.id, data_inicio=date.today() - timedelta(days=200))
            db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.commit()
            data_antiga = datetime.now(timezone.utc) - timedelta(days=120)
            _registrar_treino(u.id, treino, versao, ex, data_antiga)

        _login(client, 'tab_prog_janela')
        resp = client.get('/estatisticas/visualizar/tabela')
        assert resp.status_code == 200
        # o exercício existe (está no treino) mas nenhuma semana com
        # dado dele deveria aparecer -- carga/reps ficam None
        assert b'80.0' not in resp.data

    def test_filtro_por_versao_so_mostra_exercicios_daquela_versao(self, client, app):
        with app.app_context():
            u = _criar_usuario('tab_prog_filtro', tipo_usuario='professor')
            ex_v1 = _criar_exercicio(u.id, 'ExercicioDaV1Unico')
            ex_v2 = _criar_exercicio(u.id, 'ExercicioDaV2Unico')

            versao1, treino1 = _criar_versao_com_treino(u.id, numero_versao=1, codigo='A')
            db.session.add(VersaoExercicio(treino_versao_id=treino1.id, exercicio_usuario_id=ex_v1.id, ordem=0))
            db.session.commit()

            versao2, treino2 = _criar_versao_com_treino(u.id, numero_versao=2, codigo='A')
            db.session.add(VersaoExercicio(treino_versao_id=treino2.id, exercicio_usuario_id=ex_v2.id, ordem=0))
            db.session.commit()

            versao_id_v1 = versao1.id

        _login(client, 'tab_prog_filtro')
        resp = client.get(f'/estatisticas/visualizar/tabela?versao_id={versao_id_v1}')

        assert resp.status_code == 200
        assert b'ExercicioDaV1Unico' in resp.data
        assert b'ExercicioDaV2Unico' not in resp.data

    def test_exige_login(self, client):
        resp = client.get('/estatisticas/visualizar/tabela', follow_redirects=False)
        assert resp.status_code in (302, 401)


class TestEstatisticasAluno:

    def test_carrega_sem_registro_nenhum(self, client, app):
        with app.app_context():
            _criar_usuario('stats_aluno_vazio')
        _login(client, 'stats_aluno_vazio')

        resp = client.get('/aluno/estatisticas')
        assert resp.status_code == 200


class TestApiBuscarProfessores:

    def test_busca_por_termo_filtra_corretamente(self, client, app):
        with app.app_context():
            _criar_usuario('busca_prof_aluno')
            _criar_usuario('busca_prof_walter', tipo_usuario='professor')
            _criar_usuario('busca_prof_outro', tipo_usuario='professor')
        _login(client, 'busca_prof_aluno')

        resp = client.get('/aluno/api/buscar-professores?termo=walter')
        assert resp.status_code == 200
        dados = resp.get_json()
        usernames = [p['username'] for p in dados]
        assert 'busca_prof_walter' in usernames
        assert 'busca_prof_outro' not in usernames

    def test_sem_termo_retorna_todos_os_professores_ativos(self, client, app):
        with app.app_context():
            _criar_usuario('busca_prof_aluno2')
            _criar_usuario('busca_prof_a', tipo_usuario='professor')
            _criar_usuario('busca_prof_b', tipo_usuario='professor')
        _login(client, 'busca_prof_aluno2')

        resp = client.get('/aluno/api/buscar-professores')
        assert resp.status_code == 200
        dados = resp.get_json()
        assert len(dados) >= 2

    def test_nao_retorna_alunos(self, client, app):
        with app.app_context():
            _criar_usuario('busca_prof_aluno3')
            _criar_usuario('busca_prof_c', tipo_usuario='professor')
        _login(client, 'busca_prof_aluno3')

        resp = client.get('/aluno/api/buscar-professores')
        dados = resp.get_json()
        usernames = [p['username'] for p in dados]
        assert 'busca_prof_aluno3' not in usernames
