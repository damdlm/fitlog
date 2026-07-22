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


def test_reset_password_request_page(client):
    """Testa se página de solicitação de reset carrega"""
    response = client.get('/auth/reset-password-request')
    assert response.status_code == 200


def test_reset_password_request_email_existente(client, db):
    """Solicitar reset para e-mail cadastrado deve retornar a mesma
    mensagem genérica de sucesso (sem revelar se o e-mail existe)."""
    from models import User
    user = User(username='resetuser', email='reset@test.com')
    user.set_password('SenhaAntiga123')
    db.session.add(user)
    db.session.commit()

    response = client.post('/auth/reset-password-request',
                            data={'email': 'reset@test.com'},
                            follow_redirects=True)
    assert response.status_code == 200
    assert 'link de redefinição' in response.get_data(as_text=True)


def test_reset_password_request_email_inexistente(client, db):
    """Solicitar reset para e-mail não cadastrado deve dar a MESMA
    resposta genérica (protege contra user enumeration)."""
    response = client.post('/auth/reset-password-request',
                            data={'email': 'naoexiste@test.com'},
                            follow_redirects=True)
    assert response.status_code == 200
    assert 'link de redefinição' in response.get_data(as_text=True)


def test_reset_password_com_token_valido(client, db):
    """Fluxo completo: token válido troca a senha, e a senha antiga
    deixa de funcionar."""
    from models import User
    user = User(username='tokenuser', email='token@test.com')
    user.set_password('SenhaAntiga123')
    db.session.add(user)
    db.session.commit()

    token = user.get_reset_token()

    get_resp = client.get(f'/auth/reset-password/{token}')
    assert get_resp.status_code == 200

    post_resp = client.post(f'/auth/reset-password/{token}', data={
        'password': 'SenhaNova456',
        'confirm_password': 'SenhaNova456',
    }, follow_redirects=True)
    assert post_resp.status_code == 200

    user_atualizado = User.query.filter_by(username='tokenuser').first()
    assert user_atualizado.check_password('SenhaNova456') is True
    assert user_atualizado.check_password('SenhaAntiga123') is False


def test_reset_password_com_token_invalido(client):
    """Token inválido/adulterado deve redirecionar para a solicitação,
    sem quebrar a aplicação."""
    response = client.get('/auth/reset-password/token-adulterado-qualquer',
                           follow_redirects=True)
    assert response.status_code == 200
    assert 'inválido' in response.get_data(as_text=True) or 'expirou' in response.get_data(as_text=True)


def test_reset_password_token_nao_pode_ser_reusado(client, db):
    """Depois que a senha já foi trocada, o mesmo token não pode ser
    usado de novo (ele embute o hash da senha antiga)."""
    from models import User
    user = User(username='reuseuser', email='reuse@test.com')
    user.set_password('SenhaAntiga123')
    db.session.add(user)
    db.session.commit()

    token = user.get_reset_token()

    client.post(f'/auth/reset-password/{token}', data={
        'password': 'SenhaNova456',
        'confirm_password': 'SenhaNova456',
    })

    response = client.get(f'/auth/reset-password/{token}', follow_redirects=True)
    texto = response.get_data(as_text=True)
    assert 'inválido' in texto or 'expirou' in texto


def test_reset_password_senhas_nao_coincidem(client, db):
    """Se a confirmação de senha não bater, a senha não deve ser alterada."""
    from models import User
    user = User(username='mismatchuser', email='mismatch@test.com')
    user.set_password('SenhaAntiga123')
    db.session.add(user)
    db.session.commit()

    token = user.get_reset_token()

    response = client.post(f'/auth/reset-password/{token}', data={
        'password': 'SenhaNova456',
        'confirm_password': 'SenhaDiferente789',
    }, follow_redirects=True)

    assert response.status_code == 200
    user_atualizado = User.query.filter_by(username='mismatchuser').first()
    assert user_atualizado.check_password('SenhaAntiga123') is True