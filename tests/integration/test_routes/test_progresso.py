from datetime import datetime, timedelta, timezone
from models import db, User, TreinoVersao, VersaoGlobal, RegistroTreino, HistoricoTreino, Musculo, ExercicioUsuario
from services.billing_service import BillingService


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def test_progresso_sem_registro_retorna_vazio(client, app):
    with app.app_context():
        u = User(username='sem_treino_pt', email='sem_pt@t.com', tipo_usuario='aluno')
        u.set_password('x' * 12)
        db.session.add(u)
        db.session.flush()
        BillingService.iniciar_trial(u)
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
        db.session.flush()
        BillingService.iniciar_trial(u)
        db.session.commit()

        m = Musculo(nome='peito_pt', nome_exibicao='Peito')
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

        treino = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A', descricao_treino='desc')
        db.session.add(treino)
        db.session.commit()

        hoje = datetime.now(timezone.utc)
        for dias_atras in [0, 5, 40]:  # 40 deve ficar fora da janela
            r = RegistroTreino(
                treino_versao_id=treino.id, versao_id=versao.id, periodo='Julho/2026', semana=1,
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


def test_progresso_todos_ignora_versoes_encerradas(client, app):
    """'Todos' (sem treino selecionado) deve somar só a versão corrente
    (ativa) do usuário -- registros de uma versão já encerrada (mesmo
    dentro dos últimos 30 dias) não podem entrar na conta."""
    with app.app_context():
        u = User(username='com_versao_encerrada_pt', email='versao_encerrada_pt@t.com', tipo_usuario='aluno')
        u.set_password('x' * 12)
        db.session.add(u)
        db.session.flush()
        BillingService.iniciar_trial(u)
        db.session.commit()

        m = Musculo(nome='costas_pt', nome_exibicao='Costas')
        db.session.add(m)
        db.session.commit()

        ex = ExercicioUsuario(usuario_id=u.id, nome='Remada', musculo_id=m.id)
        db.session.add(ex)
        db.session.commit()

        hoje = datetime.now(timezone.utc)

        # Versão ENCERRADA (data_fim preenchida) -- não pode entrar no "Todos"
        versao_antiga = VersaoGlobal(
            numero_versao=1, descricao='v1 (encerrada)', divisao='A',
            data_inicio=(hoje - timedelta(days=10)).date(),
            data_fim=(hoje - timedelta(days=2)).date(),
            user_id=u.id
        )
        db.session.add(versao_antiga)
        db.session.commit()

        treino_antigo = TreinoVersao(versao_id=versao_antiga.id, codigo='A', nome_treino='Treino A', descricao_treino='desc')
        db.session.add(treino_antigo)
        db.session.commit()

        r_antigo = RegistroTreino(
            treino_versao_id=treino_antigo.id, versao_id=versao_antiga.id, periodo='Julho/2026', semana=1,
            exercicio_usuario_id=ex.id, data_registro=hoje - timedelta(days=5),
            user_id=u.id
        )
        db.session.add(r_antigo)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=r_antigo.id, carga=999, repeticoes=1))
        db.session.commit()

        # Versão CORRENTE (ativa, sem data_fim)
        versao_atual = VersaoGlobal(
            numero_versao=2, descricao='v2 (corrente)', divisao='B',
            data_inicio=(hoje - timedelta(days=1)).date(),
            user_id=u.id
        )
        db.session.add(versao_atual)
        db.session.commit()

        treino_atual = TreinoVersao(versao_id=versao_atual.id, codigo='B', nome_treino='Treino B', descricao_treino='desc')
        db.session.add(treino_atual)
        db.session.commit()

        r_atual = RegistroTreino(
            treino_versao_id=treino_atual.id, versao_id=versao_atual.id, periodo='Julho/2026', semana=1,
            exercicio_usuario_id=ex.id, data_registro=hoje,
            user_id=u.id
        )
        db.session.add(r_atual)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=r_atual.id, carga=50, repeticoes=10))
        db.session.commit()

        user_id = u.id

    _login(client, u.__class__.query.get(user_id))
    resp = client.get('/api/progresso')
    data = resp.get_json()
    assert resp.status_code == 200
    # Só o registro da versão corrente (50*10=500) -- os 999 da versão
    # encerrada não podem entrar, mesmo estando dentro da janela de 30 dias.
    assert sum(data['volumes']) == 500.0