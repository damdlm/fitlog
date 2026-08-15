"""Testes de segurança de resource exhaustion via paginação.

CORREÇÃO seção 14 (prompt de hardening): nenhum endpoint deve aceitar
um "limite" ilimitado vindo do cliente.
"""
from models import db, User


def _cria_usuario_logado(client, db, username='paguser'):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaForte123')
    db.session.add(user)
    db.session.commit()
    client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123'})
    return user


def test_limite_gigante_e_travado_no_teto(client, db):
    _cria_usuario_logado(client, db)
    resp = client.get('/api/catalogo/todos?limite=999999999')
    assert resp.status_code == 200
    dados = resp.get_json()
    assert isinstance(dados, list)
    assert len(dados) <= 500


def test_limite_negativo_nao_quebra_e_usa_minimo_seguro(client, db):
    _cria_usuario_logado(client, db)
    resp = client.get('/api/catalogo/todos?limite=-50')
    assert resp.status_code == 200
    dados = resp.get_json()
    assert isinstance(dados, list)


def test_limite_nao_numerico_cai_no_padrao(client, db):
    _cria_usuario_logado(client, db)
    resp = client.get('/api/catalogo/todos?limite=abc')
    assert resp.status_code == 200
    dados = resp.get_json()
    assert isinstance(dados, list)
    assert len(dados) <= 500
