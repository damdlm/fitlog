"""Posição (enquadramento) da foto na página pública do professor."""
import pytest
from models import db, User
from services.professor_perfil_service import ProfessorPerfilService


def _criar_professor(username='profposicao', com_foto=True):
    user = User(
        username=username,
        email=f'{username}@teste.com',
        tipo_usuario='professor',
        nome_completo='Felipe Luis',
    )
    user.set_password('123456')
    if com_foto:
        user.professor_foto_chave = f'professores/{username}-1.jpg'
    db.session.add(user)
    db.session.commit()
    ProfessorPerfilService.garantir_slug(user)
    db.session.commit()
    return user


def _login(client, username='profposicao'):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


@pytest.fixture
def professor(app):
    with app.app_context():
        user = _criar_professor()
        yield user.id, user.professor_slug


def _salvar(client, x, y):
    return client.post(
        '/professor/pagina/foto/posicao',
        data={'foto_pos_x': x, 'foto_pos_y': y},
        follow_redirects=True,
    )


def test_padrao_e_centralizada(app, professor):
    uid, _ = professor
    user = db.session.get(User, uid)
    assert user.professor_foto_posicao_css == '50% 50%'


def test_salvar_posicao_reflete_na_pagina_publica(app, client, professor):
    uid, slug = professor
    _login(client)
    resp = _salvar(client, 30, 80)
    assert 'Posição da foto atualizada!'.encode() in resp.data
    user = db.session.get(User, uid)
    assert (user.professor_foto_pos_x, user.professor_foto_pos_y) == (30, 80)

    publico = client.get(f'/professor/pagina/{slug}')
    assert b'--pp-foto-pos: 30% 80%' in publico.data


@pytest.mark.parametrize('x,y', [(-1, 50), (50, 101), ('abc', 50), ('', ''), (50, None)])
def test_posicao_invalida_e_rejeitada(app, client, professor, x, y):
    uid, _ = professor
    _login(client)
    resp = client.post(
        '/professor/pagina/foto/posicao',
        data={k: v for k, v in (('foto_pos_x', x), ('foto_pos_y', y)) if v is not None},
        follow_redirects=True,
    )
    assert 'Posição inválida.'.encode() in resp.data
    user = db.session.get(User, uid)
    assert (user.professor_foto_pos_x, user.professor_foto_pos_y) == (50, 50)


def test_sem_foto_nao_salva_posicao(app, client):
    with app.app_context():
        user = _criar_professor('profsemfoto', com_foto=False)
        uid = user.id
    _login(client, 'profsemfoto')
    resp = _salvar(client, 20, 20)
    assert 'Envie uma foto antes de ajustar a posição.'.encode() in resp.data
    assert db.session.get(User, uid).professor_foto_pos_x == 50


def test_editar_pagina_mostra_titulo_minha_pagina(app, client, professor):
    _login(client)
    resp = client.get('/professor/pagina/editar')
    assert resp.status_code == 200
    assert b'Minha P\xc3\xa1gina' in resp.data
    assert b'ppPosicaoCirculo' in resp.data


def test_exige_login(app, client):
    resp = client.post('/professor/pagina/foto/posicao', data={'foto_pos_x': 1, 'foto_pos_y': 1})
    assert resp.status_code in (302, 401)
