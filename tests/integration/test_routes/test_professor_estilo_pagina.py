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
    assert b'pp-textura-linhas' in publico.data


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
    assert b'<select' in resp.data and b'name="estilo_pagina"' in resp.data


def test_tela_de_edicao_marca_o_estilo_salvo_como_selecionado(app, client, professor):
    _login(client)
    _salvar(client, estilo_pagina='esportivo')
    html = client.get('/professor/pagina/editar').get_data(as_text=True)
    import re
    selecionadas = re.findall(r'<option value="(\w+)"[^>]*?selected', html, re.S)
    assert selecionadas == ['esportivo']


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
    _salvar(client, estilo_pagina='glow')
    assert b'pp-poster-feminino' in client.get(f'/professor/pagina/{slug}').data


@pytest.mark.parametrize('chave', list(ESTILOS_PAGINA))
def test_estilos_novos_mostram_icones_e_avaliacao_em_uma_linha(app, client, professor, chave):
    """Estilos no formato dos mockups: cartão com ícone + título (sem a
    descrição), nome em uma linha e texto de avaliação 'de alunos'."""
    uid, slug = professor
    usuario = db.session.get(User, uid)
    usuario.professor_especialidades = ['emagrecimento', 'hipertrofia', 'reabilitacao']
    usuario.professor_estilo_pagina = chave
    db.session.commit()
    html = client.get(f'/professor/pagina/{slug}').get_data(as_text=True)
    assert html.count('class="pp-service-icon pp-service-icon-') == 3
    assert 'Foco em queima de gordura' not in html  # descrição não aparece nesses estilos
    assert 'pp-name-first' in html and 'pp-name-last' in html


def test_servicos_destaque_traz_a_chave_de_cada_servico(app, professor):
    uid, _ = professor
    usuario = db.session.get(User, uid)
    usuario.professor_especialidades = ['hipertrofia']
    db.session.commit()
    servicos = ProfessorPerfilService.servicos_destaque(usuario)
    assert [s['chave'] for s in servicos] == ['hipertrofia', 'presencial', 'online']
    assert all(s['titulo'] and s['descricao'] for s in servicos)


def test_icones_de_todas_as_chaves_renderizam_svg(app):
    from flask import render_template_string
    chaves = ['emagrecimento', 'hipertrofia', 'reabilitacao', 'terceira_idade',
              'presencial', 'online', 'avaliacao', 'chave_desconhecida']
    with app.test_request_context():
        for chave in chaves:
            html = render_template_string(
                '{% from "professor/estilos/_macros.html" import icone_servico %}{{ icone_servico(k) }}',
                k=chave,
            )
            assert '<svg' in html and 'pp-service-icon' in html, chave


def test_assets_dos_estilos_existem():
    import os, re
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    pasta_css = os.path.join(raiz, 'static', 'css', 'professor-estilos')
    for nome in os.listdir(pasta_css):
        if not nome.endswith('.css'):
            continue
        css = open(os.path.join(pasta_css, nome), encoding='utf-8').read()
        for rel in re.findall(r"url\('(\.\./\.\./[^')]+)'\)", css):
            assert os.path.isfile(os.path.normpath(os.path.join(pasta_css, rel))), f'{nome}: {rel}'


@pytest.mark.parametrize('chave', list(ESTILOS_PAGINA))
def test_logo_do_fitlog_e_sobre_mim_dentro_do_poster(app, client, professor, chave):
    """Todos os estilos (inclusive o padrão, Dedicação): logo do FitLog no pôster e
    "Sobre mim" DENTRO do mesmo cartão (antes do </article>)."""
    uid, slug = professor
    usuario = db.session.get(User, uid)
    usuario.professor_bio = 'Bio de teste do professor.'
    usuario.professor_especialidades = ['hipertrofia']
    usuario.professor_estilo_pagina = chave
    db.session.commit()

    for url, em_embed in ((f'/professor/pagina/{slug}', False), (f'/professor/pagina/{slug}?embed=1', True)):
        html = client.get(url).get_data(as_text=True)
        assert 'class="pp-brand"' in html and 'images/logo-poster.png' in html, (chave, url)
        # normal: a logo leva pra home; no preview (iframe) é só imagem
        assert ('<a class="pp-brand"' in html) is (not em_embed), (chave, url)
        assert 'professor-estilos/comum.css' in html
        fim_poster = html.index('</article>')
        assert html.index('Sobre mim') < fim_poster, chave
        assert html.index('Bio de teste do professor.') < fim_poster, chave


NOMES_DOS_ESTILOS = {
    'diagonal': 'Dedicação',
    'textura': 'Disciplina',
    'moderno': 'Equilíbrio',
    'esportivo': 'Superação',
    'glow': 'Vitalidade',
}


def test_nomes_dos_estilos_na_tela_de_edicao(app, client, professor):
    """O professor vê os nomes dos temas (Dedicação, Disciplina, Equilíbrio,
    Superação e Vitalidade); as chaves internas gravadas no banco não mudam."""
    assert {c: e['rotulo'] for c, e in ESTILOS_PAGINA.items()} == NOMES_DOS_ESTILOS
    assert ESTILO_PAGINA_PADRAO == 'diagonal'
    _login(client)
    html = client.get('/professor/pagina/editar').get_data(as_text=True)
    for chave, nome in NOMES_DOS_ESTILOS.items():
        assert f'value="{chave}"' in html and f'>{nome}</option>' in html, chave
    for antigo in ('Default', 'Diagonal', 'Textura', 'Moderno', 'Esportivo', 'Glow'):
        assert f'>{antigo}</option>' not in html, antigo


@pytest.mark.parametrize('chave', list(ESTILOS_PAGINA))
def test_fitlog_vip_aparece_antes_do_instagram_do_professor(app, client, professor, chave):
    """Em todos os estilos, o @fitlog.vip vem ANTES do @ do professor; sem
    Instagram informado, a linha de redes não aparece."""
    uid, slug = professor
    usuario = db.session.get(User, uid)
    usuario.professor_estilo_pagina = chave
    usuario.professor_instagram = None
    db.session.commit()
    html = client.get(f'/professor/pagina/{slug}').get_data(as_text=True)
    assert '@fitlog.vip' not in html

    usuario.professor_instagram = 'felipeluis'
    db.session.commit()
    html = client.get(f'/professor/pagina/{slug}').get_data(as_text=True)
    assert html.count('@fitlog.vip') == 1
    assert 'href="https://instagram.com/fitlog.vip"' in html
    assert html.index('@fitlog.vip') < html.index('@felipeluis')


def test_modal_ver_pagina_tem_botao_compartilhar_abaixo_do_fechar(app, client, professor):
    """O modal 'Ver página' tem o botão Compartilhar logo depois do X, com o
    link público do professor (não o ?embed=1) e o menu de redes."""
    uid, slug = professor
    _login(client)
    html = client.get('/professor/pagina/editar').get_data(as_text=True)
    assert 'id="ppShareModalBtn"' in html
    assert html.index('epp-preview-close') < html.index('id="ppShareModalBtn"')
    assert f'data-share-url="http://localhost/professor/pagina/{slug}"' in html
    assert 'data-share-template="http://localhost/professor/pagina/__SLUG__"' in html
    assert 'embed=1' not in html.split('data-share-url=')[1].split('"')[1]
    # compartilha a IMAGEM do pôster; o link fica como opção secundária
    for canal in ('baixar', 'copiar-imagem', 'whatsapp', 'copiar'):
        assert f'data-canal="{canal}"' in html


def test_base_css_define_formato_stories_9_16():
    """Todos os estilos que usam o base.css herdam o pôster 9:16 (Stories)."""
    import pathlib
    css = pathlib.Path('static/css/professor-estilos/base.css').read_text(encoding='utf-8')
    assert 'min-height: calc(100cqw * 16 / 9)' in css
    assert 'aspect-ratio: 9 / 16' in css  # fallback sem container queries
    diag = pathlib.Path('static/css/professor-estilos/diagonal.css').read_text(encoding='utf-8')
    assert 'min-height: calc(100cqw * 16 / 9)' in diag


def test_embed_carrega_gerador_de_imagem_do_poster(app, client, professor):
    """O iframe do modal precisa trazer o gerador da imagem 1080x1920 (e a
    biblioteca vendorizada), que o botão Compartilhar chama."""
    import pathlib
    uid, slug = professor
    html = client.get(f'/professor/pagina/{slug}?embed=1').get_data(as_text=True)
    assert 'vendor/html-to-image/html-to-image.js' in html
    assert 'js/professor-pagina-imagem.js' in html
    # fora do embed (página pública normal) não carrega nada disso
    normal = client.get(f'/professor/pagina/{slug}').get_data(as_text=True)
    assert 'professor-pagina-imagem.js' not in normal
    assert pathlib.Path('static/vendor/html-to-image/html-to-image.js').exists()
    assert pathlib.Path('static/vendor/html-to-image/LICENSE').exists()
    js = pathlib.Path('static/js/professor-pagina-imagem.js').read_text(encoding='utf-8')
    assert 'LARGURA = 1080' in js and 'ALTURA = 1920' in js
    # comentários HTML com "--" quebram o SVG da captura: têm que ser filtrados
    assert 'nodeType !== 8' in js