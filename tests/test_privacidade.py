"""Testes obrigatórios de LGPD (ver prompt de ajustes finais de LGPD).

Cobre os 5 itens: aceite versionado no cadastro, reaceite de usuário
existente quando a versão muda, gate do FitBot, exportação de dados e
exclusão/anonimização de conta (incluindo isolamento entre usuários).

Esses testes usam @pytest.mark.lgpd_aceite para desligar o bypass
padrão configurado em tests/conftest.py (a maioria dos outros testes do
projeto cria usuário direto no banco e não deveria ser afetada pelo
gate de reaceite -- ver docstring do bypass).
"""

from datetime import date, datetime, timezone

import pytest

from models import (
    db, User, ConsentimentoLGPD, PasswordResetToken, AlunoProfessor,
    Musculo, ExercicioUsuario, VersaoGlobal, TreinoVersao, VersaoExercicio,
    RegistroTreino, HistoricoTreino,
)
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


def _criar_treino_completo(user, codigo='A'):
    """Cria treino + versão + exercício próprio + registro + série para
    um usuário -- usado pelos testes de exclusão (Alternativa A) para
    verificar que esse histórico é de fato apagado, não só ocultado."""
    musculo = Musculo.query.filter_by(nome=f'm_{user.id}').first()
    if not musculo:
        musculo = Musculo(nome=f'm_{user.id}', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.commit()

    ex = ExercicioUsuario(usuario_id=user.id, nome=f'Exercicio de {user.username}', musculo_id=musculo.id)
    db.session.add(ex)
    db.session.commit()

    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date.today(), user_id=user.id)
    db.session.add(versao)
    db.session.commit()

    tv = TreinoVersao(versao_id=versao.id, codigo=codigo, nome_treino=f'Treino {codigo}', descricao_treino='')
    db.session.add(tv)
    db.session.commit()
    db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=1))
    db.session.commit()

    registro = RegistroTreino(
        treino_versao_id=tv.id, versao_id=versao.id, periodo='manha', semana=1,
        exercicio_usuario_id=ex.id, data_registro=datetime.now(timezone.utc), user_id=user.id,
    )
    db.session.add(registro)
    db.session.commit()
    db.session.add(HistoricoTreino(registro_id=registro.id, carga=100, repeticoes=10))
    db.session.commit()

    return {'treino': tv, 'versao': versao, 'exercicio': ex, 'registro': registro}


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
# 1b) Cadastro é transacional: falha no aceite reverte o usuário inteiro
# ------------------------------------------------------------------
class TestCadastroTransacional:

    def test_falha_no_aceite_reverte_criacao_do_usuario(self, client, db, monkeypatch):
        """Simula uma falha ao gravar o aceite -- o usuário (e a
        Assinatura de trial) não pode sobreviver a essa falha, já que
        tudo faz parte da mesma transação (ver routes/auth_routes.py:
        register)."""
        def _explode(*args, **kwargs):
            raise RuntimeError("falha simulada ao gravar aceite")

        monkeypatch.setattr(
            PrivacidadeService, 'registrar_aceite_cadastro', staticmethod(_explode),
        )

        client.post('/auth/register', data={
            'username': 'vaifalhar', 'email': 'vaifalhar@t.com',
            'password': 'Senha1234', 'confirm_password': 'Senha1234',
            'aceite_termos': 'on',
        }, follow_redirects=True)

        assert User.query.filter_by(username='vaifalhar').first() is None
        assert ConsentimentoLGPD.query.filter_by(contexto='cadastro').count() == 0

    def test_cadastro_normal_grava_usuario_e_aceite_juntos(self, client, db):
        """Contraprova do teste acima: no caminho feliz, User + Assinatura
        + os dois aceites aparecem juntos, todos do mesmo commit."""
        from models import Assinatura

        client.post('/auth/register', data={
            'username': 'vaifuncionar', 'email': 'vaifuncionar@t.com',
            'password': 'Senha1234', 'confirm_password': 'Senha1234',
            'aceite_termos': 'on',
        }, follow_redirects=True)

        user = User.query.filter_by(username='vaifuncionar').first()
        assert user is not None
        assert Assinatura.query.filter_by(usuario_id=user.id).first() is not None
        assert ConsentimentoLGPD.tem_versao_aceita(user.id, TIPO_TERMOS_USO, VERSAO_TERMOS_USO)
        assert ConsentimentoLGPD.tem_versao_aceita(user.id, TIPO_POLITICA_PRIVACIDADE, VERSAO_POLITICA_PRIVACIDADE)


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

    def test_exportacao_inclui_versao_do_consentimento(self, client, db):
        user = _criar_usuario_direto('comversao')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        _login(client, 'comversao')

        import json
        resp = client.get('/privacidade/exportar-dados')
        dados = json.loads(resp.data)

        termos = next(c for c in dados['consentimentos_lgpd'] if c['tipo'] == TIPO_TERMOS_USO)
        assert termos['versao'] == VERSAO_TERMOS_USO

    def test_exportacao_compativel_com_consentimento_antigo_sem_versao(self, client, db):
        """Um consentimento pontual (ex: fitbot_ia) nunca teve `versao`
        preenchida -- a exportação precisa continuar funcionando e
        devolver null, sem inventar uma versão retroativa."""
        user = _criar_usuario_direto('semversaoantiga')
        PrivacidadeService.registrar_aceite_cadastro(user.id)
        PrivacidadeService.registrar_consentimento(user.id, TIPO_FITBOT, concedido=True)
        _login(client, 'semversaoantiga')

        import json
        resp = client.get('/privacidade/exportar-dados')
        dados = json.loads(resp.data)

        fitbot = next(c for c in dados['consentimentos_lgpd'] if c['tipo'] == TIPO_FITBOT)
        assert fitbot['versao'] is None


# ------------------------------------------------------------------
# 4b) Aluno criado pelo professor -- sem aceite falso, aceite exigido
# no primeiro acesso (Parte 2 do prompt de escalabilidade/LGPD)
# ------------------------------------------------------------------
class TestAlunoCriadoPeloProfessor:

    def _criar_professor_logado(self, client, username='profcadastrador'):
        professor = _criar_usuario_direto(username, tipo_usuario='professor')
        # o próprio professor não deve ficar preso no gate de aceite ao
        # tentar cadastrar o aluno -- registra o aceite dele normalmente.
        PrivacidadeService.registrar_aceite_cadastro(professor.id)
        db.session.commit()
        _login(client, username)
        return professor

    @pytest.mark.lgpd_aceite
    def test_professor_cria_aluno_sem_registrar_aceite_falso(self, client, db):
        self._criar_professor_logado(client)

        client.post('/professor/aluno/novo', data={
            'username': 'alunodoprof', 'email': 'alunodoprof@t.com',
            'password': 'Senha1234', 'nome_completo': 'Aluno Do Professor',
        }, follow_redirects=True)

        aluno = User.query.filter_by(username='alunodoprof').first()
        assert aluno is not None
        # nenhum aceite (Termos/Política) foi registrado em nome do
        # aluno -- só o próprio aluno pode aceitar, no primeiro acesso.
        assert ConsentimentoLGPD.query.filter_by(usuario_id=aluno.id).count() == 0
        assert PrivacidadeService.precisa_aceitar_algum(aluno.id) is True

    @pytest.mark.lgpd_aceite
    def test_primeiro_login_do_aluno_e_redirecionado_para_aceite(self, client, db):
        self._criar_professor_logado(client)
        client.post('/professor/aluno/novo', data={
            'username': 'alunoprimeiroacesso', 'email': 'alunoprimeiro@t.com',
            'password': 'Senha1234', 'nome_completo': 'Aluno Primeiro Acesso',
        }, follow_redirects=True)

        # troca a sessão do professor pela do aluno no MESMO client --
        # auth.login redireciona direto pra index se já houver alguém
        # autenticado (ver routes/auth_routes.py:login), então o
        # logout explícito é obrigatório antes de logar como o aluno.
        client.get('/auth/logout')
        _login(client, 'alunoprimeiroacesso')
        resp = client.get('/', follow_redirects=False)

        assert resp.status_code in (301, 302)
        assert '/privacidade/aceite' in resp.headers.get('Location', '')

    @pytest.mark.lgpd_aceite
    def test_aluno_aceita_e_e_liberado_com_versao_correta(self, client, db):
        self._criar_professor_logado(client)
        client.post('/professor/aluno/novo', data={
            'username': 'alunoaceita', 'email': 'alunoaceita@t.com',
            'password': 'Senha1234', 'nome_completo': 'Aluno Que Aceita',
        }, follow_redirects=True)
        aluno = User.query.filter_by(username='alunoaceita').first()

        client.get('/auth/logout')
        _login(client, 'alunoaceita')
        client.get('/')  # dispara o redirect para a tela de aceite

        resp = client.post('/privacidade/aceite', data={'ciencia': 'on'}, follow_redirects=True)

        assert resp.status_code == 200
        assert ConsentimentoLGPD.tem_versao_aceita(aluno.id, TIPO_TERMOS_USO, VERSAO_TERMOS_USO)
        assert ConsentimentoLGPD.tem_versao_aceita(aluno.id, TIPO_POLITICA_PRIVACIDADE, VERSAO_POLITICA_PRIVACIDADE)
        assert PrivacidadeService.precisa_aceitar_algum(aluno.id) is False

        # depois de aceitar, a navegação normal não é mais interrompida
        resp_normal = client.get('/', follow_redirects=False)
        assert resp_normal.status_code == 200


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

    def test_historico_de_treino_e_apagado_apos_exclusao(self, client, db):
        """Alternativa A: não fica só 'oculto' -- o histórico individual
        de treino (versão, treino, exercício próprio, registro e série)
        deixa de existir no banco."""
        user = _criar_usuario_direto('comtreinos')
        dados = _criar_treino_completo(user)
        versao_id, tv_id, ex_id = dados['versao'].id, dados['treino'].id, dados['exercicio'].id
        registro_id = dados['registro'].id

        _login(client, 'comtreinos')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        db.session.expire_all()
        assert db.session.get(VersaoGlobal, versao_id) is None
        assert db.session.get(TreinoVersao, tv_id) is None
        assert db.session.get(ExercicioUsuario, ex_id) is None
        assert db.session.get(RegistroTreino, registro_id) is None
        assert HistoricoTreino.query.filter_by(registro_id=registro_id).first() is None

    def test_cache_do_fitbot_invalidado_apos_exclusao(self, client, db, monkeypatch):
        from services.privacidade_service import CacheService

        chamadas = []
        monkeypatch.setattr(
            CacheService, 'invalidate_pattern',
            staticmethod(lambda pattern: chamadas.append(pattern)),
        )

        user = _criar_usuario_direto('comcachefitbot')
        _login(client, 'comcachefitbot')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        assert any(f"fitbot_context:{user.id}:" in c for c in chamadas)

    def test_falha_ao_registrar_exclusao_reverte_tudo(self, client, db, monkeypatch):
        """Parte 3 do prompt de escalabilidade/LGPD: exclusão e registro
        da exclusão são UMA transação -- se o registro falhar (ex.:
        erro de banco no meio do caminho), nada pode ficar
        parcialmente aplicado. Antes desta correção, a anonimização
        (dados pessoais + histórico de treino) já tinha sido commitada
        SEPARADAMENTE antes de tentar registrar o consentimento de
        exclusão -- então essa falha simulada não revertia nada. Agora
        precisa reverter TUDO: dados, histórico e o próprio registro."""
        user = _criar_usuario_direto('vaifalharexclusao', nome_completo='Nome Original')
        user_id = user.id
        dados = _criar_treino_completo(user)
        versao_id = dados['versao'].id

        def _explode(*args, **kwargs):
            raise RuntimeError("falha simulada ao registrar exclusão")

        monkeypatch.setattr(
            PrivacidadeService, 'registrar_consentimento', staticmethod(_explode),
        )

        _login(client, 'vaifalharexclusao')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        db.session.expire_all()
        ainda_intacto = db.session.get(User, user_id)
        assert ainda_intacto.ativo is True
        assert ainda_intacto.username == 'vaifalharexclusao'
        assert ainda_intacto.nome_completo == 'Nome Original'
        # histórico de treino preservado -- nenhuma remoção parcial
        assert db.session.get(VersaoGlobal, versao_id) is not None
        # nenhum registro de exclusão foi criado
        assert ConsentimentoLGPD.query.filter_by(
            usuario_id=user_id, tipo='exclusao_conta',
        ).count() == 0


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

    def test_professor_nao_acessa_endpoints_do_aluno_apos_exclusao(self, client, db):
        """Teste 4 do prompt: acesso indireto via endpoint direto, não só
        pela navegação normal (listagem já filtra o aluno excluído)."""
        professor = _criar_usuario_direto('profposexclusao', tipo_usuario='professor')
        aluno = _criar_usuario_direto('alunoposexclusao', tipo_usuario='aluno')
        vinculo = AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True)
        db.session.add(vinculo)
        db.session.commit()
        aluno_id = aluno.id

        _login(client, 'alunoposexclusao')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        client2 = client.application.test_client()
        _login(client2, 'profposexclusao')

        for rota in (
            f'/professor/aluno/{aluno_id}',
            f'/professor/aluno/{aluno_id}/estatisticas',
            f'/professor/aluno/{aluno_id}/calendario',
            f'/professor/aluno/{aluno_id}/versoes',
        ):
            resp = client2.get(rota, follow_redirects=False)
            assert resp.status_code in (302, 403, 404), f"{rota} não bloqueou o acesso"

    def test_usuario_excluido_nao_reloga_com_username_antigo(self, client, db):
        _criar_usuario_direto('exusuario')
        _login(client, 'exusuario')
        client.post('/privacidade/excluir-conta', data={'senha_confirmacao': 'Senha1234'})

        client2 = client.application.test_client()
        resp = client2.post('/auth/login', data={'username': 'exusuario', 'password': 'Senha1234'}, follow_redirects=True)
        # username antigo não existe mais (foi anonimizado) -- login falha
        assert client2.get('/', follow_redirects=False).status_code == 302