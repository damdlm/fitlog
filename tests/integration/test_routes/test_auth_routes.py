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
    # '123456' não atende ao validador de senha da aplicação (mínimo 8
    # caracteres, com letra e número — ver utils/validators.validar_senha),
    # então o registro falhava silenciosamente e nunca criava o usuário.
    response = client.post('/auth/register', data={
        'username': 'testuser',
        'email': 'test@test.com',
        'password': 'Senha1234',
        'confirm_password': 'Senha1234'
    }, follow_redirects=True)

    assert response.status_code == 200

    from models import User
    user = User.query.filter_by(username='testuser').first()
    assert user is not None
    assert user.email == 'test@test.com'

    # Checagem best-effort do texto de sucesso (decodificado como string,
    # já que literais bytes não podem conter acentuação em Python).
    texto = response.get_data(as_text=True)
    assert 'Conta criada' in texto

def test_login_user(client, db):
    """Testa login de usuário"""
    # Primeiro registra (mesma observação sobre senha do teste acima)
    client.post('/auth/register', data={
        'username': 'logintest',
        'email': 'login@test.com',
        'password': 'Senha1234',
        'confirm_password': 'Senha1234'
    })

    # Depois faz login
    response = client.post('/auth/login', data={
        'username': 'logintest',
        'password': 'Senha1234'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Bem-vindo' in response.data