"""Testes do estilo visual da página pública do professor:
escolha na tela de edição, renderização do CSS/HTML do estilo salvo,
fallback pra estilo desconhecido e prévia (?estilo=) só pro dono."""
import pytest
from models import db, User
from services.professor_perfil_service import (
    ESTILOS_PAGINA, ESTILO_PAGINA_PADRAO, ProfessorPerfilService,
)


def _criar_professor(username='profestilo'):
    user = User(
        username=username,
        email=f'{username}@teste.com',
        tipo_usuario='professor',
        nome_completo='Felipe Luis',
    )
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    ProfessorPerfilService.garantir_slug(user)
    db.session.commit()
    return user


def _login(client, username='profestilo'):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


@pytest.fixture
def professor(app):
    with app.app_context():
        user = _criar_professor()
        yield user.id, user.professor_slug


def _salvar(client, **campos):
    return client.post('/professor/pagina/editar', data=campos, follow_redirects=True)


def test_padrao_e_diagonal(app, client, professor):
    _, slug = professor
    resp = client.get(f'/professor/pagina/{slug}')
    assert resp.status_code == 200
    assert b'professor-estilos/diagonal.css' in resp.data
    assert b'professor-estilos/textura.css' not in resp.data
    assert ESTILO_PAGINA_PADRAO == 'diagonal'


def test_salvar_estilo_textura_reflete_na_pagina_publica(app, client, professor):
    uid, slug = professor
    _login(client)
    resp = _salvar(client, estilo_pagina='textura')
    assert 'Página atualizada com sucesso!'.encode() in resp.data
    assert db.session.get(User, uid).professor_estilo_pagina == 'textura'

    publico = client.get(f'/professor/pagina/{slug}')
    assert b'professor-estilos/textura.css' in publico.data
    assert b'professor-estilos/diagonal.css' not in publico.data
    # o partial do estilo Textura tem as faixas diagonais exclusivas dele
    assert b'pp-diagonal-a' in publico.data


def test_estilo_invalido_e_rejeitado_e_nao_altera(app, client, professor):
    uid, _ = professor
    _login(client)
    resp = _salvar(client, estilo_pagina='../../etc/passwd')
    assert 'Estilo de página inválido.'.encode() in resp.data
    assert db.session.get(User, uid).professor_estilo_pagina == 'diagonal'


def test_formulario_sem_campo_estilo_mantem_o_atual(app, client, professor):
    uid, _ = professor
    _login(client)
    _salvar(client, estilo_pagina='textura')
    _salvar(client, tagline='Só mudei a frase')  # sem estilo_pagina
    usuario = db.session.get(User, uid)
    assert usuario.professor_tagline == 'Só mudei a frase'
    assert usuario.professor_estilo_pagina == 'textura'


def test_estilo_desconhecido_no_banco_cai_no_padrao(app, client, professor):
    uid, slug = professor
    usuario = db.session.get(User, uid)
    usuario.professor_estilo_pagina = 'estilo_removido'
    db.session.commit()
    resp = client.get(f'/professor/pagina/{slug}')
    assert resp.status_code == 200
    assert b'professor-estilos/diagonal.css' in resp.data


def test_previa_so_vale_para_o_dono(app, client, professor):
    _, slug = professor
    # visitante anônimo: ?estilo= é ignorado
    anonimo = client.get(f'/professor/pagina/{slug}?embed=1&estilo=textura')
    assert b'professor-estilos/diagonal.css' in anonimo.data
    assert b'professor-estilos/textura.css' not in anonimo.data

    # dono: a prévia mostra o estilo pedido, sem gravar nada
    _login(client)
    dono = client.get(f'/professor/pagina/{slug}?embed=1&estilo=textura')
    assert b'professor-estilos/textura.css' in dono.data
    assert db.session.get(User, professor[0]).professor_estilo_pagina == 'diagonal'

    # dono com chave inválida: cai no estilo salvo
    invalido = client.get(f'/professor/pagina/{slug}?embed=1&estilo=xpto')
    assert b'professor-estilos/diagonal.css' in invalido.data


def test_tela_de_edicao_lista_todos_os_estilos(app, client, professor):
    _login(client)
    resp = client.get('/professor/pagina/editar')
    assert resp.status_code == 200
    for chave, estilo in ESTILOS_PAGINA.items():
        assert f'value="{chave}"'.encode() in resp.data
        assert estilo['rotulo'].encode() in resp.data
    assert b'name="estilo_pagina"' in resp.data


def test_arquivos_de_cada_estilo_existem():
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    for estilo in ESTILOS_PAGINA.values():
        if estilo.get('base'):
            assert os.path.isfile(os.path.join(raiz, 'static', estilo['base'])), estilo['base']
        assert os.path.isfile(os.path.join(raiz, 'static', estilo['css'])), estilo['css']
        assert os.path.isfile(os.path.join(raiz, 'templates', estilo['template'])), estilo['template']


@pytest.mark.parametrize('chave', list(ESTILOS_PAGINA))
def test_cada_estilo_renderiza_com_seu_css_html_e_base(app, client, professor, chave):
    """Todos os estilos registrados renderizam a página pública (normal e
    embed) com o CSS do estilo, o CSS base quando o estilo declara um, e
    nunca carregam o CSS de outro estilo."""
    uid, slug = professor
    _login(client)
    assert 'Página atualizada com sucesso!'.encode() in _salvar(client, estilo_pagina=chave).data
    info = ESTILOS_PAGINA[chave]

    for url in (f'/professor/pagina/{slug}', f'/professor/pagina/{slug}?embed=1'):
        resp = client.get(url)
        assert resp.status_code == 200, (chave, url)
        assert info['css'].encode() in resp.data
        if info.get('base'):
            assert info['base'].encode() in resp.data
            # a base precisa vir ANTES do CSS do estilo
            assert resp.data.index(info['base'].encode()) < resp.data.index(info['css'].encode())
        for outra, outra_info in ESTILOS_PAGINA.items():
            if outra != chave:
                assert outra_info['css'].encode() not in resp.data, (chave, outra)
        assert b'FELIPE' in resp.data and b'LUIS' in resp.data


def test_estilos_moderno_e_esportivo_tem_marcadores_proprios(app, client, professor):
    _, slug = professor
    _login(client)
    _salvar(client, estilo_pagina='moderno')
    assert b'pp-poster-estilo-2' in client.get(f'/professor/pagina/{slug}').data
    _salvar(client, estilo_pagina='esportivo')
    assert b'pp-poster-estilo-5' in client.get(f'/professor/pagina/{slug}').data
