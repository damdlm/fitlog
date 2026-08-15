"""Testes de segurança do fluxo de reset de senha.

CORREÇÃO 9 (prompt de hardening): token aleatório, hash armazenado no
banco (nunca o token em si), expira, é de uso único e não contém o
password_hash do usuário.
"""
from datetime import datetime, timezone, timedelta

from models import db, User, PasswordResetToken


def _cria_usuario(db, username='resetuser'):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaAntiga123')
    db.session.add(user)
    db.session.commit()
    return user


def test_token_gerado_e_imprevisivel_e_nao_contem_hash_da_senha(app, db):
    with app.app_context():
        user = _cria_usuario(db)
        token = user.get_reset_token()
        db.session.commit()

        # O token não pode conter o hash de senha (nem em base64) --
        # diferente da implementação antiga baseada em itsdangerous.
        assert user.password_hash not in token
        # Token aleatório de 32 bytes -> bem maior que um id sequencial
        assert len(token) >= 32

        # O banco guarda só o hash SHA-256 do token, nunca o token cru
        registro = PasswordResetToken.query.filter_by(user_id=user.id).first()
        assert registro is not None
        assert registro.token_hash != token
        assert len(registro.token_hash) == 64  # sha256 hex digest


def test_token_valido_resolve_para_o_usuario_correto(app, db):
    with app.app_context():
        user = _cria_usuario(db)
        token = user.get_reset_token()
        db.session.commit()

        resolvido = User.verify_reset_token(token)
        assert resolvido is not None
        assert resolvido.id == user.id


def test_token_invalido_nao_resolve(app, db):
    with app.app_context():
        _cria_usuario(db)
        assert User.verify_reset_token('token-que-nao-existe') is None
        assert User.verify_reset_token('') is None
        assert User.verify_reset_token(None) is None


def test_token_expirado_nao_resolve(app, db):
    with app.app_context():
        user = _cria_usuario(db)
        token = user.get_reset_token(expires_sec=1800)
        db.session.commit()

        # Simula o token já expirado
        registro = PasswordResetToken.query.filter_by(user_id=user.id).first()
        registro.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()

        assert User.verify_reset_token(token) is None


def test_token_e_de_uso_unico(app, db):
    """Fluxo completo: token válido -> usado -> não pode ser reusado."""
    with app.app_context():
        user = _cria_usuario(db)
        token = user.get_reset_token()
        db.session.commit()

        assert User.verify_reset_token(token) is not None

        User.invalidate_reset_token(token)
        db.session.commit()

        assert User.verify_reset_token(token) is None


def test_fluxo_reset_via_rotas_invalida_token_apos_uso(client, db):
    """Fim a fim: solicitar reset -> trocar senha -> tentar reusar o
    mesmo link -> deve falhar."""
    user = _cria_usuario(db, username='fimafim')

    resp = client.post('/auth/reset-password-request', data={'email': user.email},
                        follow_redirects=True)
    assert resp.status_code == 200

    registro = PasswordResetToken.query.filter_by(user_id=user.id).first()
    assert registro is not None

    # Não temos o token cru aqui (só o hash foi persistido) -- geramos
    # um novo via get_reset_token para simular o link que teria sido
    # enviado por e-mail, e testamos o ciclo de vida completo por ele.
    token = user.get_reset_token()
    db.session.commit()

    resp = client.post(f'/auth/reset-password/{token}', data={
        'password': 'SenhaNovaForte123',
        'confirm_password': 'SenhaNovaForte123',
    }, follow_redirects=True)
    assert resp.status_code == 200

    # Login com a senha nova deve funcionar
    resp = client.post('/auth/login', data={
        'username': user.username,
        'password': 'SenhaNovaForte123',
    }, follow_redirects=True)
    assert resp.status_code == 200

    # Precisa deslogar antes de tentar reusar o link -- a rota de reset
    # redireciona usuários já autenticados direto pra home, então o
    # teste precisaria estar deslogado pra realmente exercitar o
    # branch de "token inválido/já usado".
    client.get('/auth/logout')

    # Reusar o mesmo link de reset não deve mais funcionar -- a rota
    # detecta token inválido/já usado e redireciona de volta para a
    # tela de solicitar um novo link.
    resp2 = client.get(f'/auth/reset-password/{token}', follow_redirects=False)
    assert resp2.status_code == 302
    assert '/auth/reset-password-request' in resp2.headers['Location']
