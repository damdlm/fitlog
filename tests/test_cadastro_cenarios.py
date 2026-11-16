"""Matriz de cenários do cadastro simplificado, do login e da carência da
confirmação de e-mail (revisão de 16/11/2026).

Complementa tests/test_cadastro_simplificado.py com casos de borda:
contas antigas (usuário fora da regra nova), limites de tamanho que o
SQLite não aplica mas o Postgres sim, professor, admin, carência no limite
e reuso do link de confirmação.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import db, User
from services.email_verificacao_service import CARENCIA_DIAS, EmailVerificacaoService

SENHA = 'cachorro feliz'


def _dados(**extra):
    dados = {'tipo_usuario': 'aluno', 'nome_completo': 'Ana Lima', 'email': 'ana@exemplo.com',
             'password': SENHA, 'aceite_termos': 'on'}
    dados.update(extra)
    return dados


def _cadastrar(client, **extra):
    return client.post('/auth/register', data=_dados(**extra))


def _criar(username, email=None, criado_ha_dias=30, verificado=True, admin=False, tipo='aluno',
           senha=SENHA, ativo=True):
    u = User(username=username, email=email or f'{abs(hash(username))}@exemplo.com', tipo_usuario=tipo,
             is_admin=admin, ativo=ativo, nome_completo='Conta Antiga',
             created_at=datetime.now(timezone.utc) - timedelta(days=criado_ha_dias))
    u.set_password(senha)
    if verificado:
        u.email_verificado_em = datetime.now(timezone.utc)
    db.session.add(u)
    db.session.commit()
    return u.id


def _logar(client, identificador, senha=SENHA):
    return client.post('/auth/login', data={'username': identificador, 'password': senha})


def _uid_logado(client):
    with client.session_transaction() as sess:
        valor = sess.get('_user_id')
    return int(valor.split('.')[0]) if valor else None


@pytest.fixture
def com_verificacao(app):
    app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = True
    yield
    app.config['EMAIL_VERIFICACAO_OBRIGATORIA'] = False


# =============================================================== cadastro

class TestCadastroBordas:
    def test_professor_cria_conta_e_cai_numa_pagina_valida(self, client, app):
        resp = _cadastrar(client, tipo_usuario='professor', nome_completo='Prof Carlos', email='carlos@exemplo.com')
        assert resp.headers['Location'] == '/'
        final = client.get('/', follow_redirects=True)
        assert final.status_code == 200
        with app.app_context():
            u = User.query.filter_by(email='carlos@exemplo.com').first()
            assert u.tipo_usuario == 'professor' and u.username == 'prof.carlos'

    def test_tipo_forjado_e_recusado(self, client, app):
        resp = _cadastrar(client, tipo_usuario='admin')
        assert '/auth/register' in resp.headers['Location']
        with app.app_context():
            assert User.query.filter_by(email='ana@exemplo.com').first() is None

    def test_nome_maior_que_a_coluna_e_recusado_sem_erro_500(self, client, app):
        resp = _cadastrar(client, nome_completo='A' * 201)
        assert resp.status_code == 302 and '/auth/register' in resp.headers['Location']
        with app.app_context():
            assert User.query.filter_by(email='ana@exemplo.com').first() is None

    def test_nome_no_limite_da_coluna_e_aceito(self, client, app):
        resp = _cadastrar(client, nome_completo='Ana ' + 'B' * 196)
        assert resp.headers['Location'] == '/'

    def test_email_maior_que_a_coluna_e_recusado_sem_erro_500(self, client, app):
        email = 'a' * 110 + '@exemplo.com'  # 122 > 120
        resp = _cadastrar(client, email=email)
        assert resp.status_code == 302 and '/auth/register' in resp.headers['Location']

    def test_nome_so_com_simbolos_gera_usuario_pelo_email(self, client, app):
        _cadastrar(client, nome_completo='🏋️💪', email='forte.123@exemplo.com')
        with app.app_context():
            assert User.query.filter_by(email='forte.123@exemplo.com').first().username == 'forte123'

    def test_espacos_no_email_sao_ignorados(self, client, app):
        _cadastrar(client, email='  ana@exemplo.com  ')
        with app.app_context():
            assert User.query.filter_by(email='ana@exemplo.com').first() is not None

    def test_usuario_logado_nao_cria_outra_conta(self, client, app):
        _cadastrar(client)
        assert client.get('/auth/register').status_code == 302
        _cadastrar(client, email='outra@exemplo.com', nome_completo='Outra Pessoa')
        with app.app_context():
            assert User.query.filter_by(email='outra@exemplo.com').first() is None

    def test_sem_aceite_nao_cria_e_preserva_dados(self, client, app):
        dados = _dados()
        dados.pop('aceite_termos')
        client.post('/auth/register', data=dados)
        with app.app_context():
            assert User.query.filter_by(email='ana@exemplo.com').first() is None
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'value="ana@exemplo.com"' in html and 'value="Ana Lima"' in html

    @pytest.mark.parametrize('senha', ['curta', '12345678', 'aaaaaaaa', 'abcabcab', 'qwertyui', 'anaana123'])
    def test_senhas_fracas_recusadas(self, client, app, senha):
        # 'ana@exemplo' e 'anaana123': contêm a parte do e-mail antes do @
        # (só vale a partir de 4 letras, por isso o e-mail anaana@ no 2º).
        email = 'anaana@exemplo.com' if senha == 'anaana123' else 'ana.lima@exemplo.com'
        if senha == 'ana@exemplo':
            email = 'ana@exemplo.com'
        resp = _cadastrar(client, password=senha, email=email)
        assert '/auth/register' in resp.headers['Location'], senha
        with app.app_context():
            assert User.query.filter_by(email=email).first() is None

    @pytest.mark.parametrize('senha', ['cachorro feliz', 'Tr3ino-Forte', 'minhaacademiapreferida', 'um dois três quatro'])
    def test_senhas_boas_aceitas(self, client, app, senha):
        resp = _cadastrar(client, password=senha)
        assert resp.headers['Location'] == '/'


# ================================================================== login

class TestLoginBordas:
    def test_usuario_antigo_com_maiuscula_entra_digitando_minusculo(self, client, app):
        with app.app_context():
            uid = _criar('Joao')
        _logar(client, 'joao')
        assert _uid_logado(client) == uid

    def test_ambiguidade_de_maiusculas_nao_entra_em_conta_errada(self, client, app):
        with app.app_context():
            _criar('Joao', senha='senha do Joao')
            _criar('joao', senha='senha do joao')
        _logar(client, 'JOAO', senha='senha do joao')
        assert _uid_logado(client) is None  # ambíguo: não escolhe por conta própria

    def test_correspondencia_exata_tem_prioridade(self, client, app):
        with app.app_context():
            _criar('Joao', senha='senha do Joao')
            uid = _criar('joao', senha='senha do joao')
        _logar(client, 'joao', senha='senha do joao')
        assert _uid_logado(client) == uid

    def test_email_com_espacos_e_maiusculas(self, client, app):
        with app.app_context():
            uid = _criar('bia', email='bia@exemplo.com')
        _logar(client, '  BIA@Exemplo.com ')
        assert _uid_logado(client) == uid

    def test_conta_inativa_nao_entra_pelo_email(self, client, app):
        with app.app_context():
            _criar('inativo', email='inativo@exemplo.com', ativo=False)
        _logar(client, 'inativo@exemplo.com')
        assert _uid_logado(client) is None

    def test_bloqueio_por_tentativas_vale_tambem_pelo_email(self, client, app):
        with app.app_context():
            uid = _criar('alvo', email='alvo@exemplo.com')
        for _ in range(12):
            _logar(client, 'alvo@exemplo.com', senha='errada!!')
        with app.app_context():
            u = db.session.get(User, uid)
            assert (u.falhas_login or 0) > 0 or u.login_bloqueado_ate is not None
        _logar(client, 'alvo', senha=SENHA)
        # bloqueado (pela conta ou pelo IP): a senha certa não entra agora
        assert _uid_logado(client) is None

    def test_trocar_usuario_e_entrar_com_o_novo(self, client, app):
        with app.app_context():
            uid = _criar('antigo', email='antigo@exemplo.com')
        _logar(client, 'antigo')
        client.post('/auth/profile/update', data={'username': 'NovoNome', 'email': 'antigo@exemplo.com',
                                                  'nome_completo': 'Conta Antiga'})
        client.get('/auth/logout')
        _logar(client, 'novonome')
        assert _uid_logado(client) == uid
        client.get('/auth/logout')
        _logar(client, 'antigo')
        assert _uid_logado(client) is None


# ====================================================== perfil (legado)

class TestPerfilContasAntigas:
    @pytest.mark.parametrize('legado', ['Joao', 'joão-silva', 'Maria Souza'])
    def test_salva_o_perfil_sem_mexer_no_usuario(self, client, app, legado):
        with app.app_context():
            uid = _criar(legado, email='legado@exemplo.com')
        _logar(client, legado)
        html = client.get('/auth/profile').get_data(as_text=True)
        assert 'pattern="[a-z0-9._]' not in html  # não pode travar o formulário no navegador
        client.post('/auth/profile/update', data={'username': legado, 'email': 'legado@exemplo.com',
                                                  'nome_completo': 'Nome Novo'})
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.username == legado and u.nome_completo == 'Nome Novo'

    def test_usuario_em_maiusculas_vira_minusculo(self, client, app):
        with app.app_context():
            uid = _criar('maria.souza', email='m@exemplo.com')
        _logar(client, 'maria.souza')
        client.post('/auth/profile/update', data={'username': 'MariaFit', 'email': 'm@exemplo.com'})
        with app.app_context():
            assert db.session.get(User, uid).username == 'mariafit'


# ============================================ carência da verificação

class TestCarenciaBordas:
    @pytest.mark.parametrize('dias, travado', [(0, False), (CARENCIA_DIAS - 1, False), (CARENCIA_DIAS + 1, True)])
    def test_limites_da_carencia(self, client, app, com_verificacao, dias, travado):
        with app.app_context():
            _criar('c', email='c@exemplo.com', criado_ha_dias=dias, verificado=False)
        _logar(client, 'c')
        resp = client.get('/aluno/cadastrar-treinos')
        assert (resp.status_code == 302 and '/auth/verificar-email' in resp.headers['Location']) is travado

    def test_admin_nunca_e_travado(self, client, app, com_verificacao):
        with app.app_context():
            _criar('chefe', criado_ha_dias=60, verificado=False, admin=True, senha='Admin#2026x')
        _logar(client, 'chefe', senha='Admin#2026x')
        assert client.get('/admin/monitoramento').status_code == 200

    def test_professor_em_carencia_usa_o_painel(self, client, app, com_verificacao):
        with app.app_context():
            _criar('prof', email='prof@exemplo.com', criado_ha_dias=0, verificado=False, tipo='professor')
        _logar(client, 'prof')
        final = client.get('/', follow_redirects=True)
        assert final.status_code == 200
        assert '/auth/verificar-email' not in (final.request.path or '')

    def test_tela_de_pendencia_acessivel_na_carencia(self, client, app, com_verificacao):
        with app.app_context():
            _criar('c2', email='c2@exemplo.com', criado_ha_dias=0, verificado=False)
        _logar(client, 'c2')
        assert client.get('/auth/verificar-email').status_code == 200

    def test_link_confirma_e_a_faixa_some(self, client, app, com_verificacao):
        with app.app_context():
            uid = _criar('c3', email='c3@exemplo.com', criado_ha_dias=0, verificado=False)
            token = EmailVerificacaoService.gerar_token(db.session.get(User, uid))
        _logar(client, 'c3')
        assert 'Reenviar link' in client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        client.get(f'/auth/verificar-email/{token}')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'Reenviar link' not in html
        resp = client.post('/fitbot/chat', json={'mensagem': 'oi'})
        # Pode dar 403 por outro motivo (ex.: plano), mas não pelo e-mail.
        assert 'Confirme seu e-mail' not in ((resp.get_json() or {}).get('resposta') or '')

    def test_link_aberto_em_outro_aparelho_sem_login(self, client, app, com_verificacao):
        with app.app_context():
            uid = _criar('c4', email='c4@exemplo.com', criado_ha_dias=0, verificado=False)
            token = EmailVerificacaoService.gerar_token(db.session.get(User, uid))
        resp = client.get(f'/auth/verificar-email/{token}')
        assert resp.status_code == 302 and '/auth/login' in resp.headers['Location']
        with app.app_context():
            assert db.session.get(User, uid).email_verificado_em is not None

    def test_troca_de_email_na_carencia_continua_na_carencia(self, client, app, com_verificacao):
        with app.app_context():
            _criar('c5', email='c5@exemplo.com', criado_ha_dias=1, verificado=True)
        _logar(client, 'c5')
        with patch('routes.auth_routes.enviar_email', return_value=True):
            client.post('/auth/profile/update', data={'email': 'novo5@exemplo.com', 'nome_completo': 'X',
                                                      'senha_atual': SENHA})
        resp = client.get('/aluno/cadastrar-treinos')
        assert resp.status_code == 200
        assert client.post('/fitbot/chat', json={'mensagem': 'oi'}).status_code in (403, 200, 400, 429)


# =================================================================== senha

class TestSenhaFluxos:
    def test_aluno_troca_senha_para_frase_sem_numero(self, client, app):
        with app.app_context():
            uid = _criar('t', senha='Antiga#2020')
        _logar(client, 't', senha='Antiga#2020')
        client.post('/auth/change-password', data={'current_password': 'Antiga#2020', 'new_password': 'frase bem comprida',
                                                   'confirm_password': 'frase bem comprida'})
        with app.app_context():
            assert db.session.get(User, uid).check_password('frase bem comprida')

    def test_professor_cria_aluno_com_senha_simples(self, client, app):
        with app.app_context():
            _criar('chefe2', admin=True, senha='Admin#2026x')
        _logar(client, 'chefe2', senha='Admin#2026x')
        client.post('/professor/aluno/novo', data={'username': 'aluno.novo', 'email': 'novo@exemplo.com',
                                                   'password': 'cachorrofeliz', 'confirm_password': 'cachorrofeliz',
                                                   'nome_completo': 'Aluno Novo'})
        with app.app_context():
            assert User.query.filter_by(username='aluno.novo').first() is not None


# ============================== maiúsculas em e-mail e usuário (revisão)

class TestMaiusculasEmailEUsuario:
    def test_esqueci_a_senha_com_email_em_outra_capitalizacao(self, client, app):
        with app.app_context():
            _criar('rec', email='rec@exemplo.com')
        with patch('routes.auth_routes.enviar_email', return_value=True) as envio:
            client.post('/auth/reset-password-request', data={'email': 'REC@Exemplo.com'})
        assert envio.called and envio.call_args[0][0] == 'rec@exemplo.com'

    def test_trocar_so_a_capitalizacao_do_proprio_email_nao_e_conflito(self, client, app):
        with app.app_context():
            uid = _criar('cap', email='cap@exemplo.com')
        _logar(client, 'cap')
        with patch('routes.auth_routes.enviar_email', return_value=True):
            client.post('/auth/profile/update', data={'email': 'Cap@exemplo.com', 'nome_completo': 'X',
                                                      'senha_atual': SENHA})
        with app.app_context():
            assert db.session.get(User, uid).email == 'Cap@exemplo.com'

    def test_email_de_outra_conta_em_outra_capitalizacao_e_conflito(self, client, app):
        with app.app_context():
            _criar('dona', email='dona@exemplo.com')
            uid = _criar('outra', email='outra@exemplo.com')
        _logar(client, 'outra')
        client.post('/auth/profile/update', data={'email': 'DONA@exemplo.com', 'nome_completo': 'X',
                                                  'senha_atual': SENHA})
        with app.app_context():
            assert db.session.get(User, uid).email == 'outra@exemplo.com'

    def test_usuario_gerado_nao_colide_com_conta_antiga_em_maiusculas(self, client, app):
        with app.app_context():
            _criar('Ana.Lima')
        _cadastrar(client)
        with app.app_context():
            assert User.query.filter_by(email='ana@exemplo.com').first().username == 'ana.lima2'

    def test_perfil_nao_aceita_usuario_que_so_difere_em_maiusculas(self, client, app):
        with app.app_context():
            _criar('Joao')
            uid = _criar('maria', email='maria@exemplo.com')
        _logar(client, 'maria')
        client.post('/auth/profile/update', data={'username': 'joao', 'email': 'maria@exemplo.com'})
        with app.app_context():
            assert db.session.get(User, uid).username == 'maria'


class TestTamanhosNosOutrosFormularios:
    def test_perfil_com_nome_e_telefone_longos_nao_salva(self, client, app):
        with app.app_context():
            uid = _criar('longo', email='longo@exemplo.com')
        _logar(client, 'longo')
        client.post('/auth/profile/update', data={'email': 'longo@exemplo.com', 'nome_completo': 'N' * 201})
        client.post('/auth/profile/update', data={'email': 'longo@exemplo.com', 'telefone': '9' * 21})
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.nome_completo == 'Conta Antiga' and u.telefone in (None, '')

    def test_professor_editar_aluno_com_email_invalido_nao_salva(self, client, app):
        with app.app_context():
            _criar('chefe3', admin=True, senha='Admin#2026x')
            aluno = _criar('alu', email='alu@exemplo.com')
        _logar(client, 'chefe3', senha='Admin#2026x')
        client.post(f'/professor/aluno/editar/{aluno}', data={'email': 'isso não é e-mail', 'nome_completo': 'X'})
        with app.app_context():
            assert db.session.get(User, aluno).email == 'alu@exemplo.com'

    def test_professor_novo_aluno_com_email_invalido_nao_cria(self, client, app):
        with app.app_context():
            _criar('chefe4', admin=True, senha='Admin#2026x')
        _logar(client, 'chefe4', senha='Admin#2026x')
        client.post('/professor/aluno/novo', data={'username': 'aluno.x', 'email': 'sem-arroba',
                                                   'password': 'cachorrofeliz', 'nome_completo': 'X'})
        with app.app_context():
            assert User.query.filter_by(username='aluno.x').first() is None
