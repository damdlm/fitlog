"""Testes de segurança relacionados a autenticação e privilege escalation.

CORREÇÃO 1 (prompt de hardening): o primeiro usuário público cadastrado
não deve receber privilégio administrativo automaticamente. O bootstrap
do admin é feito exclusivamente por routes/../app.py via ADMIN_PASSWORD.
"""
from models import User


def test_primeiro_usuario_registrado_nao_vira_admin(client, db):
    """Usuário público se registra -> usuário NÃO é admin, mesmo sendo
    o primeiro cadastro feito pela tela pública (o app já cria um admin
    de bootstrap via ADMIN_PASSWORD na inicialização -- ver app.py)."""
    response = client.post('/auth/register', data={
        'username': 'primeirousuario',
        'email': 'primeiro@teste.com',
        'password': 'Senha1234',
        'confirm_password': 'Senha1234',
        'aceite_termos': 'on',
    }, follow_redirects=True)

    assert response.status_code == 200

    user = User.query.filter_by(username='primeirousuario').first()
    assert user is not None
    assert user.is_admin is False


def test_primeiro_usuario_registrado_como_aluno_nao_vira_professor(client, db):
    """O tipo de usuário escolhido no cadastro deve ser respeitado,
    mesmo sendo o primeiro registro do banco."""
    response = client.post('/auth/register', data={
        'username': 'alunoum',
        'email': 'alunoum@teste.com',
        'password': 'Senha1234',
        'confirm_password': 'Senha1234',
        'tipo_usuario': 'aluno',
        'aceite_termos': 'on',
    }, follow_redirects=True)

    assert response.status_code == 200
    user = User.query.filter_by(username='alunoum').first()
    assert user is not None
    assert user.tipo_usuario == 'aluno'
    assert user.is_admin is False


def test_multiplos_registros_nenhum_vira_admin(client, db):
    """Vários cadastros em sequência (simulando registros concorrentes)
    -- nenhum deve receber is_admin=True."""
    for i in range(3):
        client.post('/auth/register', data={
            'username': f'usuario{i}',
            'email': f'usuario{i}@teste.com',
            'password': 'Senha1234',
            'confirm_password': 'Senha1234',
            'aceite_termos': 'on',
        }, follow_redirects=True)

    usuarios_publicos = User.query.filter(User.username.in_(
        ['usuario0', 'usuario1', 'usuario2']
    )).all()
    assert len(usuarios_publicos) == 3
    assert all(u.is_admin is False for u in usuarios_publicos)
