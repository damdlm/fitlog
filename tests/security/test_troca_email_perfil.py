"""Troca de e-mail em /auth/profile/update.

O e-mail é o canal de recuperação de senha: quem o controla controla a
conta. Por isso a troca exige a senha atual, valida o formato, zera a
verificação do e-mail e avisa o endereço anterior. Antes desta correção, uma
sessão roubada (ou um XSS) trocava o e-mail sem senha e a conta continuava
"verificada".
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import db, User
from services.email_verificacao_service import EmailVerificacaoService

SENHA = 'SenhaForte123!'
URL = '/auth/profile/update'


def _criar_usuario(username='ana', verificado=True):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno', ativo=True)
    user.set_password(SENHA)
    if verificado:
        user.email_verificado_em = datetime.now(timezone.utc)
    db.session.add(user)
    db.session.commit()
    return user.id


def _logar(client, username='ana'):
    client.post('/auth/login', data={'username': username, 'password': SENHA})


def _form(**extra):
    dados = {'nome_completo': 'Ana Teste', 'email': 'ana@teste.com', 'telefone': '', 'genero': 'F'}
    dados.update(extra)
    return dados


def _flashes(client):
    with client.session_transaction() as sess:
        return [msg for _cat, msg in sess.get('_flashes', [])]


@pytest.fixture
def usuario(app, client):
    app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = True
    with app.app_context():
        uid = _criar_usuario()
    _logar(client)
    return uid


class TestTrocaDeEmailExigeSenha:
    def test_sem_senha_atual_e_recusada(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            resp = client.post(URL, data=_form(email='invasor@evil.com'))
        assert resp.status_code == 302
        assert envio.call_count == 0
        with app.app_context():
            user = db.session.get(User, usuario)
            assert user.email == 'ana@teste.com'
            assert user.email_verificado_em is not None
        assert any('senha atual' in m for m in _flashes(client))

    def test_senha_atual_errada_e_recusada(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            client.post(URL, data=_form(email='invasor@evil.com', senha_atual='errada'))
        assert envio.call_count == 0
        with app.app_context():
            assert db.session.get(User, usuario).email == 'ana@teste.com'

    @pytest.mark.parametrize('invalido', ['sem-arroba', 'a@b', 'a b@c.com', 'x@@c.com'])
    def test_formato_invalido_e_recusado(self, client, app, usuario, invalido):
        with patch('routes.auth_routes.enviar_email', return_value=True):
            client.post(URL, data=_form(email=invalido, senha_atual=SENHA))
        with app.app_context():
            assert db.session.get(User, usuario).email == 'ana@teste.com'

    def test_email_ja_em_uso_so_e_revelado_a_quem_provou_a_senha(self, client, app, usuario):
        with app.app_context():
            _criar_usuario('bia')
        # sem senha: a resposta NÃO pode dizer que o e-mail já existe
        client.post(URL, data=_form(email='bia@teste.com'))
        msgs = _flashes(client)
        assert any('senha atual' in m for m in msgs)
        assert not any('já está em uso' in m for m in msgs)
        # com a senha certa: aí sim informa, e não troca
        client.post(URL, data=_form(email='bia@teste.com', senha_atual=SENHA))
        assert any('já está em uso' in m for m in _flashes(client))
        with app.app_context():
            assert db.session.get(User, usuario).email == 'ana@teste.com'


class TestTrocaValida:
    def test_troca_zera_verificacao_e_envia_os_dois_e_mails(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            resp = client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        assert resp.status_code == 302
        with app.app_context():
            user = db.session.get(User, usuario)
            assert user.email == 'nova@teste.com'
            assert user.email_verificado_em is None
        destinatarios = [c[0][0] for c in envio.call_args_list]
        assert destinatarios == ['ana@teste.com', 'nova@teste.com']
        aviso = envio.call_args_list[0][0][2]
        assert 'n***@teste.com' in aviso and 'nova@teste.com' not in aviso
        assert '/auth/verificar-email/' in envio.call_args_list[1][0][2]

    def test_apos_a_troca_o_usuario_fica_barrado_ate_confirmar(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True):
            client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 302 and '/auth/verificar-email' in resp.headers['Location']

    def test_confirmar_o_novo_email_libera(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        corpo = envio.call_args_list[1][0][2]
        token = corpo.split('/auth/verificar-email/')[1].split()[0]
        client.get(f'/auth/verificar-email/{token}')
        with app.app_context():
            assert db.session.get(User, usuario).email_verificado_em is not None
        assert client.get('/aluno/cadastrar-treinos').status_code == 200

    def test_link_enviado_ao_email_antigo_deixa_de_valer(self, client, app, usuario):
        with app.app_context():
            token_antigo = EmailVerificacaoService.gerar_token(db.session.get(User, usuario))
        with patch('routes.auth_routes.enviar_email', return_value=True):
            client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        client.get(f'/auth/verificar-email/{token_antigo}')
        with app.app_context():
            assert db.session.get(User, usuario).email_verificado_em is None

    def test_falha_no_envio_nao_derruba_e_avisa_o_usuario(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=False):
            resp = client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(User, usuario).email == 'nova@teste.com'
        assert any('não conseguimos enviar' in m for m in _flashes(client))

    def test_falha_no_aviso_ao_email_antigo_nao_impede_a_verificacao(self, client, app, usuario):
        chamadas = []

        def enviar(destinatario, assunto, corpo, *a, **k):
            chamadas.append(destinatario)
            if destinatario == 'ana@teste.com':
                raise RuntimeError('resend fora do ar')
            return True

        with patch('routes.auth_routes.enviar_email', side_effect=enviar):
            client.post(URL, data=_form(email='nova@teste.com', senha_atual=SENHA))
        assert chamadas == ['ana@teste.com', 'nova@teste.com']


class TestSemTrocaNadaMuda:
    def test_atualizar_outros_campos_nao_exige_senha_nem_reverifica(self, client, app, usuario):
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            client.post(URL, data=_form(nome_completo='Ana Silva', telefone='47999990000'))
        assert envio.call_count == 0
        with app.app_context():
            user = db.session.get(User, usuario)
            assert user.nome_completo == 'Ana Silva'
            assert user.email_verificado_em is not None
        assert any('sucesso' in m for m in _flashes(client))