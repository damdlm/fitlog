"""
Testes de integração do painel financeiro do admin (routes/financeiro_routes.py,
montado em /admin/financeiro) e do hook `_financeiro_expira_ao_sair` (app.py).

É a área mais sensível do app (faturamento, saldo na conta Asaas), protegida
por DUAS camadas: @admin_required + reautenticação por usuário E senha que só
vale enquanto o admin continua dentro da área. Aqui garantimos que nenhuma
das duas camadas pode ser contornada -- inclusive chamando a API JSON direto.

O Asaas nunca é chamado de verdade: FinanceiroService.obter_saldo_asaas é
substituído por um stub nos testes que chegam até ele.
"""

from datetime import datetime, timezone

import pytest

from extensions import limiter
from models import db, User, PagamentoRecebido
from services.financeiro_service import FinanceiroService

SESSION_KEY = 'financeiro_desbloqueado'
BASE = '/admin/financeiro'


# ------------------------------------------------------------------
# helpers / fixtures
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limiter_limpo():
    """O login financeiro tem @limiter.limit('10 per minute'); zera o
    contador antes e depois para um teste não afetar o outro."""
    limiter.reset()
    yield
    limiter.reset()


def _criar_usuario(username, is_admin=False, tipo_usuario='aluno', senha='senha-correta-1'):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo_usuario, is_admin=is_admin)
    u.set_password(senha)
    db.session.add(u)
    db.session.commit()
    return u.id


def _login(client, username, senha='senha-correta-1'):
    return client.post('/auth/login', data={'username': username, 'password': senha})


@pytest.fixture
def admin_client(client, app):
    with app.app_context():
        _criar_usuario('fin_admin', is_admin=True)
    _login(client, 'fin_admin')
    return client


@pytest.fixture
def admin_desbloqueado(admin_client):
    with admin_client.session_transaction() as sess:
        sess[SESSION_KEY] = True
    return admin_client


def _desbloqueado(client):
    with client.session_transaction() as sess:
        return sess.get(SESSION_KEY)


def _pagamento(gw_id, centavos, confirmado_em, plano='aluno_fit', forma='pix',
               tipo='aluno', taxa=None, liquido=None):
    p = PagamentoRecebido(
        gateway_payment_id=gw_id, plano_codigo=plano, tipo_usuario=tipo,
        forma_pagamento=forma, valor_bruto_centavos=centavos,
        taxa_asaas_centavos=taxa, valor_liquido_centavos=liquido,
        confirmado_em=confirmado_em,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ------------------------------------------------------------------
# 1ª camada: @admin_required
# ------------------------------------------------------------------

class TestSomenteAdmin:

    @pytest.mark.parametrize('metodo,caminho', [
        ('get', '/login'), ('post', '/login'), ('get', '/'), ('get', '/api/resumo'),
    ])
    def test_anonimo_vai_para_o_login_do_app(self, app, metodo, caminho):
        with app.app_context():     # `g` limpo: ver nota em test_aluno_versao_salvar_finalizar
            resp = getattr(app.test_client(), metodo)(BASE + caminho)
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers['Location']

    @pytest.mark.parametrize('metodo,caminho', [
        ('get', '/login'), ('post', '/login'), ('get', '/'), ('get', '/api/resumo'),
    ])
    def test_usuario_comum_logado_e_barrado(self, client, app, metodo, caminho):
        with app.app_context():
            _criar_usuario('aluno_comum')
        _login(client, 'aluno_comum')

        resp = getattr(client, metodo)(BASE + caminho)

        assert resp.status_code == 302
        assert '/auth/login' not in resp.headers['Location']
        assert BASE not in resp.headers['Location']          # não caiu em nenhuma tela financeira
        assert _desbloqueado(client) is None

    def test_post_de_usuario_comum_com_senha_certa_nao_desbloqueia(self, client, app):
        with app.app_context():
            _criar_usuario('aluno_comum2')
        _login(client, 'aluno_comum2')

        client.post(BASE + '/login', data={'username': 'aluno_comum2', 'password': 'senha-correta-1'})

        assert _desbloqueado(client) is None


# ------------------------------------------------------------------
# 2ª camada: reautenticação (usuário E senha)
# ------------------------------------------------------------------

class TestReautenticacao:

    def test_get_mostra_o_formulario(self, admin_client):
        resp = admin_client.get(BASE + '/login')
        assert resp.status_code == 200
        assert 'password' in resp.get_data(as_text=True)

    def test_senha_errada_retorna_401_e_nao_desbloqueia(self, admin_client):
        resp = admin_client.post(BASE + '/login',
                                 data={'username': 'fin_admin', 'password': 'errada'})

        assert resp.status_code == 401
        assert 'Usuário ou senha incorretos.' in resp.get_data(as_text=True)
        assert _desbloqueado(admin_client) is None

    def test_usuario_errado_com_senha_certa_tambem_e_recusado(self, admin_client):
        """Confere usuário E senha: digitar o nome de OUTRA conta com a
        senha da sessão aberta não pode desbloquear."""
        resp = admin_client.post(BASE + '/login',
                                 data={'username': 'outra_pessoa', 'password': 'senha-correta-1'})

        assert resp.status_code == 401
        assert _desbloqueado(admin_client) is None

    def test_campos_vazios_sao_recusados(self, admin_client):
        resp = admin_client.post(BASE + '/login', data={})
        assert resp.status_code == 401
        assert _desbloqueado(admin_client) is None

    def test_username_com_espacos_nas_pontas_e_aceito(self, admin_client):
        resp = admin_client.post(BASE + '/login',
                                 data={'username': '  fin_admin  ', 'password': 'senha-correta-1'})
        assert resp.status_code == 302
        assert _desbloqueado(admin_client) is True

    def test_credenciais_corretas_desbloqueiam_e_levam_ao_painel(self, admin_client):
        resp = admin_client.post(BASE + '/login',
                                 data={'username': 'fin_admin', 'password': 'senha-correta-1'})

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(BASE + '/')
        assert _desbloqueado(admin_client) is True

    def test_ja_desbloqueado_pula_a_tela_de_login(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/login')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(BASE + '/')

    def test_limite_de_10_tentativas_por_minuto_contra_forca_bruta(self, admin_client):
        codigos = [
            admin_client.post(BASE + '/login',
                              data={'username': 'fin_admin', 'password': f'chute{i}'}).status_code
            for i in range(11)
        ]

        assert codigos[:10] == [401] * 10
        assert codigos[10] == 429
        assert _desbloqueado(admin_client) is None

    def test_apos_estourar_o_limite_ate_a_senha_certa_e_barrada(self, admin_client):
        for i in range(10):
            admin_client.post(BASE + '/login', data={'username': 'fin_admin', 'password': f'x{i}'})

        resp = admin_client.post(BASE + '/login',
                                 data={'username': 'fin_admin', 'password': 'senha-correta-1'})

        assert resp.status_code == 429
        assert _desbloqueado(admin_client) is None


# ------------------------------------------------------------------
# painel (página)
# ------------------------------------------------------------------

class TestPainel:

    def test_sem_desbloqueio_redireciona_para_a_reautenticacao(self, admin_client):
        resp = admin_client.get(BASE + '/')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(BASE + '/login')

    def test_desbloqueado_renderiza_com_periodo_padrao_do_mes_corrente(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/')
        corpo = resp.get_data(as_text=True)

        hoje = datetime.now(timezone.utc)
        assert resp.status_code == 200
        assert hoje.strftime('%Y-%m-01') in corpo       # data_inicio_padrao = dia 1
        assert hoje.strftime('%Y-%m-%d') in corpo       # data_fim_padrao = hoje


# ------------------------------------------------------------------
# API JSON (/api/resumo)
# ------------------------------------------------------------------

class TestApiResumo:

    @pytest.fixture(autouse=True)
    def _sem_asaas(self, monkeypatch):
        monkeypatch.setattr(
            FinanceiroService, 'obter_saldo_asaas',
            staticmethod(lambda: {'saldo_centavos': 98765}),
        )

    def test_sem_desbloqueio_retorna_401_json_mesmo_sendo_admin(self, admin_client):
        """Quem só tem a URL da API em mãos não pode driblar a tela de senha."""
        resp = admin_client.get(BASE + '/api/resumo?data_inicio=2026-01-01&data_fim=2026-12-31')

        assert resp.status_code == 401
        assert resp.get_json() == {'erro': 'reautenticacao_necessaria'}

    def test_sem_desbloqueio_nao_consulta_o_asaas(self, admin_client, monkeypatch):
        chamadas = []
        monkeypatch.setattr(FinanceiroService, 'obter_saldo_asaas',
                            staticmethod(lambda: chamadas.append(1) or {}))
        admin_client.get(BASE + '/api/resumo?data_inicio=2026-01-01&data_fim=2026-12-31')
        assert chamadas == []

    @pytest.mark.parametrize('query', [
        '',                                                    # sem parâmetros
        '?data_inicio=2026-01-01',                             # falta data_fim
        '?data_fim=2026-01-01',                                # falta data_inicio
        '?data_inicio=01/01/2026&data_fim=31/01/2026',         # formato errado
        '?data_inicio=2026-13-40&data_fim=2026-01-01',         # data impossível
        '?data_inicio=abc&data_fim=def',
    ])
    def test_datas_invalidas_retornam_400(self, admin_desbloqueado, query):
        resp = admin_desbloqueado.get(BASE + '/api/resumo' + query)

        assert resp.status_code == 400
        assert resp.get_json() == {'erro': 'Datas inválidas.'}

    def test_data_inicial_depois_da_final_retorna_400(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2026-02-10&data_fim=2026-02-01')

        assert resp.status_code == 400
        assert 'não pode ser depois' in resp.get_json()['erro']

    def test_mesmo_dia_como_inicio_e_fim_e_valido(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2026-02-01&data_fim=2026-02-01')
        assert resp.status_code == 200

    def test_sucesso_retorna_resumo_e_saldo(self, admin_desbloqueado, app):
        with app.app_context():
            _pagamento('pay_1', 2990, datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                       taxa=199, liquido=2791)

        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2026-03-01&data_fim=2026-03-31')

        assert resp.status_code == 200
        dados = resp.get_json()
        assert dados['saldo'] == {'saldo_centavos': 98765}
        assert dados['resumo']['qtd_pagamentos'] == 1
        assert dados['resumo']['total_bruto_centavos'] == 2990
        assert dados['resumo']['total_taxa_centavos'] == 199
        assert dados['resumo']['total_liquido_centavos'] == 2791

    def test_data_fim_e_inclusiva_ate_23h59m59s(self, admin_desbloqueado, app):
        with app.app_context():
            _pagamento('pay_ultimo_seg', 1000, datetime(2026, 3, 31, 23, 59, 58, tzinfo=timezone.utc))
            _pagamento('pay_dia_seguinte', 5000, datetime(2026, 4, 1, 0, 0, 1, tzinfo=timezone.utc))

        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2026-03-01&data_fim=2026-03-31')

        resumo = resp.get_json()['resumo']
        assert resumo['qtd_pagamentos'] == 1
        assert resumo['total_bruto_centavos'] == 1000

    def test_periodo_sem_pagamentos_retorna_zeros(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2020-01-01&data_fim=2020-01-31')

        resumo = resp.get_json()['resumo']
        assert resp.status_code == 200
        assert resumo['qtd_pagamentos'] == 0
        assert resumo['total_bruto_centavos'] == 0
        assert resumo['por_forma_pagamento'] == []

    def test_falha_no_asaas_nao_derruba_os_dados_locais(self, admin_desbloqueado, app, monkeypatch):
        monkeypatch.setattr(
            FinanceiroService, 'obter_saldo_asaas',
            staticmethod(lambda: {'erro': 'Não foi possível consultar o saldo no Asaas agora.'}),
        )
        with app.app_context():
            _pagamento('pay_ok', 1500, datetime(2026, 3, 5, tzinfo=timezone.utc))

        resp = admin_desbloqueado.get(BASE + '/api/resumo?data_inicio=2026-03-01&data_fim=2026-03-31')

        dados = resp.get_json()
        assert resp.status_code == 200
        assert 'erro' in dados['saldo']
        assert dados['resumo']['total_bruto_centavos'] == 1500


# ------------------------------------------------------------------
# hook app.py:_financeiro_expira_ao_sair
# ------------------------------------------------------------------

class TestExpiraAoSair:
    """Sair da área financeira (navegação de página) derruba o desbloqueio;
    chamadas em segundo plano (fetch/XHR) NÃO podem derrubar."""

    NAVEGACAO = {'Sec-Fetch-Mode': 'navigate'}

    def test_navegar_para_pagina_fora_da_area_derruba_o_desbloqueio(self, admin_desbloqueado):
        admin_desbloqueado.get('/', headers=self.NAVEGACAO)
        assert _desbloqueado(admin_desbloqueado) is None

    def test_apos_sair_e_voltar_pede_usuario_e_senha_de_novo(self, admin_desbloqueado):
        admin_desbloqueado.get('/', headers=self.NAVEGACAO)

        resp = admin_desbloqueado.get(BASE + '/')

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(BASE + '/login')

    def test_navegar_dentro_da_propria_area_mantem_o_desbloqueio(self, admin_desbloqueado):
        resp = admin_desbloqueado.get(BASE + '/', headers=self.NAVEGACAO)
        assert resp.status_code == 200
        assert _desbloqueado(admin_desbloqueado) is True

    @pytest.mark.parametrize('modo', ['cors', 'same-origin', 'no-cors'])
    def test_fetch_em_segundo_plano_nao_derruba(self, admin_desbloqueado, modo):
        """Ex.: o sino de notificações faz fetch em toda tela."""
        admin_desbloqueado.get('/', headers={'Sec-Fetch-Mode': modo})
        assert _desbloqueado(admin_desbloqueado) is True

    def test_sem_sec_fetch_com_accept_html_conta_como_navegacao(self, admin_desbloqueado):
        admin_desbloqueado.get('/', headers={'Accept': 'text/html,application/xhtml+xml'})
        assert _desbloqueado(admin_desbloqueado) is None

    def test_sem_sec_fetch_com_accept_json_nao_derruba(self, admin_desbloqueado):
        admin_desbloqueado.get('/', headers={'Accept': 'application/json'})
        assert _desbloqueado(admin_desbloqueado) is True

    def test_sem_sec_fetch_e_sem_accept_nao_derruba(self, admin_desbloqueado):
        admin_desbloqueado.get('/')
        assert _desbloqueado(admin_desbloqueado) is True

    def test_sem_sec_fetch_caminho_api_nao_derruba_mesmo_aceitando_html(self, admin_desbloqueado):
        admin_desbloqueado.get('/api/notificacoes', headers={'Accept': 'text/html'})
        assert _desbloqueado(admin_desbloqueado) is True

    def test_arquivos_estaticos_nao_derrubam(self, admin_desbloqueado):
        admin_desbloqueado.get('/static/inexistente.css', headers=self.NAVEGACAO)
        assert _desbloqueado(admin_desbloqueado) is True

    def test_post_fora_da_area_nao_derruba(self, admin_desbloqueado):
        """O hook só intercepta GET (não quebrar POSTs/fetch existentes)."""
        admin_desbloqueado.post('/auth/logout-inexistente', headers=self.NAVEGACAO)
        assert _desbloqueado(admin_desbloqueado) is True

    def test_navegacao_anonima_nao_quebra(self, app):
        with app.app_context():
            resp = app.test_client().get('/', headers=self.NAVEGACAO)
        assert resp.status_code in (200, 302)
