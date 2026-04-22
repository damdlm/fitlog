"""Testes para rotas de autenticação"""

def test_login_page(client):
    """Testa se página de login carrega"""
    response = client.get('/auth/login')
    assert response.status_code == 200
    assert b'Login' in response.data

def test_register_page(client):
    """Testa se página de registro carrega"""
    response = client.get('/auth/register')
    assert response.status_code == 200
    assert b'Criar Conta' in response.data

def test_register_user(client, db):
    """Testa registro de usuário"""
    response = client.post('/auth/register', data={
        'username': 'testuser',
        'email': 'test@test.com',
        'password': '123456',
        'confirm_password': '123456'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Usuário criado com sucesso' in response.data

def test_login_user(client, db):
    """Testa login de usuário"""
    # Primeiro registra
    client.post('/auth/register', data={
        'username': 'logintest',
        'email': 'login@test.com',
        'password': '123456',
        'confirm_password': '123456'
    })
    
    # Depois faz login
    response = client.post('/auth/login', data={
        'username': 'logintest',
        'password': '123456'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Bem-vindo' in response.data