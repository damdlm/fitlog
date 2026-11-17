"""Estáticos baratos de servir e de guardar em cache.

A primeira tela depois de um deploy travava segundos no celular: a versão
(?v=) mudava em TODOS os arquivos a cada deploy (mtime do build), e cada
CSS/JS carregava o usuário do banco e saía com Set-Cookie / Vary: Cookie,
então o Cloudflare não guardava nada e os ~25 arquivos iam até o servidor.
"""
import os
import re

from sqlalchemy import event


def _static_v(app, nome):
    with app.test_request_context('/'):
        return app.jinja_env.globals['static_v'](nome)


def test_versao_e_hash_do_conteudo(app):
    pasta = os.path.join(app.static_folder, 'js')
    caminho = os.path.join(pasta, '_teste_versao_tmp.js')
    try:
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write('var a = 1;')
        v1 = _static_v(app, 'js/_teste_versao_tmp.js').split('?v=')[1]
        assert re.fullmatch(r'[0-9a-f]{10}', v1)

        # Mesmo conteúdo com outro mtime (como no build do Railway): mesma versão.
        os.utime(caminho, (1, 1))
        assert _static_v(app, 'js/_teste_versao_tmp.js').endswith('?v=' + v1)

        with open(caminho, 'w', encoding='utf-8') as f:
            f.write('var a = 2;')
        assert not _static_v(app, 'js/_teste_versao_tmp.js').endswith('?v=' + v1)
    finally:
        os.remove(caminho)


def test_bibliotecas_tambem_versionadas_no_layout(client):
    html = client.get('/auth/login').get_data(as_text=True)
    assert re.search(r'/static/vendor/bootstrap/js/bootstrap\.bundle\.min\.js\?v=[0-9a-f]{10}', html)


def test_estatico_versionado_cache_de_um_ano(app, client):
    url = _static_v(app, 'js/fitlog-utils.js')
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert 'Expires' not in resp.headers


def test_estatico_sem_versao_mantem_um_dia(client):
    resp = client.get('/static/js/fitlog-utils.js')
    assert 'max-age=86400' in resp.headers['Cache-Control']
    assert 'immutable' not in resp.headers['Cache-Control']


def test_service_worker_continua_sem_cache(client):
    resp = client.get('/sw.js')
    assert 'no-cache' in resp.headers['Cache-Control']


def test_estatico_logado_sem_cookie_sem_banco(app, auth_client):
    from models import db
    consultas = []

    def contar(*_a):
        consultas.append(1)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', contar)
    try:
        resp = auth_client.get(_static_v(app, 'js/fitlog-utils.js'))
    finally:
        with app.app_context():
            event.remove(db.engine, 'before_cursor_execute', contar)

    assert resp.status_code == 200
    assert 'Set-Cookie' not in resp.headers
    assert 'Cookie' not in resp.headers.get('Vary', '')
    assert consultas == []


def test_pagina_logada_continua_usando_a_sessao(auth_client):
    resp = auth_client.get('/aluno/dashboard')
    assert 'Cookie' in resp.headers.get('Vary', '')
