"""Login que sobrevive à perda do cookie de sessão (PWA reaberto).

O cookie "remember" do Flask-Login recria a sessão do zero, sem 'sv'. O
identificador "<id>.<session_version>" (User.get_id) faz a versão viajar
junto, então o login restaurado funciona -- e uma troca de senha continua
invalidando sessão e remember cookie.
"""
from flask import g
from flask_login import current_user

from models import User


def _criar_usuario(db, username):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.commit()
    return user


def _autenticado(client):
    """Faz uma requisição e diz se o Flask-Login carregou o usuário.

    O fixture `app` mantém um app context aberto, então `g` (onde o
    Flask-Login guarda o usuário já carregado) sobrevive entre requisições
    do mesmo teste -- limpamos para cada requisição recarregar do zero,
    como acontece em produção.
    """
    g.pop('_login_user', None)
    with client:
        client.get('/health')
        return current_user.is_authenticated


def test_get_id_inclui_session_version(app, db):
    user = _criar_usuario(db, 'persist_getid')
    assert user.get_id() == f"{user.id}.{user.session_version}"


def test_sessao_sem_sv_restaurada_pelo_id_novo_autentica(client, app, db):
    user = _criar_usuario(db, 'persist_remember')
    with client.session_transaction() as sess:
        sess['_user_id'] = user.get_id()  # sem 'sv', como após o remember cookie
        sess['_fresh'] = False
    assert _autenticado(client)


def test_troca_de_senha_invalida_id_antigo(client, app, db):
    user = _criar_usuario(db, 'persist_troca')
    id_antigo = user.get_id()
    user.set_password('OutraSenha456!')
    db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = id_antigo
        sess['_fresh'] = False
    assert not _autenticado(client)


def test_formato_legado_continua_exigindo_sv(client, app, db):
    user = _criar_usuario(db, 'persist_legado')
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['sv'] = user.session_version
        sess['_fresh'] = True
    assert _autenticado(client)

    with client.session_transaction() as sess:
        sess.pop('sv')
    assert not _autenticado(client)


def test_id_malformado_nao_quebra(client, app, db):
    with client.session_transaction() as sess:
        sess['_user_id'] = 'abc.xyz'
        sess['_fresh'] = False
    assert not _autenticado(client)