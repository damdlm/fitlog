"""Cota diária / teto mensal na rota /fitbot/chat e a tela Admin > FitBot."""
import pytest

from models import db, User, FitBotMensagem
from services.fitbot_limite_service import FitBotLimiteService
from services.fitbot_service import FitBotService
from tests.integration.test_routes.test_fitbot_routes import _criar_usuario, _login


@pytest.fixture
def ia_ok(monkeypatch):
    chamadas = []

    def fake(**kw):
        chamadas.append(kw)
        return {'ok': True, 'resposta': 'Resposta de teste', 'modo': 'texto'}

    monkeypatch.setattr(FitBotService, 'get_resposta', staticmethod(fake))
    return chamadas


def _perguntar(client, texto='oi'):
    return client.post('/fitbot/chat', json={'mensagem': texto, 'historico': []})


def test_bloqueia_ao_passar_da_cota_sem_chamar_a_ia(client, app, ia_ok):
    with app.app_context():
        _criar_usuario('cota_rota')
        FitBotLimiteService.set_limites('2', '')
    _login(client, 'cota_rota')

    r1, r2, r3 = _perguntar(client), _perguntar(client), _perguntar(client)

    assert r1.status_code == 200 and r1.get_json()['restantes_hoje'] == 1
    assert r2.status_code == 200 and r2.get_json()['restantes_hoje'] == 0
    assert r3.status_code == 429
    assert r3.get_json()['limite_atingido'] == 'diario'
    assert len(ia_ok) == 2  # a 3ª não gerou custo


def test_falha_da_ia_nao_gasta_cota(client, app, monkeypatch):
    monkeypatch.setattr(FitBotService, 'get_resposta',
                        staticmethod(lambda **kw: {'ok': False, 'resposta': 'erro', 'modo': 'texto'}))
    with app.app_context():
        u = _criar_usuario('cota_falha')
        FitBotLimiteService.set_limites('1', '')
        uid = u.id
    _login(client, 'cota_falha')

    assert _perguntar(client).status_code == 503
    assert _perguntar(client).status_code == 503  # continua tentando, sem 429
    with app.app_context():
        assert FitBotMensagem.query.filter_by(user_id=uid).count() == 0


def test_mensagem_invalida_nao_conta(client, app, ia_ok):
    with app.app_context():
        u = _criar_usuario('cota_invalida')
        FitBotLimiteService.set_limites('1', '')
        uid = u.id
    _login(client, 'cota_invalida')

    assert client.post('/fitbot/chat', json={'mensagem': ''}).status_code == 400
    assert _perguntar(client).status_code == 200
    with app.app_context():
        assert FitBotMensagem.query.filter_by(user_id=uid).count() == 1


def test_teto_mensal_bloqueia_na_rota(client, app, ia_ok):
    with app.app_context():
        outro = _criar_usuario('teto_outro')
        _criar_usuario('teto_rota')
        FitBotLimiteService.set_limites('', '1')
        db.session.add(FitBotMensagem(user_id=outro.id))
        db.session.commit()
    _login(client, 'teto_rota')

    r = _perguntar(client)
    assert r.status_code == 429 and r.get_json()['limite_atingido'] == 'mensal'
    assert ia_ok == []


def test_sem_limite_diario_nao_manda_restantes(client, app, ia_ok):
    with app.app_context():
        _criar_usuario('sem_restantes')
        FitBotLimiteService.set_limites('', '')
    _login(client, 'sem_restantes')
    assert 'restantes_hoje' not in _perguntar(client).get_json()


# ------------------------------------------------------------------
# Admin > FitBot
# ------------------------------------------------------------------
def _admin(app, username='admin_fitbot_tela'):
    with app.app_context():
        u = User(username=username, email=f'{username}@teste.com', is_admin=True)
        u.set_password('123456')
        db.session.add(u)
        db.session.commit()


def test_tela_so_para_admin(client, app):
    with app.app_context():
        _criar_usuario('nao_admin_fitbot')
    _login(client, 'nao_admin_fitbot')
    r = client.get('/admin/fitbot')
    assert r.status_code == 302


def test_tela_mostra_numeros_e_salva_limites(client, app, ia_ok):
    with app.app_context():
        _criar_usuario('usa_fitbot')
    _login(client, 'usa_fitbot')
    _perguntar(client)
    client.get('/auth/logout')

    _admin(app)
    _login(client, 'admin_fitbot_tela')
    html = client.get('/admin/fitbot').get_data(as_text=True)
    assert 'Mensagens hoje' in html and 'id="fb-msgs-hoje">1<' in html
    assert 'Usa_Fitbot' in html  # quem mais usa
    assert 'name="limite_diario"' in html and 'value="30"' in html

    r = client.post('/admin/fitbot', data={'limite_diario': '12', 'limite_mensal': '500'}, follow_redirects=True)
    assert 'Limites do FitBot salvos' in r.get_data(as_text=True)
    with app.app_context():
        assert FitBotLimiteService.get_limites() == {'diario': 12, 'mensal': 500}

    r = client.post('/admin/fitbot', data={'limite_diario': 'abc', 'limite_mensal': ''}, follow_redirects=True)
    assert 'número inteiro' in r.get_data(as_text=True)
    with app.app_context():
        assert FitBotLimiteService.get_limites() == {'diario': 12, 'mensal': 500}


def test_link_no_menu_e_no_monitoramento(client, app):
    _admin(app, 'admin_fitbot_menu')
    _login(client, 'admin_fitbot_menu')
    assert 'href="/admin/fitbot"' in client.get('/admin/monitoramento').get_data(as_text=True)
