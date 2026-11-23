"""Lote 3: alertas do painel do professor -- sem treinar, abaixo do ritmo,
ficha para revisar e recorde da semana; filtro, ações e "Visto"."""
from datetime import datetime, timedelta, timezone

from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, RegistroTreino,
                    HistoricoTreino, ExercicioSistema, AlertaVistoProfessor)
from services.base_service import CacheService
from services.dashboard_service import DashboardService, _hoje_br, _telefone_whatsapp, _kg


def _usuario(username, tipo='aluno', telefone=None):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo,
             ativo=True, nome_completo=username.replace('_', ' ').title(), telefone=telefone)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _vincular(aluno, prof):
    db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True,
                                  data_associacao=datetime.now(timezone.utc) - timedelta(days=90)))
    db.session.commit()


def _ficha(aluno, dias_atras=0):
    v = VersaoGlobal(numero_versao=1, descricao='V1', divisao='AB', user_id=aluno.id,
                     data_inicio=(_hoje_br() - timedelta(days=dias_atras)).date())
    db.session.add(v)
    db.session.commit()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='Treino A')
    db.session.add(t)
    db.session.commit()
    return v, t


_N_EX = [0]


def _exercicio(nome='Supino'):
    _N_EX[0] += 1
    ex = ExercicioSistema(id_original=f'alerta_ex_{_N_EX[0]}', nome=nome, grupo_muscular='Peito')
    db.session.add(ex)
    db.session.commit()
    return ex


def _treino(aluno, v, t, ex, dias_atras, carga=50, cardio=False):
    r = RegistroTreino(treino_versao_id=t.id, versao_id=v.id, periodo='Nov/2026', semana=1,
                       exercicio_base_id=ex.id, user_id=aluno.id,
                       data_registro=_hoje_br() - timedelta(days=dias_atras))
    db.session.add(r)
    db.session.flush()
    if cardio:
        db.session.add(HistoricoTreino(registro_id=r.id, duracao_segundos=600))
    else:
        db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=10))
    db.session.commit()


def _alertas(prof, tipo=None):
    CacheService.invalidate(f'dashboard_professor:{prof.id}')
    itens = DashboardService.dados_professor(prof.id)['alertas']
    return [a for a in itens if tipo is None or a['tipo'] == tipo]


class TestRitmo:
    def test_caiu_para_menos_da_metade_do_habitual(self, app):
        with app.app_context():
            prof = _usuario('rit_prof', 'professor')
            aluno = _usuario('rit_aluno')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            ex = _exercicio()
            # base: 3x/semana nas 6 semanas anteriores (18 dias -> 6 por quinzena)
            for semana in range(6):
                for d in (0, 2, 4):
                    _treino(aluno, v, t, ex, 14 + semana * 7 + d)
            # recente: 2 treinos em 14 dias (último há 3 dias -> não está "sem treinar")
            _treino(aluno, v, t, ex, 3)
            _treino(aluno, v, t, ex, 10)
            a = _alertas(prof, 'ritmo')
            assert len(a) == 1
            assert a[0]['detalhe'] == 'treinou 2 vezes em 2 semanas · costuma 6'
            assert a[0]['chave'].startswith(str(_hoje_br().isocalendar()[0]) + '-W')

    def test_ritmo_normal_nao_alerta(self, app):
        with app.app_context():
            prof = _usuario('rit_prof2', 'professor')
            aluno = _usuario('rit_aluno2')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            ex = _exercicio()
            for d in range(0, 56, 2):
                _treino(aluno, v, t, ex, d)
            assert _alertas(prof, 'ritmo') == []

    def test_quem_treinava_pouco_nao_alerta(self, app):
        with app.app_context():
            prof = _usuario('rit_prof3', 'professor')
            aluno = _usuario('rit_aluno3')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            ex = _exercicio()
            for d in (16, 30, 44):  # 1 por quinzena: abaixo do mínimo
                _treino(aluno, v, t, ex, d)
            _treino(aluno, v, t, ex, 2)
            assert _alertas(prof, 'ritmo') == []

    def test_parado_fica_so_em_sem_treinar(self, app):
        with app.app_context():
            prof = _usuario('rit_prof4', 'professor')
            aluno = _usuario('rit_aluno4')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            ex = _exercicio()
            for d in range(14, 56, 2):
                _treino(aluno, v, t, ex, d)
            tipos = [a['tipo'] for a in _alertas(prof)]
            assert tipos == ['sem_treinar']


class TestRecorde:
    def test_carga_da_semana_passou_a_anterior(self, app):
        with app.app_context():
            prof = _usuario('rec_prof', 'professor')
            aluno = _usuario('rec_aluno')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            supino, agach = _exercicio('Supino'), _exercicio('Agachamento')
            _treino(aluno, v, t, supino, 20, carga=60)
            _treino(aluno, v, t, supino, 2, carga=62.5)
            _treino(aluno, v, t, agach, 20, carga=80)
            _treino(aluno, v, t, agach, 1, carga=90)
            a = _alertas(prof, 'recorde')
            assert len(a) == 1
            assert a[0]['detalhe'] == '2 recordes na semana · Agachamento: 90 kg (antes 80 kg)'

    def test_sem_historico_anterior_ou_cardio_nao_conta(self, app):
        with app.app_context():
            prof = _usuario('rec_prof2', 'professor')
            aluno = _usuario('rec_aluno2')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            novo, esteira, igual = _exercicio('Novo'), _exercicio('Esteira'), _exercicio('Remada')
            _treino(aluno, v, t, novo, 1, carga=40)
            _treino(aluno, v, t, esteira, 20, cardio=True)
            _treino(aluno, v, t, esteira, 1, cardio=True)
            _treino(aluno, v, t, igual, 20, carga=50)
            _treino(aluno, v, t, igual, 1, carga=50)
            assert _alertas(prof, 'recorde') == []


class TestOrdemERevisao:
    def test_ordem_dos_tipos_e_chaves(self, app):
        with app.app_context():
            prof = _usuario('ord_prof', 'professor')
            parado, revisar = _usuario('ord_parado'), _usuario('ord_revisar')
            _vincular(parado, prof)
            _vincular(revisar, prof)
            v, t = _ficha(parado)
            ex = _exercicio()
            _treino(parado, v, t, ex, 9)
            v2, t2 = _ficha(revisar, dias_atras=70)
            _treino(revisar, v2, t2, ex, 1)
            itens = _alertas(prof)
            assert [a['tipo'] for a in itens] == ['sem_treinar', 'revisao']
            assert itens[0]['chave'] == (_hoje_br() - timedelta(days=9)).date().isoformat()
            assert itens[0]['detalhe'] == '9 dias sem treinar'
            assert itens[1]['chave'] == f'v{v2.id}'
            assert itens[1]['detalhe'] == 'ficha v1 há 70 dias sem troca'


class TestVisto:
    def test_visto_esconde_e_volta_quando_a_chave_muda(self, app):
        with app.app_context():
            prof = _usuario('vis_prof', 'professor')
            aluno = _usuario('vis_aluno')
            _vincular(aluno, prof)
            v, t = _ficha(aluno)
            ex = _exercicio()
            _treino(aluno, v, t, ex, 10)
            alerta = _alertas(prof)[0]
            assert DashboardService.marcar_visto(prof.id, aluno.id, 'sem_treinar', alerta['chave'])
            ativos, vistos = DashboardService.separar_vistos(prof.id, _alertas(prof))
            assert ativos == [] and len(vistos) == 1
            # treinou e parou de novo: outra chave, o alerta volta
            _treino(aluno, v, t, ex, 8)
            ativos, vistos = DashboardService.separar_vistos(prof.id, _alertas(prof))
            assert len(ativos) == 1 and vistos == []

    def test_desfazer(self, app):
        with app.app_context():
            prof = _usuario('vis_prof2', 'professor')
            aluno = _usuario('vis_aluno2')
            _vincular(aluno, prof)
            DashboardService.marcar_visto(prof.id, aluno.id, 'sem_treinar', 'nunca')
            assert AlertaVistoProfessor.query.filter_by(professor_id=prof.id).count() == 1
            DashboardService.marcar_visto(prof.id, aluno.id, 'sem_treinar', 'nunca', desfazer=True)
            assert AlertaVistoProfessor.query.filter_by(professor_id=prof.id).count() == 0

    def test_rejeita_aluno_de_outro_professor_e_tipo_invalido(self, app):
        with app.app_context():
            prof, outro = _usuario('vis_prof3', 'professor'), _usuario('vis_outro', 'professor')
            aluno = _usuario('vis_aluno3')
            _vincular(aluno, outro)
            assert not DashboardService.marcar_visto(prof.id, aluno.id, 'sem_treinar', 'nunca')
            assert not DashboardService.marcar_visto(outro.id, aluno.id, 'xyz', 'nunca')
            assert not DashboardService.marcar_visto(outro.id, aluno.id, 'sem_treinar', 'x' * 41)


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestRotaETela:
    def test_painel_mostra_alerta_filtros_acoes_e_whatsapp(self, client, app):
        with app.app_context():
            prof = _usuario('tela_prof', 'professor')
            aluno = _usuario('tela_aluno_ana', telefone='(11) 98765-4321')
            _vincular(aluno, prof)
            aluno_id = aluno.id
            CacheService.invalidate(f'dashboard_professor:{prof.id}')
        _login(client, 'tela_prof')
        html = client.get('/professor/dashboard').get_data(as_text=True)
        assert 'pd-alerta--sem_treinar' in html
        assert 'nunca registrou treino' in html
        assert 'data-filtro="sem_treinar"' in html and 'data-filtro="recorde"' in html
        assert f'/professor/aluno/{aluno_id}/calendario' in html
        assert 'https://wa.me/5511987654321?text=Oi%2C%20Tela' in html
        assert 'Tudo certo por aqui' in html  # estado vazio pronto (escondido) para o JS

    def test_rota_visto_esconde_do_painel(self, client, app):
        with app.app_context():
            prof = _usuario('tela_prof2', 'professor')
            aluno = _usuario('tela_aluno2')
            _vincular(aluno, prof)
            aluno_id = aluno.id
            CacheService.invalidate(f'dashboard_professor:{prof.id}')
        _login(client, 'tela_prof2')
        r = client.post('/professor/alertas/visto',
                        json={'aluno_id': aluno_id, 'tipo': 'sem_treinar', 'chave': 'nunca'})
        assert r.status_code == 200 and r.get_json() == {'ok': True}
        html = client.get('/professor/dashboard').get_data(as_text=True)
        lista = html.split('id="pdListaAlertas"')[1].split('id="pdMostrarMais"')[0]
        vistos = html.split('id="pdListaVistos"')[1]
        assert 'pd-alerta--sem_treinar' not in lista
        assert 'pd-alerta--sem_treinar' in vistos
        assert '<span id="pdVistosN">1</span>' in html
        r = client.post('/professor/alertas/visto',
                        json={'aluno_id': aluno_id, 'tipo': 'sem_treinar', 'chave': 'nunca', 'desfazer': True})
        assert r.get_json() == {'ok': True}

    def test_rota_visto_valida_entrada(self, client, app):
        with app.app_context():
            _usuario('tela_prof3', 'professor')
            alheio = _usuario('tela_alheio')
            outro = _usuario('tela_outro', 'professor')
            _vincular(alheio, outro)
            alheio_id = alheio.id
            _usuario('tela_so_aluno')
        _login(client, 'tela_prof3')
        assert client.post('/professor/alertas/visto', json={'aluno_id': alheio_id, 'tipo': 'sem_treinar',
                                                             'chave': 'nunca'}).status_code == 404
        assert client.post('/professor/alertas/visto', json={'aluno_id': 'x'}).status_code == 400
        assert client.post('/professor/alertas/visto', data='[]',
                           content_type='application/json').status_code == 400
        client.get('/auth/logout')
        _login(client, 'tela_so_aluno')
        r = client.post('/professor/alertas/visto', json={'aluno_id': alheio_id, 'tipo': 'sem_treinar',
                                                          'chave': 'nunca'})
        assert r.status_code in (302, 403)


def test_telefone_e_kg():
    assert _telefone_whatsapp('(11) 98765-4321') == '5511987654321'
    assert _telefone_whatsapp('+55 11 3333-4444') == '551133334444'
    assert _telefone_whatsapp('123') is None
    assert _telefone_whatsapp(None) is None
    assert _kg(80.0) == '80 kg' and _kg(37.5) == '37,5 kg'


def test_migracao_cria_e_remove_a_tabela(app):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    caminho = 'migrations/versions/c8d1e5f2a7b4_alertas_vistos_professor.py'
    spec = importlib.util.spec_from_file_location('mig_alertas', caminho)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == 'b7e2c4d9a1f3'
    with app.app_context():
        def rodar(f):
            with db.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    f()

        def existe():
            return 'alertas_vistos_professor' in inspect(db.engine).get_table_names()
        assert existe()
        rodar(mig.downgrade)
        assert not existe()
        rodar(mig.upgrade)
        assert existe()
