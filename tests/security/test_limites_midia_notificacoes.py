"""Limites de requisição de mídia e notificações: cada GIF/foto e cada consulta
do sino NÃO podem esgotar a cota geral (300/hora), mas o abuso continua
limitado -- e o limite é ajustável por configuração."""
import pytest

from extensions import limiter
from models import db, User

MIDIA = '/exercicios-media/videos/0001-teste.gif'
FOTO = '/professores-media/professores/1-1.jpg'


@pytest.fixture(autouse=True)
def _limiter_limpo(app):
    limiter.reset()
    yield
    limiter.reset()


def _logar(client, app, nome='sino'):
    with app.app_context():
        u = User(username=nome, email=f'{nome}@teste.com', tipo_usuario='aluno', ativo=True)
        u.set_password('SenhaForte123!')
        db.session.add(u)
        db.session.commit()
    client.post('/auth/login', data={'username': nome, 'password': 'SenhaForte123!'})


def _quantos_429(client, caminho, n):
    return sum(1 for _ in range(n) if client.get(caminho).status_code == 429)


class TestMidia:
    def test_mais_de_300_arquivos_por_hora_nao_dao_429(self, client):
        assert _quantos_429(client, MIDIA, 320) == 0

    def test_fotos_de_professores_tambem(self, client):
        assert _quantos_429(client, FOTO, 320) == 0

    def test_a_cota_geral_de_300_continua_valendo_nas_outras_rotas(self, client):
        # controle: sem este teste, os de cima passariam mesmo se o limiter estivesse desligado
        assert _quantos_429(client, '/privacidade/termos', 320) > 0

    def test_abuso_continua_limitado_e_o_limite_e_ajustavel(self, app, client):
        app.config['LIMITE_MIDIA'] = '5 per hour'
        codigos = [client.get(MIDIA).status_code for _ in range(7)]
        assert codigos.count(429) == 2

    def test_429_de_midia_nao_devolve_a_pagina_html(self, app, client):
        app.config['LIMITE_MIDIA'] = '1 per hour'
        client.get(MIDIA)
        resp = client.get(MIDIA)
        assert resp.status_code == 429
        assert 'Muitas tentativas' not in resp.get_data(as_text=True)

    def test_429_de_pagina_continua_amigavel(self, client):
        for _ in range(300):
            client.get('/privacidade/termos')
        resp = client.get('/privacidade/termos')
        assert resp.status_code == 429 and 'Muitas tentativas' in resp.get_data(as_text=True)


class TestNotificacoes:
    def test_300_consultas_do_sino_por_hora_nao_dao_429(self, app, client):
        _logar(client, app)
        assert _quantos_429(client, '/api/notificacoes', 300) == 0

    def test_abuso_continua_limitado_e_o_limite_e_ajustavel(self, app, client):
        _logar(client, app, 'sino2')
        app.config['LIMITE_NOTIFICACOES'] = '3 per hour'
        codigos = [client.get('/api/notificacoes').status_code for _ in range(5)]
        assert codigos.count(429) == 2

    def test_a_cota_e_por_usuario_nao_compartilhada(self, app, client):
        _logar(client, app, 'um')
        app.config['LIMITE_NOTIFICACOES'] = '2 per hour'
        assert [client.get('/api/notificacoes').status_code for _ in range(3)].count(429) == 1
        client.get('/auth/logout')
        _logar(client, app, 'dois')
        assert client.get('/api/notificacoes').status_code == 200
