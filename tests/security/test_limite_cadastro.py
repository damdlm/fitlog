"""Limite do cadastro: erros de validação e a simples abertura do formulário
NÃO gastam a cota; só contas realmente criadas contam (5/hora por IP), com um
teto geral de envios (30/hora). A página de limite é amigável."""
import pytest

from extensions import limiter


@pytest.fixture(autouse=True)
def _limiter_limpo(app):
    limiter.reset()
    yield
    limiter.reset()


def _dados(n, senha='Treino#Forte9', **extra):
    d = {'username': f'conta_{n}', 'email': f'conta{n}@exemplo.com', 'password': senha,
         'confirm_password': senha, 'tipo_usuario': 'aluno', 'aceite_termos': 'on',
         'nome_completo': f'Conta {n}'}
    d.update(extra)
    return d


def test_abrir_o_formulario_nao_e_limitado(client):
    for _ in range(25):
        assert client.get('/auth/register').status_code == 200


def test_erros_de_validacao_nao_gastam_a_cota_de_contas(client):
    for i in range(12):
        resp = client.post('/auth/register', data=_dados(i, senha='abc'))
        assert resp.status_code == 302 and '/auth/register' in resp.headers['Location']
        assert client.get('/auth/register').status_code == 200
    # depois de 12 erros (e 12 recargas) o cadastro válido ainda funciona
    resp = client.post('/auth/register', data=_dados(99))
    assert resp.status_code == 302 and '/auth/login' in resp.headers['Location']


def test_so_contas_criadas_consomem_a_cota(client):
    for i in range(5):
        resp = client.post('/auth/register', data=_dados(i))
        assert resp.status_code == 302 and '/auth/login' in resp.headers['Location'], i
    assert client.post('/auth/register', data=_dados(5)).status_code == 429


def test_teto_geral_de_envios_por_hora(client):
    for i in range(30):
        assert client.post('/auth/register', data=_dados(i, senha='abc')).status_code == 302
    assert client.post('/auth/register', data=_dados(31, senha='abc')).status_code == 429


def test_pagina_429_em_portugues_para_navegador(client):
    for i in range(30):
        client.post('/auth/register', data=_dados(i, senha='abc'))
    resp = client.post('/auth/register', data=_dados(31, senha='abc'))
    assert resp.status_code == 429
    html = resp.get_data(as_text=True)
    assert 'Muitas tentativas' in html and 'Too Many Requests' not in html


def test_429_de_api_mantem_a_resposta_padrao(app, client):
    from werkzeug.exceptions import TooManyRequests
    with app.test_request_context('/api/qualquer'):
        resposta = app.handle_user_exception(TooManyRequests())
    assert getattr(resposta, 'code', None) == 429
