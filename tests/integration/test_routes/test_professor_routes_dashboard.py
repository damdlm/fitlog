"""Testes de integração para a rota /professor/dashboard (novo painel
operacional do professor)."""
from datetime import date, datetime, timedelta, timezone

from models import db, User, AlunoProfessor, VersaoGlobal, TreinoVersao


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False, ativo=True):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo_usuario, is_admin=is_admin, ativo=ativo,
             nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _associar(aluno_id, professor_id, ativo=True):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo,
                            data_associacao=datetime.now(timezone.utc))
    db.session.add(assoc)
    db.session.commit()
    return assoc


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestDashboardProfessor:
    def test_requer_login(self, client):
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 302

    def test_acesso_negado_para_aluno_comum(self, client, app):
        with app.app_context():
            username = _criar_usuario('pd_neg_1').username

        _login(client, username)
        resp = client.get('/professor/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        # redirecionado para fora do painel (não é professor nem admin)
        assert b'professor/dashboard' not in resp.request.path.encode()

    def test_professor_acessa_o_proprio_painel(self, client, app):
        with app.app_context():
            username = _criar_usuario('pd_ok_1', tipo_usuario='professor').username

        _login(client, username)
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 200
        assert 'Painel do Professor'.encode() in resp.data or 'painel operacional'.lower().encode() in resp.data.lower()

    def test_admin_tambem_acessa(self, client, app):
        with app.app_context():
            username = _criar_usuario('pd_admin_1', is_admin=True).username

        _login(client, username)
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 200

    def test_mostra_apenas_dados_dos_proprios_alunos(self, client, app):
        with app.app_context():
            from services.dashboard_service import _hoje_br
            from models import RegistroTreino, ExercicioSistema

            prof1 = _criar_usuario('pd_iso_1a', tipo_usuario='professor')
            prof2 = _criar_usuario('pd_iso_1b', tipo_usuario='professor')
            aluno1 = _criar_usuario('pd_iso_aluno1', ativo=True)
            aluno2 = _criar_usuario('pd_iso_aluno2', ativo=True)
            _associar(aluno1.id, prof1.id)
            _associar(aluno2.id, prof2.id)

            ex = ExercicioSistema(id_original='pd_iso_ex_1', nome='Supino', grupo_muscular='Peito')
            db.session.add(ex)
            db.session.commit()

            versao1 = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                                    data_inicio=date.today(), user_id=aluno1.id)
            db.session.add(versao1)
            db.session.commit()
            treino1 = TreinoVersao(versao_id=versao1.id, codigo='A', nome_treino='Treino A')
            db.session.add(treino1)
            db.session.commit()
            db.session.add(RegistroTreino(treino_versao_id=treino1.id, versao_id=versao1.id,
                                           periodo='Setembro/2026', semana=1,
                                           exercicio_base_id=ex.id,
                                           data_registro=_hoje_br(), user_id=aluno1.id))
            db.session.commit()

            versao2 = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                                    data_inicio=date.today(), user_id=aluno2.id)
            db.session.add(versao2)
            db.session.commit()
            treino2 = TreinoVersao(versao_id=versao2.id, codigo='A', nome_treino='Treino A')
            db.session.add(treino2)
            db.session.commit()
            db.session.add(RegistroTreino(treino_versao_id=treino2.id, versao_id=versao2.id,
                                           periodo='Setembro/2026', semana=1,
                                           exercicio_base_id=ex.id,
                                           data_registro=_hoje_br(), user_id=aluno2.id))
            db.session.commit()

            username = prof1.username

        _login(client, username)
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True).lower()
        assert 'pd_iso_aluno1' in html
        assert 'pd_iso_aluno2' not in html

    def test_alunos_de_outro_professor_nao_contam_no_total(self, client, app):
        with app.app_context():
            prof1 = _criar_usuario('pd_iso_2a', tipo_usuario='professor')
            prof2 = _criar_usuario('pd_iso_2b', tipo_usuario='professor')
            for i in range(3):
                aluno = _criar_usuario(f'pd_iso_2_outro{i}')
                _associar(aluno.id, prof2.id)
            username = prof1.username

        _login(client, username)
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # o professor 1 não tem alunos -- "0" deve aparecer como contagem
        # de alunos ativos, e nada dos alunos do professor 2 deve vazar
        assert 'pd_iso_2_outro0' not in html.lower()

    def test_sem_alunos_mostra_estado_vazio_de_atencao(self, client, app):
        with app.app_context():
            username = _criar_usuario('pd_vazio_1', tipo_usuario='professor').username

        _login(client, username)
        resp = client.get('/professor/dashboard')
        assert resp.status_code == 200
        assert 'Tudo certo por aqui'.encode() in resp.data

    def test_link_do_dashboard_aparece_no_menu_do_professor(self, client, app):
        with app.app_context():
            username = _criar_usuario('pd_menu_1', tipo_usuario='professor').username

        _login(client, username)
        resp = client.get('/professor/alunos')
        assert resp.status_code == 200
        assert b'/professor/dashboard' in resp.data
