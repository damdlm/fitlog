"""Testes de regressão para /calendar/api/eventos (routes/calendar_routes.py).

Cobrem o comportamento da API antes/depois da correção do N+1 (Fase 3):
TreinoService.get_all() passou a ser chamado uma única vez por request,
fora do loop de registros. Estes testes garantem que o JSON retornado
continua idêntico ao comportamento anterior.
"""
from datetime import datetime, timezone
from models import (
    db, User, TreinoVersao, VersaoGlobal, RegistroTreino, HistoricoTreino,
    Musculo, ExercicioUsuario, AlunoProfessor,
)


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def _criar_usuario(username, tipo='aluno'):
    u = User(username=username, email=f'{username}@t.com', tipo_usuario=tipo)
    u.set_password('x' * 12)
    db.session.add(u)
    db.session.commit()
    return u


def _criar_exercicio(user):
    m = Musculo(nome=f'm_{user.id}', nome_exibicao='Peito')
    db.session.add(m)
    db.session.commit()
    ex = ExercicioUsuario(usuario_id=user.id, nome='Supino', musculo_id=m.id)
    db.session.add(ex)
    db.session.commit()
    return ex


def _criar_treino(user, codigo='A'):
    # numero_versao é único por (user_id, numero_versao) -- conta quantas
    # versões esse usuário já tem para não colidir quando o teste chama
    # _criar_treino mais de uma vez para o mesmo usuário (ex: dois
    # treinos diferentes no mesmo teste).
    numero_versao = VersaoGlobal.query.filter_by(user_id=user.id).count() + 1
    versao = VersaoGlobal(numero_versao=numero_versao, descricao=f'V{numero_versao}', divisao='ABC',
                           data_inicio=datetime.now(timezone.utc).date(), user_id=user.id)
    db.session.add(versao)
    db.session.commit()
    treino = TreinoVersao(versao_id=versao.id, codigo=codigo, nome_treino=f'Treino {codigo}', descricao_treino='desc')
    db.session.add(treino)
    db.session.commit()
    return treino, versao


def _criar_registro(user, treino, versao, ex, data, carga=50, repeticoes=10):
    r = RegistroTreino(
        treino_versao_id=treino.id, versao_id=versao.id, periodo='periodo', semana=1,
        exercicio_usuario_id=ex.id, data_registro=data, user_id=user.id,
    )
    db.session.add(r)
    db.session.commit()
    db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=repeticoes))
    db.session.commit()
    return r


def test_eventos_usuario_sem_registros(client, app):
    with app.app_context():
        u = _criar_usuario('sem_registro_cal')
        user_id = u.id
    _login(client, User.query.get(user_id))

    resp = client.get('/calendar/api/eventos')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_eventos_um_registro(client, app):
    with app.app_context():
        u = _criar_usuario('um_registro_cal')
        ex = _criar_exercicio(u)
        treino, versao = _criar_treino(u)
        hoje = datetime.now(timezone.utc)
        _criar_registro(u, treino, versao, ex, hoje, carga=100, repeticoes=10)
        user_id = u.id

    _login(client, User.query.get(user_id))
    resp = client.get('/calendar/api/eventos')
    eventos = resp.get_json()

    assert resp.status_code == 200
    assert len(eventos) == 1
    assert eventos[0]['extendedProps']['volume'] == 1000.0
    assert eventos[0]['extendedProps']['exercicios'] == 1
    # treino corretamente resolvido (era o trecho afetado pela correção do N+1)
    assert eventos[0]['extendedProps']['treinos'][0]['treino_codigo'] == 'A'
    assert eventos[0]['extendedProps']['treinos'][0]['treino_nome'] == 'Treino A'


def test_eventos_varios_registros_mesmo_treino(client, app):
    with app.app_context():
        u = _criar_usuario('varios_mesmo_treino_cal')
        ex = _criar_exercicio(u)
        treino, versao = _criar_treino(u)
        hoje = datetime.now(timezone.utc)
        _criar_registro(u, treino, versao, ex, hoje, carga=100, repeticoes=10)
        _criar_registro(u, treino, versao, ex, hoje, carga=50, repeticoes=5)
        user_id = u.id

    _login(client, User.query.get(user_id))
    resp = client.get('/calendar/api/eventos')
    eventos = resp.get_json()

    assert len(eventos) == 1  # mesmo dia -> um único evento
    assert eventos[0]['extendedProps']['exercicios'] == 2
    assert eventos[0]['extendedProps']['volume'] == 1000.0 + 250.0
    assert len(eventos[0]['extendedProps']['treinos']) == 2
    for t in eventos[0]['extendedProps']['treinos']:
        assert t['treino_codigo'] == 'A'


def test_eventos_varios_treinos(client, app):
    with app.app_context():
        u = _criar_usuario('varios_treinos_cal')
        ex = _criar_exercicio(u)
        treino_a, versao_a = _criar_treino(u, codigo='A')
        treino_b, versao_b = _criar_treino(u, codigo='B')
        hoje = datetime.now(timezone.utc)
        _criar_registro(u, treino_a, versao_a, ex, hoje, carga=100, repeticoes=10)
        _criar_registro(u, treino_b, versao_b, ex, hoje, carga=20, repeticoes=10)
        user_id = u.id

    _login(client, User.query.get(user_id))
    resp = client.get('/calendar/api/eventos')
    eventos = resp.get_json()

    codigos = sorted(t['treino_codigo'] for t in eventos[0]['extendedProps']['treinos'])
    assert codigos == ['A', 'B']


def test_eventos_filtro_por_ano_e_mes(client, app):
    with app.app_context():
        u = _criar_usuario('filtro_ano_mes_cal')
        ex = _criar_exercicio(u)
        treino, versao = _criar_treino(u)
        _criar_registro(u, treino, versao, ex, datetime(2025, 3, 15, tzinfo=timezone.utc))
        _criar_registro(u, treino, versao, ex, datetime(2026, 7, 10, tzinfo=timezone.utc))
        user_id = u.id

    _login(client, User.query.get(user_id))

    resp_2025 = client.get('/calendar/api/eventos?ano=2025')
    eventos_2025 = resp_2025.get_json()
    assert len(eventos_2025) == 1
    assert eventos_2025[0]['start'] == '2025-03-15'

    resp_mes = client.get('/calendar/api/eventos?ano=2026&mes=7')
    eventos_mes = resp_mes.get_json()
    assert len(eventos_mes) == 1
    assert eventos_mes[0]['start'] == '2026-07-10'


def test_eventos_professor_consultando_aluno(client, app):
    with app.app_context():
        professor = _criar_usuario('prof_cal', tipo='professor')
        aluno = _criar_usuario('aluno_vinculado_cal', tipo='aluno')
        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
        db.session.commit()

        ex = _criar_exercicio(aluno)
        treino, versao = _criar_treino(aluno)
        hoje = datetime.now(timezone.utc)
        _criar_registro(aluno, treino, versao, ex, hoje, carga=60, repeticoes=8)

        professor_id = professor.id
        aluno_id = aluno.id

    _login(client, User.query.get(professor_id))
    resp = client.get(f'/calendar/api/eventos?aluno_id={aluno_id}')
    eventos = resp.get_json()

    assert len(eventos) == 1
    assert eventos[0]['extendedProps']['treinos'][0]['treino_codigo'] == 'A'


def test_eventos_professor_sem_vinculo_cai_para_proprios_dados(client, app):
    with app.app_context():
        professor = _criar_usuario('prof_sem_vinculo_cal', tipo='professor')
        outro_aluno = _criar_usuario('aluno_nao_vinculado_cal', tipo='aluno')

        ex = _criar_exercicio(outro_aluno)
        treino, versao = _criar_treino(outro_aluno)
        _criar_registro(outro_aluno, treino, versao, ex, datetime.now(timezone.utc))

        professor_id = professor.id
        outro_aluno_id = outro_aluno.id

    _login(client, User.query.get(professor_id))
    # get_target_user_id cai de volta para o próprio professor quando o
    # aluno não está vinculado -- o professor não tem registros, então
    # a lista de eventos deve vir vazia (não deve vazar dados do aluno).
    resp = client.get(f'/calendar/api/eventos?aluno_id={outro_aluno_id}')
    assert resp.get_json() == []


def test_eventos_com_exercicio_do_catalogo_sistema(client, app):
    """Registro usando ExercicioSistema (catálogo global) em vez de personalizado."""
    from models import ExercicioSistema

    with app.app_context():
        u = _criar_usuario('catalogo_sistema_cal')
        treino, versao = _criar_treino(u)
        ex_sistema = ExercicioSistema(id_original='9999', nome='Agachamento', grupo_muscular='Pernas')
        db.session.add(ex_sistema)
        db.session.commit()

        r = RegistroTreino(
            treino_versao_id=treino.id, versao_id=versao.id, periodo='periodo', semana=1,
            exercicio_base_id=ex_sistema.id, data_registro=datetime.now(timezone.utc),
            user_id=u.id,
        )
        db.session.add(r)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=r.id, carga=40, repeticoes=12))
        db.session.commit()
        user_id = u.id

    _login(client, User.query.get(user_id))
    resp = client.get('/calendar/api/eventos')
    eventos = resp.get_json()

    assert len(eventos) == 1
    assert eventos[0]['extendedProps']['treinos'][0]['exercicio_nome'] == 'Agachamento'


class TestCalendarioPagina:

    def test_pagina_carrega(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_pagina_1')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.get('/calendar/calendario')
        assert resp.status_code == 200

    def test_requer_login(self, client):
        resp = client.get('/calendar/calendario', follow_redirects=False)
        assert resp.status_code in (302, 401)


class TestApiEventoDetalhe:

    def test_dono_ve_o_detalhe(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_detalhe_1')
            ex = _criar_exercicio(u)
            treino, versao = _criar_treino(u)
            registro = _criar_registro(u, treino, versao, ex, datetime.now(timezone.utc), carga=60, repeticoes=8)
            user_id, registro_id = u.id, registro.id
        _login(client, User.query.get(user_id))

        resp = client.get(f'/calendar/api/evento/{registro_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['treino']['codigo'] == 'A'
        assert data['exercicios'][0]['nome'] == 'Supino'
        assert data['exercicios'][0]['volume'] == 480.0
        assert data['total_volume'] == 480.0

    def test_registro_inexistente_retorna_404(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_detalhe_2')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.get('/calendar/api/evento/999999')
        assert resp.status_code == 404

    def test_outro_usuario_sem_vinculo_nao_ve_o_registro(self, client, app):
        """IDOR: um usuário não pode ver o detalhe de um registro de
        outra pessoa só por saber o ID."""
        with app.app_context():
            dono = _criar_usuario('cal_detalhe_dono')
            outro = _criar_usuario('cal_detalhe_outro')
            ex = _criar_exercicio(dono)
            treino, versao = _criar_treino(dono)
            registro = _criar_registro(dono, treino, versao, ex, datetime.now(timezone.utc))
            outro_id, registro_id = outro.id, registro.id
        _login(client, User.query.get(outro_id))

        resp = client.get(f'/calendar/api/evento/{registro_id}')
        assert resp.status_code == 404

    def test_professor_vinculado_ve_o_registro_do_aluno(self, client, app):
        with app.app_context():
            prof = _criar_usuario('cal_detalhe_prof', tipo='professor')
            aluno = _criar_usuario('cal_detalhe_aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            db.session.commit()
            ex = _criar_exercicio(aluno)
            treino, versao = _criar_treino(aluno)
            registro = _criar_registro(aluno, treino, versao, ex, datetime.now(timezone.utc))
            prof_id, registro_id = prof.id, registro.id
        _login(client, User.query.get(prof_id))

        resp = client.get(f'/calendar/api/evento/{registro_id}')
        assert resp.status_code == 200


class TestApiEventoExcluir:

    def test_dono_exclui_com_sucesso(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_excluir_1')
            ex = _criar_exercicio(u)
            treino, versao = _criar_treino(u)
            hoje_meia_noite = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
            registro = _criar_registro(u, treino, versao, ex, hoje_meia_noite)
            user_id, registro_id = u.id, registro.id
        _login(client, User.query.get(user_id))

        resp = client.post(f'/calendar/api/evento/{registro_id}/excluir')

        assert resp.status_code == 200
        assert resp.get_json() == {'ok': True}
        with app.app_context():
            assert db.session.get(RegistroTreino, registro_id) is None

    def test_registro_inexistente_retorna_404(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_excluir_2')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.post('/calendar/api/evento/999999/excluir')
        assert resp.status_code == 404

    def test_outro_usuario_nao_pode_excluir(self, client, app):
        """Nem professor: exclusão só o próprio dono."""
        with app.app_context():
            prof = _criar_usuario('cal_excluir_prof', tipo='professor')
            aluno = _criar_usuario('cal_excluir_aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            db.session.commit()
            ex = _criar_exercicio(aluno)
            treino, versao = _criar_treino(aluno)
            hoje_meia_noite = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
            registro = _criar_registro(aluno, treino, versao, ex, hoje_meia_noite)
            prof_id, registro_id = prof.id, registro.id
        _login(client, User.query.get(prof_id))

        resp = client.post(f'/calendar/api/evento/{registro_id}/excluir')

        assert resp.status_code == 404
        with app.app_context():
            assert db.session.get(RegistroTreino, registro_id) is not None


class TestApiEventoDadosEdicao:

    def _criar_versao_exercicio(self, treino, ex):
        from models import VersaoExercicio
        db.session.add(VersaoExercicio(treino_versao_id=treino.id, exercicio_usuario_id=ex.id, ordem=0))
        db.session.commit()

    def test_dados_incompletos_retorna_400(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_1')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.get('/calendar/api/evento/dados-edicao')
        assert resp.status_code == 400

    def test_data_invalida_retorna_400(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_2')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.get('/calendar/api/evento/dados-edicao?data=31/12/2026&treino=1')
        assert resp.status_code == 400

    def test_sem_versao_ativa_na_data_retorna_404(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_3')
            user_id = u.id
        _login(client, User.query.get(user_id))

        resp = client.get('/calendar/api/evento/dados-edicao?data=2020-01-01&treino=1')
        assert resp.status_code == 404

    def test_treino_nao_encontrado_na_versao_retorna_404(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_4')
            treino, versao = _criar_treino(u)
            user_id = u.id
        _login(client, User.query.get(user_id))

        hoje = datetime.now(timezone.utc).date().isoformat()
        resp = client.get(f'/calendar/api/evento/dados-edicao?data={hoje}&treino=999999')
        assert resp.status_code == 404

    def test_sucesso_retorna_exercicios_com_valores_ja_salvos(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_5')
            ex = _criar_exercicio(u)
            treino, versao = _criar_treino(u)
            self._criar_versao_exercicio(treino, ex)
            hoje_meia_noite = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
            _criar_registro(u, treino, versao, ex, hoje_meia_noite, carga=75, repeticoes=6)
            user_id, treino_id = u.id, treino.id
        _login(client, User.query.get(user_id))

        data_str = datetime.now(timezone.utc).date().isoformat()
        resp = client.get(f'/calendar/api/evento/dados-edicao?data={data_str}&treino={treino_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['treino_codigo'] == 'A'
        assert len(data['exercicios']) == 1
        assert data['exercicios'][0]['nome'] == 'Supino'
        assert data['exercicios'][0]['carga'] == 75.0
        assert data['exercicios'][0]['repeticoes'] == 6

    def test_exercicio_sem_registro_ainda_entra_zerado(self, client, app):
        with app.app_context():
            u = _criar_usuario('cal_edicao_6')
            ex = _criar_exercicio(u)
            treino, versao = _criar_treino(u)
            self._criar_versao_exercicio(treino, ex)
            user_id, treino_id = u.id, treino.id
        _login(client, User.query.get(user_id))

        data_str = datetime.now(timezone.utc).date().isoformat()
        resp = client.get(f'/calendar/api/evento/dados-edicao?data={data_str}&treino={treino_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['exercicios'][0]['carga'] == 0
        assert data['exercicios'][0]['repeticoes'] == 0
        assert data['exercicios'][0]['num_series'] == 0


class TestEstimarData:
    """Função pura usada como fallback quando o registro não tem
    data_registro salva -- estima a partir de período+semana."""

    def test_estima_primeiro_dia_da_semana_1(self):
        from routes.calendar_routes import _estimar_data
        from datetime import date
        assert _estimar_data('Março/2024', 1) == date(2024, 3, 1)

    def test_estima_semana_3_soma_14_dias(self):
        from routes.calendar_routes import _estimar_data
        from datetime import date
        assert _estimar_data('Março/2024', 3) == date(2024, 3, 15)

    def test_periodo_sem_barra_retorna_none(self):
        from routes.calendar_routes import _estimar_data
        assert _estimar_data('Março 2024', 1) is None

    def test_mes_invalido_retorna_none(self):
        from routes.calendar_routes import _estimar_data
        assert _estimar_data('MesInventado/2024', 1) is None

    def test_ano_nao_numerico_retorna_none(self):
        from routes.calendar_routes import _estimar_data
        assert _estimar_data('Março/abcd', 1) is None