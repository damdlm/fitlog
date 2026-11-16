"""Cadastro simplificado (nov/2026).

- Formulário: tipo de conta, nome, e-mail, senha e aceite. Nome de usuário
  é gerado a partir do nome; sem "confirmar senha", gênero e telefone.
- Já entra na conta logo após o cadastro.
- Login aceita e-mail ou nome de usuário.
- Confirmação de e-mail com carência de 7 dias: usa o app na hora; só
  FitBot e assinatura ficam travados até confirmar.
- Nome de usuário editável no perfil.
- Senha: sem "letra e número" para contas comuns; admin mantém a regra rígida.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import db, User
from services.email_verificacao_service import CARENCIA_DIAS, EmailVerificacaoService
from utils.validators import gerar_username, validar_username

SENHA = 'cachorro feliz'


def _cadastrar(client, **extra):
    dados = {'tipo_usuario': 'aluno', 'nome_completo': 'Maria José Souza',
             'email': 'maria@exemplo.com', 'password': SENHA, 'aceite_termos': 'on'}
    dados.update(extra)
    return client.post('/auth/register', data=dados)


def _logado(client):
    with client.session_transaction() as sess:
        return sess.get('_user_id')


def _criar(username, email, criado_ha_dias=0, verificado=False, admin=False, senha=SENHA):
    u = User(username=username, email=email, tipo_usuario='aluno', ativo=True, is_admin=admin,
             created_at=datetime.now(timezone.utc) - timedelta(days=criado_ha_dias))
    u.set_password(senha)
    if verificado:
        u.email_verificado_em = datetime.now(timezone.utc)
    db.session.add(u)
    db.session.commit()
    return u.id


@pytest.fixture
def com_verificacao(app):
    app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = True
    yield
    app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = False


# ----------------------------------------------------------------- cadastro

class TestCadastro:
    def test_so_nome_email_senha_e_aceite_cria_a_conta_e_ja_entra(self, client, app):
        resp = _cadastrar(client)
        assert resp.status_code == 302
        assert resp.headers['Location'] == '/'
        with app.app_context():
            user = User.query.filter_by(email='maria@exemplo.com').first()
            assert user is not None
            assert user.username == 'maria.souza'
            assert user.nome_completo == 'Maria José Souza'
            assert user.genero is None and user.telefone is None
            assert (_logado(client) or '').split('.')[0] == str(user.id)

    def test_usuario_gerado_nao_repete(self, client, app):
        with app.app_context():
            _criar('maria.souza', 'outra@exemplo.com')
        _cadastrar(client)
        with app.app_context():
            assert User.query.filter_by(email='maria@exemplo.com').first().username == 'maria.souza2'

    def test_nome_e_obrigatorio(self, client, app):
        resp = _cadastrar(client, nome_completo='  ')
        assert '/auth/register' in resp.headers['Location']
        with app.app_context():
            assert User.query.filter_by(email='maria@exemplo.com').first() is None

    def test_email_repetido_sem_diferenciar_maiusculas(self, client, app):
        with app.app_context():
            _criar('existente', 'maria@exemplo.com')
        resp = _cadastrar(client, email='Maria@Exemplo.com')
        assert '/auth/register' in resp.headers['Location']
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'já tem conta' in html

    def test_formulario_nao_tem_mais_os_campos_removidos(self, client):
        html = client.get('/auth/register').get_data(as_text=True)
        for campo in ('name="username"', 'name="confirm_password"', 'name="genero"', 'name="telefone"'):
            assert campo not in html, campo
        for campo in ('name="nome_completo"', 'name="email"', 'name="password"', 'name="aceite_termos"'):
            assert campo in html, campo
        assert 'id="regSenhaOlho"' in html  # mostrar/esconder senha

    def test_campos_antigos_ainda_sao_aceitos(self, client, app):
        """Cliente desatualizado (formulário antigo em cache) continua funcionando."""
        resp = _cadastrar(client, username='escolhido', confirm_password=SENHA, genero='F',
                          telefone='(47) 99999-0000')
        assert resp.headers['Location'] == '/'
        with app.app_context():
            u = User.query.filter_by(email='maria@exemplo.com').first()
            assert u.username == 'escolhido' and u.genero == 'F'

    def test_confirmacao_diferente_ainda_e_recusada_se_enviada(self, client, app):
        resp = _cadastrar(client, confirm_password='outra coisa')
        assert '/auth/register' in resp.headers['Location']


# -------------------------------------------------------------------- login

class TestLoginPorEmailOuUsuario:
    @pytest.mark.parametrize('identificador', ['ana.lima', 'ana@exemplo.com', 'ANA@Exemplo.COM'])
    def test_entra_com_usuario_ou_email(self, client, app, identificador):
        with app.app_context():
            _criar('ana.lima', 'ana@exemplo.com', verificado=True)
        resp = client.post('/auth/login', data={'username': identificador, 'password': SENHA})
        assert resp.status_code == 302 and '/auth/login' not in resp.headers['Location']
        assert _logado(client)

    def test_senha_errada_continua_recusada(self, client, app):
        with app.app_context():
            _criar('ana.lima', 'ana@exemplo.com', verificado=True)
        resp = client.post('/auth/login', data={'username': 'ana@exemplo.com', 'password': 'errada123'})
        assert '/auth/login' in resp.headers['Location']
        assert not _logado(client)

    def test_tela_de_login_pede_email_ou_usuario(self, client):
        assert 'E-mail ou usuário' in client.get('/auth/login').get_data(as_text=True)


# ------------------------------------------------- carência da verificação

class TestCarenciaVerificacaoEmail:
    def test_conta_nova_usa_o_app_e_ve_o_aviso(self, client, app, com_verificacao):
        with app.app_context():
            _criar('nova', 'nova@exemplo.com', criado_ha_dias=0)
        client.post('/auth/login', data={'username': 'nova', 'password': SENHA})
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Reenviar link' in html
        assert f'em até {CARENCIA_DIAS} dias' in html and 'Reenviar link' in html

    def test_fitbot_e_assinatura_ficam_travados_na_carencia(self, client, app, com_verificacao):
        with app.app_context():
            _criar('nova2', 'nova2@exemplo.com', criado_ha_dias=1)
        client.post('/auth/login', data={'username': 'nova2', 'password': SENHA})
        resp = client.post('/fitbot/chat', json={'mensagem': 'oi'})
        assert resp.status_code == 403
        dados = resp.get_json()
        assert dados['ok'] is False and 'Confirme seu e-mail' in dados['resposta']
        resp = client.get('/billing/minha-assinatura')
        assert resp.status_code == 302 and '/auth/verificar-email' in resp.headers['Location']

    def test_depois_da_carencia_trava_tudo(self, client, app, com_verificacao):
        with app.app_context():
            _criar('velha', 'velha@exemplo.com', criado_ha_dias=CARENCIA_DIAS + 1)
        client.post('/auth/login', data={'username': 'velha', 'password': SENHA})
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 302 and '/auth/verificar-email' in resp.headers['Location']

    def test_verificado_nao_ve_aviso_nem_trava(self, client, app, com_verificacao):
        with app.app_context():
            _criar('ok', 'ok@exemplo.com', criado_ha_dias=0, verificado=True)
        client.post('/auth/login', data={'username': 'ok', 'password': SENHA})
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 200
        assert 'Reenviar link' not in resp.get_data(as_text=True)

    def test_reenviar_pela_faixa_volta_para_a_mesma_pagina(self, client, app, com_verificacao):
        with app.app_context():
            _criar('nova3', 'nova3@exemplo.com', criado_ha_dias=0)
        client.post('/auth/login', data={'username': 'nova3', 'password': SENHA})
        with patch('routes.auth_routes.enviar_email', return_value=True):
            resp = client.post('/auth/reenviar-verificacao', data={'next': '/aluno/cadastrar-treinos'})
        assert resp.headers['Location'].endswith('/aluno/cadastrar-treinos')

    def test_cadastro_com_verificacao_ja_entra_e_avisa(self, client, app, com_verificacao):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            resp = _cadastrar(client)
        assert resp.headers['Location'] == '/'
        assert envio.called
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'Reenviar link' in html

    def test_dias_restantes(self, app):
        with app.app_context():
            u = User(username='x', email='x@x.com', created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=1))
            assert EmailVerificacaoService.dias_restantes_carencia(u) == CARENCIA_DIAS - 2
            u.created_at = datetime.now(timezone.utc) - timedelta(days=CARENCIA_DIAS, seconds=1)
            assert EmailVerificacaoService.dias_restantes_carencia(u) == 0


# ------------------------------------------------ nome de usuário no perfil

class TestUsernameNoPerfil:
    def _logar(self, client, app):
        with app.app_context():
            _criar('maria.souza', 'maria@exemplo.com', verificado=True)
            _criar('ocupado', 'ocupado@exemplo.com', verificado=True)
        client.post('/auth/login', data={'username': 'maria.souza', 'password': SENHA})

    def _salvar(self, client, username):
        return client.post('/auth/profile/update', data={
            'username': username, 'email': 'maria@exemplo.com', 'nome_completo': 'Maria'})

    def test_troca_valida(self, client, app):
        self._logar(client, app)
        self._salvar(client, 'mariafit')
        with app.app_context():
            assert User.query.filter_by(email='maria@exemplo.com').first().username == 'mariafit'

    @pytest.mark.parametrize('invalido', ['ma', 'maria@x', 'Maria Souza', 'ocupado'])
    def test_troca_invalida_nao_salva(self, client, app, invalido):
        self._logar(client, app)
        self._salvar(client, invalido)
        with app.app_context():
            assert User.query.filter_by(email='maria@exemplo.com').first().username == 'maria.souza'


# ------------------------------------------------------------------ senha

class TestSenhaDoAdmin:
    def test_admin_trocando_senha_precisa_de_letra_e_numero(self, client, app):
        with app.app_context():
            _criar('chefe', 'chefe@exemplo.com', verificado=True, admin=True, senha='Admin#Forte2026')
        client.post('/auth/login', data={'username': 'chefe', 'password': 'Admin#Forte2026'})
        rota = None
        for regra in app.url_map.iter_rules():
            if regra.endpoint == 'auth.change_password':
                rota = regra.rule
        assert rota, 'rota de troca de senha não encontrada'
        client.post(rota, data={'current_password': 'Admin#Forte2026', 'new_password': 'cachorrofeliz',
                                'confirm_password': 'cachorrofeliz'})
        with app.app_context():
            assert User.query.filter_by(username='chefe').first().check_password('Admin#Forte2026')


# ------------------------------------------------------------- utilitários

class TestGerarUsername:
    @pytest.mark.parametrize('nome, email, esperado', [
        ('Maria José Souza', 'm@x.com', 'maria.souza'),
        ('João', 'j@x.com', 'joao'),
        ('Lu', 'l@x.com', 'lufit'),
        ('', 'fulano.123@x.com', 'fulano123'),
        ('李', 'zz@x.com', 'zzfit'),
    ])
    def test_gera_a_partir_do_nome(self, nome, email, esperado):
        assert gerar_username(nome, email, lambda c: False) == esperado

    def test_resultado_e_sempre_um_username_valido(self):
        for nome in ('Ana', 'José da Silva Xavier', 'Ñandú Ç', 'x' * 80, '!!!'):
            assert validar_username(gerar_username(nome, 'a@b.com', lambda c: False))[0], nome
