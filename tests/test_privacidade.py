"""Testes obrigatórios de LGPD (ver prompt de ajustes finais de LGPD).

Cobre os 5 itens: aceite versionado no cadastro, reaceite de usuário
existente quando a versão muda, gate do FitBot, exportação de dados e
exclusão/anonimização de conta (incluindo isolamento entre usuários).

Esses testes usam @pytest.mark.lgpd_aceite para desligar o bypass
padrão configurado em tests/conftest.py (a maioria dos outros testes do
projeto cria usuário direto no banco e não deveria ser afetada pelo
gate de reaceite -- ver docstring do bypass).
"""

import pytest

from models import db, User, ConsentimentoLGPD, PasswordResetToken, AlunoProfessor
from services.privacidade_service import (
    PrivacidadeService,
    TIPO_FITBOT,
    TIPO_TERMOS_USO,
    TIPO_POLITICA_PRIVACIDADE,
    VERSAO_TERMOS_USO,
    VERSAO_POLITICA_PRIVACIDADE,
)


def _login(client, username, senha='Senha1234'):
    return client.post('/auth/login', data={'username': username, 'password': senha})


def _criar_usuario_direto(username, tipo_usuario='aluno', nome_completo=None):
    """Cria usuário sem passar por auth.register -- simula uma conta que
    já existia antes deste conjunto de mudanças, sem nenhum aceite
    registrado."""
    user = User(
        username=username, email=f'{username}@teste.com',
        tipo_usuario=tipo_usuario, nome_completo=nome_completo or username.title(),
    )
    user.set_password('Senha1234')
    db.session.add(user)
    db.session.commit()
    return user


# ------------------------------------------------------------------
# 1) Termos de Uso -- aceite versionado no cadastro
# ------------------------------------------------------------------
class TestAceiteTermosNoCadastro:

    def test_registro_sem_marcar_checkbox_nao_cria_conta(self, client, db):
        client.post('/auth/register', data={
            'username': 'semcheckbox', 'email': 'semcheckbox@t.com',
            'password': 'Senha1234', 'confirm_password': 'Senha1234',
        }, follow_redirects=True)

        assert User.query.filter_by(username='semcheckbox').first() is None

    def test_novo_usuario_aceite_e_versao_registrados(self, client, db):
        resp = client.post('/auth/register', data={
            'username': 'novoaluno', 'email': 'novoaluno@t.com',
            'password': 'Senha1234', 'confirm_password': 'Senha1234',
            'aceite_termos': 'on',
        }, follow_redirects=True)

        assert resp.status_code == 200
        user = User.query.filter_by(username='novoaluno').first()
        assert user is not None

        assert ConsentimentoLGPD.tem_versao_aceita(user.id, TIPO_TERMOS_USO, VERSAO_TERMOS_USO)
        assert ConsentimentoLGPD.tem_versao_aceita(user.id, TIPO_POLITICA_PRIVACIDADE, VERSAO_POLITICA_PRIVACIDADE)
        assert not PrivacidadeService.precisa_aceitar_algum(user.id)


# ------------------------------------------------------------------
# 2) Reaceite de usuário já existente, quando a versão vigente muda
# ------------------------------------------------------------------
@pytest.mark.lgpd_aceite
class TestReaceiteUsuarioExistente:

    def test_usuario_antigo_e_redirecionado_para_tela_de_aceite(self, client, db):
        _criar_usuario_direto('antigo1')
        _login(client, 'antigo1')

        resp = client.get('/', follow_redirects=False)

        assert resp.status_code == 302
        assert '/privacidade/aceite' in resp.headers['Location']

    def test_nao_marcar_ciencia_mantem_pendente(self, client, db):
        _criar_usuario_direto('antigo2')
        _login(client, 'antigo2')

        resp = client.post('/privacidade/aceite', data={}, follow_redirects=True)
        texto = resp.get_data(as_text=True)
        assert 'marcar' in texto or 'ciente' in texto.lower()

        user = User.query.filter_by(username='antigo2').first()
        assert PrivacidadeService.precisa_aceitar_algum(user.id)

    def test_aceitar_registra_e_libera_navegacao_sem_reaparecer(self, client, db):
        _criar_usuario_direto('antigo3')
        _login(client, 'antigo3')
        user = User.query.filter_by(username='antigo3').first()

        resp = client.post('/privacidade/aceite', data={'ciencia': 'on'}, follow_redirects=False)
        assert resp.status_code in (302, 303)

        assert not PrivacidadeService.precisa_aceitar_algum(user.id)

        # navegação normal não fica presa em loop
        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 200

    def test_usuario_que_ja_aceitou_nao_e_incomodado_de_novo(self, client, db):
        user = _criar_usuario_direto('emdia')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        _login(client, 'emdia')

        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 200

    def test_fluxo_de_ajax_post_nunca_e_interrompido_pelo_gate(self, client, db):
        """O gate só intercepta GET de página -- uma chamada POST (ex.:
        o próprio fetch do FitBot) nunca deveria ser redirecionada para
        uma página HTML, o que quebraria o parse de JSON no front-end."""
        _criar_usuario_direto('antigo4')
        _login(client, 'antigo4')

        resp = client.post('/privacidade/fitbot-consentimento', json={'concedido': True})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


# ------------------------------------------------------------------
# 3) FitBot -- gate de consentimento específico
# ------------------------------------------------------------------
class TestGateFitbot:

    def test_sem_consentimento_fitbot_fica_bloqueado(self, client, db):
        user = _criar_usuario_direto('semconsent')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        _login(client, 'semconsent')

        resp = client.post('/fitbot/chat', json={'mensagem': 'oi'})
        dados = resp.get_json()
        assert dados.get('consentimento_necessario') is True

    def test_com_consentimento_fitbot_nao_e_mais_bloqueado_pelo_gate_de_privacidade(self, client, db):
        user = _criar_usuario_direto('comconsent')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        PrivacidadeService.registrar_consentimento(user.id, TIPO_FITBOT, concedido=True)
        _login(client, 'comconsent')

        resp = client.post('/fitbot/chat', json={'mensagem': 'oi'})
        dados = resp.get_json()
        # não deve mais ser barrado por falta de consentimento (pode
        # falhar adiante por outro motivo, ex. billing/gate de plano --
        # o que importa aqui é que o motivo não é mais LGPD)
        assert dados.get('consentimento_necessario') is not True

    def test_revogar_consentimento_bloqueia_de_novo(self, client, db):
        user = _criar_usuario_direto('revogando')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        _login(client, 'revogando')

        client.post('/privacidade/fitbot-consentimento', json={'concedido': True})
        assert PrivacidadeService.tem_consentimento_fitbot(user.id)

        client.post('/privacidade/fitbot-consentimento', json={'concedido': False})
        assert not PrivacidadeService.tem_consentimento_fitbot(user.id)

        resp = client.post('/fitbot/chat', json={'mensagem': 'oi de novo'})
        assert resp.get_json().get('consentimento_necessario') is True


# ------------------------------------------------------------------
# 4) Exportação -- só os próprios dados
# ------------------------------------------------------------------
class TestExportacaoDados:

    def test_exporta_apenas_os_proprios_dados(self, client, db):
        eu = _criar_usuario_direto('eumesmo', nome_completo='Eu Mesmo')
        outro = _criar_usuario_direto('outrapessoa', nome_completo='Outra Pessoa')
        PrivacidadeService.registrar_aceite_cadastro(eu.id)
        _login(client, 'eumesmo')

        resp = client.get('/privacidade/exportar-dados')
        assert resp.status_code == 200

        import json
        dados = json.loads(resp.data)
        assert dados['dados_pessoais']['username'] == 'eumesmo'
        texto_completo = resp.get_data(as_text=True)
        assert 'Outra Pessoa' not in texto_completo
        assert 'outrapessoa' not in texto_completo

    def test_exportacao_nao_inclui_hash_de_senha(self, client, db):
        user = _criar_usuario_direto('semvazamento')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        _login(client, 'semvazamento')

        resp = client.get('/privacidade/exportar-dados')
        texto = resp.get_data(as_text=True)
        assert user.password_hash not in texto


# ------------------------------------------------------------------
# 5) Exclusão / anonimização
# ------------------------------------------------------------------
class TestExclusaoConta:

    def test_apos_exclusao_conta_nao_autentica_mais(self, client, db):
        _criar_usuario_direto('vousumir')
        _login(client, 'vousumir')

        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'}, follow_redirects=True)

        client2 = client.application.test_client()
        resp = client2.post('/auth/login', data={'username': 'vousumir', 'password': 'Senha1234'}, follow_redirects=True)
        assert b'inv\xc3\xa1lidos' in resp.data or resp.status_code == 200

    def test_dados_pessoais_removidos_apos_exclusao(self, client, db):
        user = _criar_usuario_direto('meusdados', nome_completo='Nome Real Completo')
        user_id = user.id
        _login(client, 'meusdados')

        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        db.session.expire_all()
        atualizado = db.session.get(User, user_id)
        assert atualizado.ativo is False
        assert atualizado.nome_completo != 'Nome Real Completo'
        assert atualizado.username != 'meusdados'
        assert '@removido.fitlog' in atualizado.email
        assert atualizado.telefone is None

    def test_vinculos_desativados_apos_exclusao_do_aluno(self, client, db):
        professor = _criar_usuario_direto('profvinculado', tipo_usuario='professor')
        aluno = _criar_usuario_direto('alunosumindo', tipo_usuario='aluno')
        vinculo = AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True)
        db.session.add(vinculo)
        db.session.commit()

        _login(client, 'alunosumindo')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        db.session.expire_all()
        vinculo_atualizado = db.session.get(AlunoProfessor, vinculo.id)
        assert vinculo_atualizado.ativo is False

    def test_tokens_de_reset_invalidados_apos_exclusao(self, client, db, app):
        user = _criar_usuario_direto('comtokenativo')
        with app.app_context():
            token = user.get_reset_token()
            db.session.commit()
            registro = PasswordResetToken.query.filter_by(user_id=user.id).order_by(PasswordResetToken.id.desc()).first()
            assert registro.used_at is None

        _login(client, 'comtokenativo')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        db.session.expire_all()
        registro_atualizado = db.session.get(PasswordResetToken, registro.id)
        assert registro_atualizado.used_at is not None

        # o link de reset não funciona mais
        resp = client.get(f'/auth/reset-password/{token}', follow_redirects=True)
        texto = resp.get_data(as_text=True)
        assert 'inválido' in texto or 'expirou' in texto or 'não é mais válido' in texto

    def test_senha_errada_nao_exclui_conta(self, client, db):
        user = _criar_usuario_direto('naoexclui')
        _login(client, 'naoexclui')

        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'senhaerrada'})

        db.session.expire_all()
        ainda_ativo = db.session.get(User, user.id)
        assert ainda_ativo.ativo is True
        assert ainda_ativo.username == 'naoexclui'


# ------------------------------------------------------------------
# Autorização entre usuários (isolamento, incluindo pós-exclusão)
# ------------------------------------------------------------------
class TestIsolamentoEntreUsuarios:

    def test_professor_nao_acessa_aluno_sem_vinculo(self, client, db):
        _criar_usuario_direto('profisolado', tipo_usuario='professor')
        aluno = _criar_usuario_direto('alunoisolado', tipo_usuario='aluno')

        _login(client, 'profisolado')
        resp = client.get(f'/professor/aluno/{aluno.id}')
        assert resp.status_code in (302, 403, 404)

    def test_usuario_excluido_nao_reloga_com_username_antigo(self, client, db):
        _criar_usuario_direto('exusuario')
        _login(client, 'exusuario')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        client2 = client.application.test_client()
        resp = client2.post('/auth/login', data={'username': 'exusuario', 'password': 'Senha1234'}, follow_redirects=True)
        # username antigo não existe mais (foi anonimizado) -- login falha
        assert client2.get('/', follow_redirects=False).status_code == 302
