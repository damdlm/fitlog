"""
Ramos de erro/borda do billing que ficavam sem teste:

  BillingService.situacao_conta         (painel /admin/contas, ~45 linhas de if)
  BillingService.listar_contas          (filtros do painel)
  BillingService.listar_faturas         (tela "Minhas Faturas", chama o Asaas)
  BillingService.expirar_pix_vencidos   (cron: ramos de falha e de corrida)

Nenhum teste sai para a rede: requests.get é substituído por fake.
"""

import itertools
from datetime import datetime, timedelta, timezone

import pytest
import requests

from models import db, User, Plano, Assinatura, AlunoProfessor
from services.billing_service import BillingService
from services.configuracao_service import ConfiguracaoService

_SEQ = itertools.count(1)


def _agora():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _planos():
    fit = Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599)
    pro = Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
                preco_centavos=2990, min_alunos=3, max_alunos=9)
    prem = Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor',
                 preco_centavos=9990, min_alunos=10, max_alunos=None)
    db.session.add_all([fit, pro, prem])
    db.session.commit()
    return fit, pro, prem


def _user(tipo='aluno', prefixo='u'):
    n = next(_SEQ)
    u = User(username=f'{prefixo}{n}', email=f'{prefixo}{n}@teste.com', tipo_usuario=tipo)
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u


def _com_alunos(prof, qtd):
    for _ in range(qtd):
        a = _user('aluno', 'al')
        db.session.add(AlunoProfessor(aluno_id=a.id, professor_id=prof.id, ativo=True))
    db.session.commit()


def _assinar(user, status, plano=None, **campos):
    a = Assinatura(usuario_id=user.id, status=status, plano_id=plano.id if plano else None, **campos)
    db.session.add(a)
    db.session.commit()
    db.session.refresh(user)
    return a


def _situacao(user):
    db.session.refresh(user)
    return BillingService.situacao_conta(user)


# ======================================================================
# situacao_conta -- aluno
# ======================================================================

class TestSituacaoAluno:

    def test_sem_assinatura(self, app):
        s = _situacao(_user())
        assert (s['codigo'], s['rotulo'], s['inadimplente'], s['plano_codigo']) == ('sem_registro', 'Sem registro', False, None)
        assert s['acesso_alunos_bloqueado'] is False

    @pytest.mark.parametrize('status,rotulo,inadimplente,plano', [
        ('trialing', 'Em teste', False, None),
        ('active', 'Ativo', False, 'aluno_fit'),
        ('past_due', 'Pagamento atrasado', True, 'aluno_fit'),
        ('blocked', 'Bloqueado', True, 'aluno_fit'),
        ('canceled', 'Cancelado', False, None),
    ])
    def test_cada_status(self, app, status, rotulo, inadimplente, plano):
        u = _user()
        _assinar(u, status)

        s = _situacao(u)

        assert (s['codigo'], s['rotulo'], s['inadimplente'], s['plano_codigo']) == (status, rotulo, inadimplente, plano)
        assert s['acesso_alunos_bloqueado'] is False

    def test_status_desconhecido_usa_o_proprio_codigo_como_rotulo(self, app):
        u = _user()
        _assinar(u, 'status_novo')
        s = _situacao(u)
        assert (s['codigo'], s['rotulo'], s['inadimplente']) == ('status_novo', 'status_novo', False)


# ======================================================================
# situacao_conta -- professor
# ======================================================================

class TestSituacaoProfessorFaixaGratis:
    """Até 2 alunos: nenhum plano de gestão exigido."""

    def test_sem_assinatura(self, app):
        _planos()
        p = _user('professor')
        _com_alunos(p, 2)

        s = _situacao(p)

        assert (s['codigo'], s['inadimplente'], s['acesso_alunos_bloqueado']) == ('sem_registro', False, False)

    @pytest.mark.parametrize('status,inadimplente', [('trialing', False), ('active', False),
                                                      ('past_due', True), ('blocked', True)])
    def test_status_do_plano_fit_pessoal(self, app, status, inadimplente):
        fit, *_ = _planos()
        p = _user('professor')
        _assinar(p, status, fit)

        s = _situacao(p)

        assert (s['codigo'], s['inadimplente'], s['plano_codigo']) == (status, inadimplente, 'aluno_fit')
        assert s['acesso_alunos_bloqueado'] is False       # blocked de Fit não tranca alunos


class TestSituacaoProfessorComGestao:
    """3+ alunos: exige Pró (3-9) ou Premium (10+)."""

    def _prof(self, qtd=5):
        planos = _planos()
        p = _user('professor')
        _com_alunos(p, qtd)
        return planos, p

    def test_sem_assinatura_fica_pendente(self, app):
        _, p = self._prof()
        s = _situacao(p)
        assert (s['codigo'], s['rotulo'], s['inadimplente'], s['plano_codigo']) == \
            ('pendente', 'Pendente de pagamento', True, 'professor_pro')

    def test_cancelada_tambem_fica_pendente(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'canceled', pro)
        assert _situacao(p)['codigo'] == 'pendente'

    def test_blocked_tranca_o_acesso_aos_alunos(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'blocked', pro)

        s = _situacao(p)

        assert (s['codigo'], s['inadimplente'], s['acesso_alunos_bloqueado']) == ('blocked', True, True)

    def test_past_due_esta_inadimplente_mas_ainda_acessa_alunos(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'past_due', pro)

        s = _situacao(p)

        assert (s['codigo'], s['inadimplente'], s['acesso_alunos_bloqueado']) == ('past_due', True, False)

    def test_active_no_plano_certo(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'active', pro)

        s = _situacao(p)

        assert (s['codigo'], s['inadimplente'], s['plano_codigo']) == ('active', False, 'professor_pro')

    def test_active_em_tier_errado_e_desatualizado(self, app):
        (fit, pro, prem), p = self._prof(12)             # precisa de Premium
        _assinar(p, 'active', pro)

        s = _situacao(p)

        assert (s['codigo'], s['rotulo'], s['inadimplente'], s['plano_codigo']) == \
            ('desatualizado', 'Tier desatualizado', False, 'professor_premium')

    def test_trialing_com_gestao_devolve_status_cru(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'trialing', pro)

        s = _situacao(p)

        assert (s['codigo'], s['rotulo'], s['inadimplente'], s['plano_codigo']) == \
            ('trialing', 'trialing', False, 'professor_pro')

    def test_modo_gratis_nunca_tranca_acesso_mesmo_blocked(self, app):
        (_, pro, _), p = self._prof()
        _assinar(p, 'past_due', pro)
        ConfiguracaoService.set_cobranca_ativa(False)

        # blocked + modo grátis: professor_acesso_alunos_liberado -> True
        a = p.assinatura
        a.status = 'blocked'
        db.session.commit()
        db.session.refresh(p)

        assert BillingService.professor_acesso_alunos_liberado(p) is True


# ======================================================================
# listar_contas
# ======================================================================

class TestListarContas:

    @pytest.fixture
    def contas(self, app):
        fit, pro, _ = _planos()
        self.aluno_ok = _user('aluno', 'ana')
        _assinar(self.aluno_ok, 'active')
        self.aluno_atrasado = _user('aluno', 'bia')
        _assinar(self.aluno_atrasado, 'past_due')
        self.prof = _user('professor', 'pedro')
        _assinar(self.prof, 'trialing', fit)
        adm = User(username='adm_contas', email='adm_contas@teste.com', tipo_usuario='admin', is_admin=True)
        adm.set_password('SenhaForte123!')
        db.session.add(adm)
        db.session.commit()
        # o app já semeia outros usuários (ex.: 'admin'); olhamos só os criados aqui
        self.meus = {self.aluno_ok.username, self.aluno_atrasado.username, self.prof.username}

    def _nomes(self, **f):
        return [c['usuario'].username for c in BillingService.listar_contas(**f)
                if c['usuario'].username in self.meus or c['usuario'].username == 'adm_contas']

    def test_so_alunos_e_professores_admin_fica_de_fora(self, contas):
        nomes = self._nomes()
        assert 'adm_contas' not in nomes
        assert set(nomes) == self.meus

    def test_filtro_por_tipo(self, contas):
        assert self._nomes(tipo_usuario='professor') == [self.prof.username]
        assert set(self._nomes(tipo_usuario='aluno')) == {self.aluno_ok.username, self.aluno_atrasado.username}

    def test_tipo_desconhecido_e_ignorado(self, contas):
        nomes = self._nomes(tipo_usuario='admin')
        assert set(nomes) == self.meus and 'adm_contas' not in nomes

    @pytest.mark.parametrize('campo', ['username', 'email'])
    @pytest.mark.parametrize('caixa', [str.lower, str.upper])
    def test_busca_por_username_ou_email_sem_diferenciar_caixa(self, contas, campo, caixa):
        termo = caixa(getattr(self.aluno_atrasado, campo))
        assert self._nomes(busca=termo) == [self.aluno_atrasado.username]

    def test_busca_por_nome_completo(self, contas):
        self.prof.nome_completo = 'Pedro Treinador'
        db.session.commit()
        assert self._nomes(busca='treinador') == [self.prof.username]

    def test_busca_sem_resultado(self, contas):
        assert self._nomes(busca='zzzz') == []

    def test_busca_com_curinga_sql_e_tratada_como_texto_e_nao_quebra(self, contas):
        assert isinstance(self._nomes(busca="'; DROP TABLE users;--"), list)
        db.session.execute(db.text('select 1 from users limit 1'))        # tabela continua lá

    def test_filtro_inadimplente(self, contas):
        assert self._nomes(situacao_codigo='inadimplente') == [self.aluno_atrasado.username]

    def test_filtro_por_codigo_de_situacao(self, contas):
        assert self._nomes(situacao_codigo='active') == [self.aluno_ok.username]
        assert self._nomes(situacao_codigo='trialing') == [self.prof.username]

    def test_filtro_por_plano(self, contas):
        nomes = set(self._nomes(plano_codigo='aluno_fit'))
        assert nomes == {self.aluno_ok.username, self.aluno_atrasado.username, self.prof.username}

    def test_filtros_se_combinam(self, contas):
        assert self._nomes(tipo_usuario='aluno', situacao_codigo='inadimplente') == [self.aluno_atrasado.username]
        assert self._nomes(tipo_usuario='professor', situacao_codigo='inadimplente') == []

    def test_cada_conta_traz_a_situacao_calculada(self, contas):
        c = BillingService.listar_contas(busca='bia')[0]
        assert c['codigo'] == 'past_due' and c['inadimplente'] is True


# ======================================================================
# listar_faturas
# ======================================================================

class _Resp:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data if json_data is not None else {}
        self.status_code = status_code
        self.text = str(self._json)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}')

    def json(self):
        return self._json


@pytest.fixture
def asaas_get(app, monkeypatch):
    app.config['ASAAS_API_KEY'] = 'chave-de-teste'
    app.config['ASAAS_ENV'] = 'sandbox'
    estado = {'chamadas': [], 'resp': _Resp({'data': []})}

    def _get(url, params=None, headers=None, timeout=None):
        estado['chamadas'].append({'url': url, 'params': params, 'headers': headers, 'timeout': timeout})
        r = estado['resp']
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr('services.billing_service.requests.get', _get)
    return estado


class TestListarFaturas:

    def test_sem_assinatura_nao_chama_o_gateway(self, app, asaas_get):
        assert BillingService.listar_faturas(_user()) == []
        assert asaas_get['chamadas'] == []

    def test_assinatura_sem_customer_id_nao_chama_o_gateway(self, app, asaas_get):
        u = _user()
        _assinar(u, 'trialing')
        assert BillingService.listar_faturas(u) == []
        assert asaas_get['chamadas'] == []

    def test_consulta_so_o_cliente_do_proprio_usuario(self, app, asaas_get):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_DELE')

        BillingService.listar_faturas(u, limite=5)

        c = asaas_get['chamadas'][0]
        assert c['url'].endswith('/payments')
        assert c['params'] == {'customer': 'cus_DELE', 'limit': 5, 'order': 'desc', 'sort': 'dueDate'}
        assert c['timeout']
        assert 'access_token' in c['headers']

    def test_converte_valor_para_centavos_com_arredondamento(self, app, asaas_get):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = _Resp({'data': [
            {'id': 'pay_1', 'value': 5.99, 'status': 'CONFIRMED', 'dueDate': '2026-11-10',
             'paymentDate': '2026-11-09', 'billingType': 'PIX', 'invoiceUrl': 'https://x/1'},
            {'id': 'pay_2', 'value': 29.9, 'status': 'PENDING', 'dueDate': '2026-12-10',
             'billingType': 'CREDIT_CARD'},
            {'id': 'pay_3', 'value': 0.29, 'status': 'PENDING'},
        ]})

        f = BillingService.listar_faturas(u)

        assert [x['valor_centavos'] for x in f] == [599, 2990, 29]       # 5.99*100 = 599.0000000000001
        assert f[0] == {'id': 'pay_1', 'valor_centavos': 599, 'status': 'CONFIRMED', 'vencimento': '2026-11-10',
                        'pago_em': '2026-11-09', 'forma_pagamento': 'PIX', 'link': 'https://x/1'}

    def test_pago_em_cai_para_clientPaymentDate(self, app, asaas_get):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = _Resp({'data': [{'id': 'p', 'value': 1, 'clientPaymentDate': '2026-01-02'}]})

        assert BillingService.listar_faturas(u)[0]['pago_em'] == '2026-01-02'

    def test_campos_ausentes_viram_none_e_valor_zero(self, app, asaas_get):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = _Resp({'data': [{}]})

        f = BillingService.listar_faturas(u)[0]

        assert f['valor_centavos'] == 0 and f['id'] is None and f['pago_em'] is None and f['link'] is None

    @pytest.mark.parametrize('corpo', [{}, {'data': []}])
    def test_sem_dados_devolve_lista_vazia(self, app, asaas_get, corpo):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = _Resp(corpo)
        assert BillingService.listar_faturas(u) == []

    @pytest.mark.parametrize('status', [400, 401, 404, 500, 503])
    def test_erro_http_do_gateway_propaga_para_a_rota_tratar(self, app, asaas_get, status):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = _Resp({'errors': [{'description': 'x'}]}, status_code=status)

        with pytest.raises(requests.HTTPError):
            BillingService.listar_faturas(u)

    @pytest.mark.parametrize('exc', [requests.ConnectionError('off'), requests.Timeout('lento')])
    def test_falha_de_rede_propaga(self, app, asaas_get, exc):
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')
        asaas_get['resp'] = exc

        with pytest.raises(requests.RequestException):
            BillingService.listar_faturas(u)

    def test_sem_api_key_configurada_levanta_runtime_error(self, app, asaas_get):
        app.config['ASAAS_API_KEY'] = ''
        u = _user()
        _assinar(u, 'active', gateway_customer_id='cus_1')

        with pytest.raises(RuntimeError):
            BillingService.listar_faturas(u)


# ======================================================================
# expirar_pix_vencidos -- ramos de falha e corrida
# ======================================================================

def _pix_vencido(**kw):
    u = _user()
    return _assinar(u, 'active', forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(days=1), **kw)


class TestExpirarPixVencidos:

    def test_caminho_feliz_move_para_past_due_com_carencia(self, app):
        a = _pix_vencido()

        assert BillingService.expirar_pix_vencidos() == 1

        db.session.refresh(a)
        assert a.status == 'past_due' and a.vencido_em is not None
        assert _utc(a.carencia_termina_em) > _agora() + timedelta(days=2)

    @pytest.mark.parametrize('campos', [
        dict(forma_pagamento='cartao'),
        dict(cancelado_em=_agora()),                       # cancelamento agendado: sem carência
        dict(periodo_atual_fim=_agora() + timedelta(days=5)),
        dict(periodo_atual_fim=None),
    ])
    def test_nao_toca_em_quem_nao_se_enquadra(self, app, campos):
        base = dict(forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(days=1))
        base.update(campos)
        u = _user()
        a = _assinar(u, 'active', **base)

        assert BillingService.expirar_pix_vencidos() == 0

        db.session.refresh(a)
        assert a.status == 'active' and a.vencido_em is None

    def test_pagamento_no_meio_do_caminho_vence_a_corrida(self, app, monkeypatch):
        """_transicionar devolve False (webhook confirmou o pagamento entre o
        SELECT e o UPDATE) -> não conta e não inicia carência."""
        a = _pix_vencido()
        chamou = []
        monkeypatch.setattr(BillingService, '_iniciar_atraso', staticmethod(lambda *x: chamou.append(1)))
        monkeypatch.setattr(BillingService, '_transicionar', staticmethod(lambda *x: False))

        assert BillingService.expirar_pix_vencidos() == 0

        assert chamou == []
        db.session.refresh(a)
        assert a.status == 'active'

    def test_excecao_em_uma_assinatura_nao_impede_as_demais(self, app, monkeypatch):
        ruim, boa = _pix_vencido(), _pix_vencido()
        original = BillingService._iniciar_atraso

        def _seletivo(assinatura, agora):
            if assinatura.id == ruim.id:
                raise RuntimeError('falha pontual')
            return original(assinatura, agora)

        monkeypatch.setattr(BillingService, '_iniciar_atraso', staticmethod(_seletivo))
        ruim_id, boa_id = ruim.id, boa.id

        assert BillingService.expirar_pix_vencidos() == 1

        db.session.expire_all()
        assert db.session.get(Assinatura, ruim_id).status == 'active'     # rollback desfez a reivindicação
        assert db.session.get(Assinatura, boa_id).status == 'past_due'

    def test_notificacao_que_falha_reverte_e_nao_conta(self, app, monkeypatch):
        """NotificacaoService._criar dá rollback na sessão toda: a assinatura
        volta a 'active' e fica para o próximo run (ramo logger.error)."""
        a = _pix_vencido()
        a_id = a.id

        def _iniciar_que_perde_o_commit(assinatura, agora):
            assinatura.status = 'past_due'
            db.session.rollback()                            # simula o rollback interno da notificação

        monkeypatch.setattr(BillingService, '_iniciar_atraso', staticmethod(_iniciar_que_perde_o_commit))

        assert BillingService.expirar_pix_vencidos() == 0

        db.session.expire_all()
        assert db.session.get(Assinatura, a_id).status == 'active'

    def test_segunda_execucao_nao_reprocessa(self, app):
        _pix_vencido()
        assert BillingService.expirar_pix_vencidos() == 1
        assert BillingService.expirar_pix_vencidos() == 0

    def test_carencia_de_professor_com_gestao_e_maior_que_a_padrao(self, app):
        _, pro, _ = _planos()
        p = _user('professor')
        a = _assinar(p, 'active', pro, forma_pagamento='pix', periodo_atual_fim=_agora() - timedelta(hours=1))
        aluno = _pix_vencido()

        BillingService.expirar_pix_vencidos()

        db.session.refresh(a)
        db.session.refresh(aluno)
        assert (_utc(a.carencia_termina_em) - _utc(aluno.carencia_termina_em)).days >= 10             # 15 dias (gestão) vs 3 (padrão)
