"""
Testes de integração do CAMINHO FELIZ (e dos erros de regra de negócio)
das rotas do aluno em routes/aluno/versao.py:

  POST /aluno/versao/<id>/treino/<tv_id>            (versao_salvar_treino)
  POST /aluno/versao/<id>/treino/<tv_id>/remover    (versao_remover_treino)
  POST /aluno/versao/<id>/finalizar                 (versao_finalizar)

tests/integration/test_versoes.py já cobre só os BLOQUEIOS (versão já
finalizada, IDOR). Aqui o foco é o que acontece numa versão ATIVA:
salvar de verdade, notificar o professor vinculado, finalizar, e as
mensagens de erro quando a regra de negócio recusa.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from models import (
    db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, ExercicioSistema, Notificacao,
)


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _criar_usuario(username, tipo_usuario='aluno'):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo_usuario, nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _vincular(aluno_id, professor_id):
    db.session.add(AlunoProfessor(
        aluno_id=aluno_id, professor_id=professor_id, ativo=True,
        data_associacao=datetime.now(timezone.utc),
    ))
    db.session.commit()


def _exercicio(user_id, nome):
    ex = ExercicioUsuario(usuario_id=user_id, nome=nome)
    db.session.add(ex)
    db.session.commit()
    return ex.id


def _versao_ativa(user_id, numero=1):
    v = VersaoGlobal(
        numero_versao=numero, descricao=f'v{numero}', divisao='LIVRE',
        data_inicio=date.today() - timedelta(days=3), data_fim=None, user_id=user_id,
    )
    db.session.add(v)
    db.session.commit()
    return v.id


def _treino(versao_id, codigo='A', nome='Treino A', descricao='desc original',
            exercicios_ids=()):
    tv = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=nome,
                      descricao_treino=descricao, ordem=0)
    db.session.add(tv)
    db.session.commit()
    for i, ex_id in enumerate(exercicios_ids):
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex_id, ordem=i))
    db.session.commit()
    return tv.id


def _flashes(resp):
    return resp.get_data(as_text=True)


@pytest.fixture
def cenario(app, client):
    """Aluno logado, com professor vinculado, uma versão ATIVA e um
    treino 'Treino A' que já tem o exercício 'Supino'."""
    with app.app_context():
        aluno = _criar_usuario('aluno1')
        professor = _criar_usuario('prof1', tipo_usuario='professor')
        _vincular(aluno.id, professor.id)
        supino = _exercicio(aluno.id, 'Supino')
        remada = _exercicio(aluno.id, 'Remada')
        versao_id = _versao_ativa(aluno.id)
        tv_id = _treino(versao_id, exercicios_ids=[supino])
        dados = dict(
            aluno_id=aluno.id, professor_id=professor.id, supino=supino,
            remada=remada, versao_id=versao_id, tv_id=tv_id,
        )
    _login(client, 'aluno1')
    return dados


def _url_salvar(c):
    return f"/aluno/versao/{c['versao_id']}/treino/{c['tv_id']}"


# ------------------------------------------------------------------
# salvar treino
# ------------------------------------------------------------------

class TestSalvarTreinoVersaoAtiva:

    def test_salva_nome_descricao_e_substitui_exercicios(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': '  Peito e Costas  ',
            'descricao_treino': 'nova descrição',
            'exercicios[]': [f"u_{c['remada']}", f"u_{c['supino']}"],
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert 'Treino salvo com sucesso!' in _flashes(resp)
        with app.app_context():
            tv = db.session.get(TreinoVersao, c['tv_id'])
            assert tv.nome_treino == 'Peito e Costas'          # strip aplicado
            assert tv.descricao_treino == 'nova descrição'
            ids = {ve.exercicio_usuario_id for ve in tv.exercicios}
            assert ids == {c['remada'], c['supino']}

    def test_preserva_a_ordem_em_que_os_exercicios_foram_enviados(self, client, app, cenario):
        c = cenario
        client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f"u_{c['remada']}", f"u_{c['supino']}"],   # remada ANTES de supino
        }, follow_redirects=True)

        with app.app_context():
            ordenados = sorted(
                VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id']),
                key=lambda ve: ve.ordem,
            )
            assert [ve.exercicio_usuario_id for ve in ordenados] == [c['remada'], c['supino']]
            assert [ve.ordem for ve in ordenados] == [0, 1]

    def test_preserva_a_ordem_intercalando_exercicios_do_usuario_e_da_base(self, client, app, cenario):
        c = cenario
        with app.app_context():
            base = ExercicioSistema(nome='Crucifixo', id_original='ord-1')
            db.session.add(base)
            db.session.commit()
            base_id = base.id

        client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f"b_{base_id}", f"u_{c['supino']}", f"b_{base_id}", f"u_{c['remada']}"],  # b, u, (b repetido), u
        }, follow_redirects=True)

        with app.app_context():
            ordenados = sorted(
                VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id']),
                key=lambda ve: ve.ordem,
            )
            assert [(ve.exercicio_base_id, ve.exercicio_usuario_id) for ve in ordenados] == [
                (base_id, None), (None, c['supino']), (None, c['remada']),
            ]
            assert [ve.ordem for ve in ordenados] == [0, 1, 2]

    def test_salva_observacao_por_exercicio_truncada_em_60_caracteres(self, client, app, cenario):
        c = cenario
        client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f"u_{c['supino']}"],
            f"observacao_u_{c['supino']}": '  ' + 'x' * 100 + '  ',
        }, follow_redirects=True)

        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id']).one()
            assert ve.observacao == 'x' * 60

    def test_sem_campo_descricao_mantem_a_descricao_ja_gravada(self, client, app, cenario):
        """O formulário novo não tem mais o campo 'descricao_treino': a
        ausência (None) NÃO pode apagar a descrição que já existia."""
        c = cenario
        client.post(_url_salvar(c), data={
            'nome_treino': 'Renomeado',
            'exercicios[]': [f"u_{c['supino']}"],
        }, follow_redirects=True)

        with app.app_context():
            tv = db.session.get(TreinoVersao, c['tv_id'])
            assert tv.nome_treino == 'Renomeado'
            assert tv.descricao_treino == 'desc original'

    def test_lista_vazia_de_exercicios_esvazia_o_treino(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
        }, follow_redirects=True)

        assert 'Treino salvo com sucesso!' in _flashes(resp)
        with app.app_context():
            assert VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id']).count() == 0

    def test_exercicio_de_outro_usuario_e_ignorado(self, client, app, cenario):
        """Chave 'u_<id>' de exercício que pertence a OUTRO usuário não
        pode entrar no treino (processar_exercicios_formulario filtra)."""
        c = cenario
        with app.app_context():
            outro = _criar_usuario('intruso')
            alheio = _exercicio(outro.id, 'Exercício alheio')

        client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f"u_{c['supino']}", f"u_{alheio}"],
        }, follow_redirects=True)

        with app.app_context():
            ids = {ve.exercicio_usuario_id
                   for ve in VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id'])}
            assert alheio not in ids
            assert c['supino'] in ids

    # ---------------- notificação ao professor ----------------

    def test_notifica_professor_com_diff_de_troca_de_exercicio(self, client, app, cenario):
        c = cenario
        client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f"u_{c['remada']}"],      # troca Supino -> Remada
        }, follow_redirects=True)

        with app.app_context():
            n = Notificacao.query.filter_by(destinatario_id=c['professor_id']).one()
            assert n.tipo == 'treino_editado'
            assert n.remetente_id == c['aluno_id']
            assert 'trocou "Supino" por "Remada"' in n.mensagem
            assert n.url.endswith(f"#treino-{c['tv_id']}")
            assert n.chave_agrupamento == f"treino_editar:{c['tv_id']}"

    def test_notificacao_sem_diff_quando_so_muda_o_nome(self, client, app, cenario):
        c = cenario
        client.post(_url_salvar(c), data={
            'nome_treino': 'Só o nome mudou', 'descricao_treino': 'desc original',
            'exercicios[]': [f"u_{c['supino']}"],
        }, follow_redirects=True)

        with app.app_context():
            n = Notificacao.query.filter_by(destinatario_id=c['professor_id']).one()
            assert n.mensagem.endswith('.')
            assert ' -- ' not in n.mensagem
            assert 'Só o nome mudou' in n.mensagem

    def test_aluno_sem_professor_salva_normalmente_sem_notificar(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('solitario')
            ex = _exercicio(aluno.id, 'Agachamento')
            versao_id = _versao_ativa(aluno.id)
            tv_id = _treino(versao_id, exercicios_ids=[ex])
            aluno_id = aluno.id
        _login(client, 'solitario')

        resp = client.post(f'/aluno/versao/{versao_id}/treino/{tv_id}', data={
            'nome_treino': 'Perna', 'descricao_treino': '', 'exercicios[]': [f'u_{ex}'],
        }, follow_redirects=True)

        assert 'Treino salvo com sucesso!' in _flashes(resp)
        with app.app_context():
            assert db.session.get(TreinoVersao, tv_id).nome_treino == 'Perna'
            assert Notificacao.query.filter_by(remetente_id=aluno_id).count() == 0

    # ---------------- erros de regra de negócio ----------------

    def test_nome_vazio_e_recusado_e_nada_muda(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': '   ', 'descricao_treino': 'x',
            'exercicios[]': [f"u_{c['remada']}"],
        }, follow_redirects=True)

        assert 'Nome do treino é obrigatório.' in _flashes(resp)
        with app.app_context():
            tv = db.session.get(TreinoVersao, c['tv_id'])
            assert tv.nome_treino == 'Treino A'
            assert [ve.exercicio_usuario_id for ve in tv.exercicios] == [c['supino']]
            assert Notificacao.query.count() == 0

    def test_nome_acima_de_100_caracteres_e_recusado(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'n' * 101, 'descricao_treino': '',
        }, follow_redirects=True)

        assert 'no máximo 100 caracteres' in _flashes(resp)
        with app.app_context():
            assert db.session.get(TreinoVersao, c['tv_id']).nome_treino == 'Treino A'

    def test_descricao_acima_de_200_caracteres_e_recusada(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': 'd' * 201,
        }, follow_redirects=True)

        assert 'Descrição do treino deve ter no máximo 200 caracteres.' in _flashes(resp)

    def test_excesso_de_exercicios_por_treino_e_recusado(self, client, app, cenario):
        from services.versao_service import VersaoService
        c = cenario
        with app.app_context():
            ids = [_exercicio(c['aluno_id'], f'Ex {i}')
                   for i in range(VersaoService.MAX_EXERCICIOS_POR_TREINO + 1)]

        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f'u_{i}' for i in ids],
        }, follow_redirects=True)

        assert f'Máximo de {VersaoService.MAX_EXERCICIOS_POR_TREINO} exercícios por treino.' in _flashes(resp)
        with app.app_context():
            tv = db.session.get(TreinoVersao, c['tv_id'])
            assert [ve.exercicio_usuario_id for ve in tv.exercicios] == [c['supino']]

    # ---------------- falhas inesperadas / resiliência ----------------

    def test_excecao_inesperada_mostra_mensagem_generica_sem_vazar_detalhe(self, client, app, cenario, monkeypatch):
        from services.versao_service import VersaoService

        def _explode(*a, **kw):
            raise RuntimeError('segredo interno: senha do banco')

        monkeypatch.setattr(VersaoService, 'salvar_treino_livre', staticmethod(_explode))
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
        }, follow_redirects=True)

        corpo = _flashes(resp)
        assert 'Não foi possível concluir a operação.' in corpo
        assert 'segredo interno' not in corpo
        with app.app_context():
            assert Notificacao.query.count() == 0

    def test_falha_ao_capturar_exercicios_antes_nao_impede_o_salvamento(self, client, app, cenario, monkeypatch):
        """A captura dos nomes 'antes' é best-effort (só serve pro diff da
        notificação): se quebrar, o treino ainda tem que ser salvo."""
        import routes.aluno.versao as mod

        class _QuebraNoGet:
            class query:
                @staticmethod
                def get(_id):
                    raise RuntimeError('boom')

        monkeypatch.setattr(mod, 'TreinoVersao', _QuebraNoGet)
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Salvou mesmo assim', 'descricao_treino': '',
            'exercicios[]': [f"u_{c['supino']}"],
        }, follow_redirects=True)

        assert 'Treino salvo com sucesso!' in _flashes(resp)
        with app.app_context():
            assert db.session.get(TreinoVersao, c['tv_id']).nome_treino == 'Salvou mesmo assim'

    def test_falha_ao_montar_diff_nao_impede_salvamento_nem_notificacao(self, client, app, cenario, monkeypatch):
        from services.exercicio_service import ExercicioService

        def _explode(*a, **kw):
            raise RuntimeError('catálogo fora do ar')

        monkeypatch.setattr(ExercicioService, 'get_exercicios_completos', staticmethod(_explode))
        c = cenario
        # Sem follow_redirects: a página de destino (ver_versao) TAMBÉM usa
        # get_exercicios_completos e quebraria por causa do monkeypatch.
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Treino A', 'descricao_treino': '',
            'exercicios[]': [f"u_{c['remada']}"],
        })

        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert ('success', 'Treino salvo com sucesso!') in sess['_flashes']
        with app.app_context():
            n = Notificacao.query.filter_by(destinatario_id=c['professor_id']).one()
            assert ' -- ' not in n.mensagem        # sem diff, texto genérico
            ids = [ve.exercicio_usuario_id
                   for ve in VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id'])]
            assert ids == [c['remada']]

    def test_usuario_sem_permissao_de_gerenciar_treino_e_barrado(self, client, app, cenario, monkeypatch):
        monkeypatch.setattr(User, 'pode_gerenciar_treino_proprio', lambda self: False)
        c = cenario
        resp = client.post(_url_salvar(c), data={
            'nome_treino': 'Invadido', 'descricao_treino': '',
        }, follow_redirects=True)

        assert 'Acesso negado.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(TreinoVersao, c['tv_id']).nome_treino == 'Treino A'

    def test_post_sem_login_redireciona_para_login(self, app, cenario):
        # app_context novo: o fixture `app` mantém um contexto aberto e o
        # Flask reaproveita o `g` dele entre requests -- sem isto o
        # flask-login "lembraria" o usuário logado pelo cenario.
        with app.app_context():
            resp = app.test_client().post(_url_salvar(cenario), data={'nome_treino': 'x'})
        assert resp.status_code in (301, 302)
        assert '/auth/login' in resp.headers['Location']
        with app.app_context():
            assert db.session.get(TreinoVersao, cenario['tv_id']).nome_treino == 'Treino A'


# ------------------------------------------------------------------
# remover treino (versão ativa)
# ------------------------------------------------------------------

class TestRemoverTreinoVersaoAtiva:

    def test_remove_treino_e_notifica_professor(self, client, app, cenario):
        c = cenario
        resp = client.post(_url_salvar(c) + '/remover', follow_redirects=True)

        assert 'Treino removido da ficha.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(TreinoVersao, c['tv_id']) is None
            assert VersaoExercicio.query.filter_by(treino_versao_id=c['tv_id']).count() == 0
            n = Notificacao.query.filter_by(destinatario_id=c['professor_id']).one()
            assert n.tipo == 'treino_excluido'

    def test_treino_com_registro_de_historico_nao_pode_ser_removido(self, client, app, cenario):
        from models import RegistroTreino
        c = cenario
        with app.app_context():
            db.session.add(RegistroTreino(
                user_id=c['aluno_id'], treino_versao_id=c['tv_id'],
                versao_id=c['versao_id'], periodo='2026-11', semana=1,
                exercicio_usuario_id=c['supino'],
                data_registro=datetime.now(timezone.utc),
            ))
            db.session.commit()

        client.post(_url_salvar(c) + '/remover', follow_redirects=True)

        with app.app_context():
            assert db.session.get(TreinoVersao, c['tv_id']) is not None
            assert Notificacao.query.count() == 0

    def test_excecao_inesperada_ao_remover_mostra_mensagem_generica(self, client, app, cenario, monkeypatch):
        from services.versao_service import VersaoService

        def _explode(*a, **kw):
            raise RuntimeError('boom')

        monkeypatch.setattr(VersaoService, 'remover_treino_livre', staticmethod(_explode))
        resp = client.post(_url_salvar(cenario) + '/remover', follow_redirects=True)
        assert 'Não foi possível concluir a operação.' in _flashes(resp)


# ------------------------------------------------------------------
# finalizar versão
# ------------------------------------------------------------------

class TestFinalizarVersao:

    def _url(self, c):
        return f"/aluno/versao/{c['versao_id']}/finalizar"

    def test_finaliza_grava_data_de_hoje_e_notifica_professor(self, client, app, cenario):
        c = cenario
        resp = client.post(self._url(c), follow_redirects=True)

        assert 'Ficha 1 finalizada!' in _flashes(resp)
        with app.app_context():
            versao = db.session.get(VersaoGlobal, c['versao_id'])
            assert versao.data_fim == datetime.now(timezone.utc).date()
            n = Notificacao.query.filter_by(destinatario_id=c['professor_id']).one()
            assert n.tipo == 'versao_finalizada'
            assert n.chave_agrupamento == f"versao_finalizar:{c['versao_id']}"
            assert '1' in n.mensagem

    def test_data_fim_nunca_vem_do_cliente(self, client, app, cenario):
        """A data de fim é SEMPRE a do servidor, mesmo que o cliente
        tente mandar uma no formulário."""
        c = cenario
        client.post(self._url(c), data={'data_fim': '1999-01-01'}, follow_redirects=True)

        with app.app_context():
            versao = db.session.get(VersaoGlobal, c['versao_id'])
            assert versao.data_fim == datetime.now(timezone.utc).date()

    def test_sem_nenhum_treino_nao_finaliza(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('vazio')
            versao_id = _versao_ativa(aluno.id)
        _login(client, 'vazio')

        resp = client.post(f'/aluno/versao/{versao_id}/finalizar', follow_redirects=True)

        assert 'Adicione pelo menos um treino antes de finalizar a ficha.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_id).data_fim is None

    def test_treino_sem_exercicio_nao_finaliza_e_aponta_qual(self, client, app, cenario):
        c = cenario
        with app.app_context():
            _treino(c['versao_id'], codigo='B', nome='Treino B', exercicios_ids=[])

        resp = client.post(self._url(c), follow_redirects=True)

        corpo = _flashes(resp)
        assert 'pelo menos um exercício antes de finalizar' in corpo
        assert 'Faltando em: B.' in corpo
        with app.app_context():
            assert db.session.get(VersaoGlobal, c['versao_id']).data_fim is None
            assert Notificacao.query.count() == 0

    def test_versao_ja_finalizada_nao_finaliza_de_novo(self, client, app, cenario):
        c = cenario
        client.post(self._url(c), follow_redirects=True)
        with app.app_context():
            Notificacao.query.delete()
            db.session.commit()

        resp = client.post(self._url(c), follow_redirects=True)

        assert 'já foi finalizada' in _flashes(resp)
        with app.app_context():
            assert Notificacao.query.count() == 0

    def test_idor_nao_finaliza_versao_de_outro_usuario(self, client, app, cenario):
        with app.app_context():
            outro = _criar_usuario('aluno2')
            versao_alheia = _versao_ativa(outro.id)
            _treino(versao_alheia, exercicios_ids=[_exercicio(outro.id, 'Ex')])

        resp = client.post(f'/aluno/versao/{versao_alheia}/finalizar', follow_redirects=True)

        assert 'Ficha não encontrada.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(VersaoGlobal, versao_alheia).data_fim is None

    def test_excecao_inesperada_ao_finalizar_mostra_mensagem_generica(self, client, app, cenario, monkeypatch):
        from services.versao_service import VersaoService

        def _explode(*a, **kw):
            raise RuntimeError('boom')

        monkeypatch.setattr(VersaoService, 'finalizar_livre', staticmethod(_explode))
        resp = client.post(self._url(cenario), follow_redirects=True)

        assert 'Não foi possível concluir a operação.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(VersaoGlobal, cenario['versao_id']).data_fim is None

    def test_usuario_sem_permissao_e_barrado(self, client, app, cenario, monkeypatch):
        monkeypatch.setattr(User, 'pode_gerenciar_treino_proprio', lambda self: False)
        resp = client.post(self._url(cenario), follow_redirects=True)

        assert 'Acesso negado.' in _flashes(resp)
        with app.app_context():
            assert db.session.get(VersaoGlobal, cenario['versao_id']).data_fim is None

    def test_sem_login_redireciona_para_login(self, app, cenario):
        with app.app_context():     # ver comentário em TestSalvarTreinoVersaoAtiva
            resp = app.test_client().post(self._url(cenario))
        assert resp.status_code in (301, 302)
        assert '/auth/login' in resp.headers['Location']
        with app.app_context():
            assert db.session.get(VersaoGlobal, cenario['versao_id']).data_fim is None
