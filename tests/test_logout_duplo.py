"""Logout chamado duas vezes não pode desfazer o login seguinte.

Bug real (iPhone, nov/2026): o clique em "Sair" disparava dois GET
/auth/logout (fila-offline-ui.js + page-transition.js). O segundo, já
deslogado, caía em /auth/login?next=/auth/logout; o login seguinte
redirecionava para o logout e a pessoa voltava para a tela de login.
"""
from pathlib import Path

from models import User


def _criar_usuario(db, username='duplo'):
    user = User(username=username, email=f'{username}@t.com')
    user.set_password('Senha#Forte9')
    db.session.add(user)
    db.session.commit()
    return user


def _logado(client):
    with client.session_transaction() as sess:
        return bool(sess.get('_user_id'))


def test_logout_deslogado_volta_ao_login_sem_next(client, db):
    resp = client.get('/auth/logout', follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert location.endswith('/auth/login')
    assert 'next=' not in location


def test_logout_duplo_nao_desfaz_o_proximo_login(client, db):
    _criar_usuario(db)
    client.post('/auth/login', data={'username': 'duplo', 'password': 'Senha#Forte9'})
    assert _logado(client)

    client.get('/auth/logout')
    client.get('/auth/logout')  # segundo clique / segundo handler
    assert not _logado(client)

    resp = client.post('/auth/login', data={'username': 'duplo', 'password': 'Senha#Forte9'},
                       follow_redirects=False)
    assert '/auth/logout' not in resp.headers['Location']
    assert _logado(client)


def test_next_apontando_para_logout_e_ignorado(client, db):
    _criar_usuario(db, 'nextlogout')
    for nxt in ('/auth/logout', '/auth/logout/', '/auth/logout?x=1'):
        client.get('/auth/logout')
        resp = client.post(f'/auth/login?next={nxt}',
                           data={'username': 'nextlogout', 'password': 'Senha#Forte9'},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert '/auth/logout' not in resp.headers['Location']
        assert _logado(client)


def test_next_valido_continua_funcionando(client, db):
    _criar_usuario(db, 'nextok')
    resp = client.post('/auth/login?next=/auth/profile',
                       data={'username': 'nextok', 'password': 'Senha#Forte9'},
                       follow_redirects=False)
    assert resp.headers['Location'].endswith('/auth/profile')


def test_handler_de_logout_da_fila_para_a_propagacao():
    js = Path(__file__).resolve().parent.parent / 'static/js/modules/fila-offline-ui.js'
    trecho = js.read_text(encoding='utf-8').split('a[href$="/auth/logout"]', 1)[1][:600]
    assert 'e.stopPropagation()' in trecho


def test_fechar_alerta_protege_contra_close_duplo():
    html = Path(__file__).resolve().parent.parent / 'templates/base.html'
    assert 'el.dataset.fechando' in html.read_text(encoding='utf-8')