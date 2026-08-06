from datetime import date
from models import db, User, VersaoGlobal, Treino, TreinoVersao


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def test_adicionar_treino_sem_cadastro_previo_aluno(client, app):
    with app.app_context():
        u = User(username='teste_auto', email='teste_auto@x.com', tipo_usuario='aluno', nome_completo='Teste')
        u.set_password('123456')
        db.session.add(u)
        db.session.commit()
        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC', data_inicio=date.today(), user_id=u.id)
        db.session.add(versao)
        db.session.commit()
        versao_id = versao.id
        assert Treino.query.filter_by(user_id=u.id).count() == 0

    _login(client, 'teste_auto')

    resp = client.get(f'/aluno/versao/{versao_id}/treino/novo')
    assert resp.status_code == 200
    assert b'letra-A' in resp.data

    resp = client.post(f'/aluno/versao/{versao_id}/treino/novo', data={
        'treino_id': 'A',
        'nome_treino': 'Treino A - Peito',
        'descricao_treino': 'foco peito',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        treino = Treino.query.filter_by(codigo='A').first()
        assert treino is not None
        tv = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        assert tv is not None
        assert tv.nome_treino == 'Treino A - Peito'


def test_adicionar_treino_sem_cadastro_previo_professor(client, app):
    with app.app_context():
        professor = User(username='prof_auto', email='prof_auto@x.com', tipo_usuario='professor', nome_completo='Prof')
        professor.set_password('123456')
        aluno = User(username='aluno_auto', email='aluno_auto@x.com', tipo_usuario='aluno', nome_completo='Aluno')
        aluno.set_password('123456')
        db.session.add_all([professor, aluno])
        db.session.commit()
        from models import AlunoProfessor
        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC', data_inicio=date.today(), user_id=aluno.id)
        db.session.add(versao)
        db.session.commit()
        versao_id = versao.id
        aluno_id = aluno.id
        assert Treino.query.filter_by(user_id=aluno.id).count() == 0

    _login(client, 'prof_auto')

    resp = client.get(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo')
    assert resp.status_code == 200
    assert b'letra-A' in resp.data

    resp = client.post(f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/novo', data={
        'treino_id': 'B',
        'nome_treino': 'Treino B - Costas',
        'descricao_treino': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        treino = Treino.query.filter_by(user_id=aluno_id, codigo='B').first()
        assert treino is not None
        tv = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        assert tv is not None
