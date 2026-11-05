"""Fila offline de treinos (static/js/modules/fila-offline.js).

Sem internet, a tela de registro guarda o formulário no IndexedDB do
aparelho e reenvia depois (página ou Background Sync do service worker).
Do lado do servidor isso exige duas garantias, testadas aqui:

1. Reenviar o mesmo treino não duplica (o servidor substitui a sessão).
2. Em aparelho compartilhado, um treino guardado por uma conta nunca é
   salvo na conta de outra pessoa que esteja logada na hora do reenvio
   (campo fila_offline_user_id).
"""
from models import RegistroTreino
from tests.integration.test_routes.test_register_routes import (
    _criar_usuario, _login, _montar_versao_com_treino_e_exercicio,
)


def _payload(treino_id, chave, user_id):
    return {
        'treino': str(treino_id), 'data': '2026-01-05',
        f'carga_{chave}': '40', f'reps_{chave}': '10', f'num_series_{chave}': '3',
        'fila_offline_user_id': str(user_id),
    }


def test_reenvio_da_fila_salva_na_conta_de_quem_registrou(client, app):
    with app.app_context():
        u = _criar_usuario('fila_1')
        versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
        chave, ex_id, uid = f'u_{ex.id}', ex.id, u.id

    _login(client, 'fila_1')
    resp = client.post('/registrar/registrar-treino', data=_payload(treino_id, chave, uid))

    assert resp.status_code == 302
    assert '/registrar-treino' not in resp.headers['Location']  # o front lê isso como sucesso
    with app.app_context():
        assert RegistroTreino.query.filter_by(exercicio_usuario_id=ex_id, user_id=uid).count() == 1


def test_reenviar_o_mesmo_treino_nao_duplica(client, app):
    with app.app_context():
        u = _criar_usuario('fila_2')
        versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
        chave, ex_id, uid = f'u_{ex.id}', ex.id, u.id

    _login(client, 'fila_2')
    for _ in range(3):  # ex.: a 1ª chegou ao servidor mas a resposta se perdeu
        client.post('/registrar/registrar-treino', data=_payload(treino_id, chave, uid))

    with app.app_context():
        assert RegistroTreino.query.filter_by(exercicio_usuario_id=ex_id, user_id=uid).count() == 1


def test_treino_de_outra_conta_nao_e_salvo(client, app):
    with app.app_context():
        dono = _criar_usuario('fila_dono')
        outro = _criar_usuario('fila_outro')
        versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(outro.id)
        chave, ex_id, dono_id, outro_id = f'u_{ex.id}', ex.id, dono.id, outro.id

    _login(client, 'fila_outro')
    resp = client.post('/registrar/registrar-treino', data=_payload(treino_id, chave, dono_id))

    # volta para a tela de registro = "recusado" para a fila
    assert resp.status_code == 302
    assert '/registrar-treino' in resp.headers['Location']
    with client.session_transaction() as sess:
        avisos = [msg for _cat, msg in sess.get('_flashes', [])]
    assert any('outra conta' in m for m in avisos)
    with app.app_context():
        assert RegistroTreino.query.filter_by(exercicio_usuario_id=ex_id).count() == 0


def test_sem_o_campo_o_salvamento_normal_continua_igual(client, app):
    with app.app_context():
        u = _criar_usuario('fila_3')
        versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
        chave, ex_id, uid = f'u_{ex.id}', ex.id, u.id

    _login(client, 'fila_3')
    dados = _payload(treino_id, chave, uid)
    dados.pop('fila_offline_user_id')
    client.post('/registrar/registrar-treino', data=dados)
    with app.app_context():
        assert RegistroTreino.query.filter_by(exercicio_usuario_id=ex_id, user_id=uid).count() == 1


def test_paginas_carregam_a_fila_e_a_tela_guarda_sem_rede(client, app):
    with app.app_context():
        u = _criar_usuario('fila_4')
        versao, treino_id, ex = _montar_versao_com_treino_e_exercicio(u.id)
        uid = u.id

    _login(client, 'fila_4')
    html = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}').get_data(as_text=True)

    assert f'<meta name="fitlog-user-id" content="{uid}">' in html
    assert 'js/modules/fila-offline.js' in html
    assert 'js/modules/fila-offline-ui.js' in html
    assert 'css/fila-offline.css' in html
    assert 'data-treino-rotulo="' in html
    assert 'async function guardarTreinoNoAparelho' in html
    # falha de rede (catch do fetch) e aparelho offline caem na fila
    assert 'if (await guardarTreinoNoAparelho()) return;' in html
    assert 'navigator.onLine === false' in html


def test_deslogado_meta_de_usuario_vazia(client):
    html = client.get('/auth/login').get_data(as_text=True)
    assert '<meta name="fitlog-user-id" content="">' in html
    assert 'js/modules/fila-offline.js' in html


def test_service_worker_envia_a_fila_por_background_sync(client):
    js = client.get('/sw.js').get_data(as_text=True)
    assert "importScripts('/static/js/modules/fila-offline.js')" in js
    assert "addEventListener('sync'" in js
    assert "'/static/js/modules/fila-offline.js'," in js  # precache para a offline.html
