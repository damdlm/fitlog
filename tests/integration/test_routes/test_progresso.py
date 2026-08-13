from datetime import datetime, timedelta, timezone, date
from models import db, User, Treino, RegistroTreino, HistoricoTreino, Musculo, ExercicioUsuario, VersaoGlobal


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True


def test_progresso_sem_registro_retorna_vazio(client, app):
    with app.app_context():
        u = User(username='sem_treino_pt', email='sem_pt@t.com', tipo_usuario='aluno')
        u.set_password('x' * 12)
        db.session.add(u)
        db.session.commit()
        user_id = u.id

    _login(client, u.__class__.query.get(user_id))
    resp = client.get('/api/progresso')
    data = resp.get_json()
    assert resp.status_code == 200
    assert data['semanas'] == []
    assert data['volumes'] == []


def test_progresso_ultimos_30_dias_com_registro(client, app):
    with app.app_context():
        u = User(username='com_treino_pt', email='com_pt@t.com', tipo_usuario='aluno')
        u.set_password('x' * 12)
        db.session.add(u)
        db.session.commit()

        m = Musculo(nome='peito_pt', nome_exibicao='Peito')
        db.session.add(m)
        db.session.commit()

        ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=m.id)
        db.session.add(ex)
        db.session.commit()

        treino = Treino(user_id=u.id, codigo='A', nome='Treino A', descricao='desc')
        db.session.add(treino)
        db.session.commit()

        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                               data_inicio=date(2026, 1, 1), user_id=u.id)
        db.session.add(versao)
        db.session.commit()

        hoje = datetime.now(timezone.utc)
        for dias_atras in [0, 5, 40]:  # 40 deve ficar fora da janela
            r = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='Julho/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=hoje - timedelta(days=dias_atras),
                user_id=u.id
            )
            db.session.add(r)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=r.id, carga=50, repeticoes=10))
            db.session.commit()

        user_id = u.id

    _login(client, u.__class__.query.get(user_id))
    resp = client.get('/api/progresso')
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data['semanas']) == 30
    assert sum(data['volumes']) == 1000.0  # só os 2 registros dentro da janela (500 + 500)