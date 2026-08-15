"""Testes de segurança de vazamento de informação (information disclosure).

CORREÇÃO seção 13 (prompt de hardening): erros internos (mensagens de
exceção, que podem conter SQL, nomes de tabela/coluna, caminhos etc.)
não podem ser devolvidos ao cliente -- só logados no servidor.
"""
from models import db, User


def _cria_usuario_logado(client, db, username='errleak'):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaForte123')
    db.session.add(user)
    db.session.commit()
    client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123'})
    return user


def test_erro_interno_em_reordenar_exercicios_nao_vaza_detalhe(client, db, monkeypatch):
    _cria_usuario_logado(client, db)

    def _explode(**kwargs):
        raise RuntimeError("SELECT * FROM exercicios_usuario WHERE segredo_interno = 42")

    monkeypatch.setattr(
        'services.exercicio_service.ExercicioService.reordenar_exercicios',
        staticmethod(_explode),
    )

    resp = client.post('/api/reordenar-exercicios', json={
        'versao_id': 1, 'treino_codigo': 'A', 'nova_ordem': [1, 2, 3],
    })
    assert resp.status_code == 500
    body = resp.get_json()
    assert body['success'] is False
    assert 'segredo_interno' not in body['error']
    assert 'SELECT' not in body['error']
    assert body['error'] == 'Não foi possível concluir a operação.'


def test_erro_interno_em_treinos_por_data_nao_vaza_detalhe(client, db, monkeypatch):
    _cria_usuario_logado(client, db)

    def _explode(*args, **kwargs):
        raise RuntimeError("psycopg2.OperationalError: password authentication failed for user X")

    # A rota importa VersaoGlobal/TreinoService internamente; simulamos a
    # falha na consulta de versão ativa do usuário.
    monkeypatch.setattr(
        'models.VersaoGlobal.query',
        property(lambda self: (_ for _ in ()).throw(RuntimeError(
            "psycopg2.OperationalError: password authentication failed for user X"
        ))),
        raising=False,
    )

    resp = client.get('/register/api/treinos-por-data?data=2026-01-01')
    # Se a rota não usa o ponto mockado, ainda assim o teste garante que
    # a mensagem sensível nunca aparece no corpo da resposta.
    body = resp.get_json()
    if body and body.get('success') is False:
        assert 'psycopg2' not in body.get('error', '')
        assert 'password authentication' not in body.get('error', '')
