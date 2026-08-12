"""Testes da tela de Contato: renderização, autenticação, envio de mensagem e transcrição de áudio."""
import io


def test_pagina_contato_renderiza(auth_client):
    resp = auth_client.get('/contato/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Reporte algum erro' in html
    assert 'Faça uma crítica' in html
    assert 'Faça um elogio' in html
    assert 'Queremos te ouvir e melhorar para vc!' in html
    assert 'ctMicBtn' in html
    assert 'ctBtnEnviar' in html


def test_contato_requer_login(client):
    resp = client.get('/contato/', follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_enviar_mensagem_sem_texto_falha(auth_client):
    resp = auth_client.post('/contato/enviar', json={'mensagem': '   '})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False


def test_enviar_mensagem_com_texto_ok(auth_client):
    # Sem RESEND_API_KEY configurada no ambiente de teste, o e-mail só é
    # logado (não enviado de verdade) -- mesmo assim o fluxo deve retornar
    # ok=True (mesmo comportamento gracioso do reset de senha existente).
    resp = auth_client.post('/contato/enviar', json={'mensagem': 'Adorei o app, só achei um bug no calendário.'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True


def test_enviar_mensagem_muito_longa_falha(auth_client):
    resp = auth_client.post('/contato/enviar', json={'mensagem': 'x' * 5000})
    assert resp.status_code == 400


def test_transcrever_sem_audio_falha(auth_client):
    resp = auth_client.post('/contato/transcrever', data={})
    assert resp.status_code == 400


def test_transcrever_sem_groq_key_retorna_erro_amigavel(auth_client):
    # Sem GROQ_API_KEY no ambiente de teste -- deve degradar graciosamente
    # (não estourar 500), avisando para digitar a mensagem.
    audio_fake = (io.BytesIO(b'conteudo-fake-de-audio'), 'gravacao.webm')
    resp = auth_client.post('/contato/transcrever', data={'audio': audio_fake}, content_type='multipart/form-data')
    assert resp.status_code == 503
    data = resp.get_json()
    assert data['ok'] is False
    assert 'digitar' in data['texto'].lower()
