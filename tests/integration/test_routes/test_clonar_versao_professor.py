"""
Clonagem de uma versão de treino DO PROFESSOR para um aluno:

  rota    POST /professor/aluno/<id>/versao/clonar-minha
  serviço VersaoService.clonar_versao_de_professor / _resolver_exercicio_do_aluno

Regras de negócio sensíveis: só clona versão do PRÓPRIO professor, só para
SEU aluno, nunca por cima de uma versão ativa, e exercícios personalizados
do professor são remapeados para a cópia do ALUNO (nunca apontam para o
exercício de outra pessoa).
"""

from datetime import date

import pytest

from models import (
    db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, ExercicioSistema, RegistroTreino,
)
from services.versao_service import VersaoService

URL = '/professor/aluno/{}/versao/clonar-minha'


def _user(username, tipo='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo)
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123!'})


def _flashes(client):
    with client.session_transaction() as sess:
        return list(sess.get('_flashes', []))


@pytest.fixture
def cenario(app):
    prof = _user('prof_clone', 'professor')
    aluno = _user('aluno_clone')
    db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
    db.session.commit()
    return prof.id, aluno.id


_SEQ_BASE = iter(range(1000, 10**6))


def _base(nome='Supino reto'):
    b = ExercicioSistema(nome=nome, id_original=next(_SEQ_BASE))
    db.session.add(b)
    db.session.commit()
    return b.id


def _versao(user_id, descricao='Modelo do professor', validade=None, numero=1, data_fim=None):
    v = VersaoGlobal(numero_versao=numero, descricao=descricao, divisao='LIVRE',
                     data_inicio=date(2024, 1, 1), data_fim=data_fim, user_id=user_id,
                     validade_meses=validade)
    db.session.add(v)
    db.session.commit()
    return v.id


def _treino(versao_id, codigo='A', nome='Treino A', ordem=0, descricao=None):
    t = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=nome, ordem=ordem,
                     descricao_treino=descricao)
    db.session.add(t)
    db.session.commit()
    return t.id


def _ve(treino_id, base=None, usuario=None, ordem=0, obs=None):
    ve = VersaoExercicio(treino_versao_id=treino_id, exercicio_base_id=base,
                         exercicio_usuario_id=usuario, ordem=ordem, observacao=obs)
    db.session.add(ve)
    db.session.commit()
    return ve.id


def _ex_usuario(user_id, nome, **kw):
    e = ExercicioUsuario(usuario_id=user_id, nome=nome, **kw)
    db.session.add(e)
    db.session.commit()
    return e.id


def _estrutura(versao_id):
    """[(codigo, nome, [(base_id, usuario_id, ordem, obs), ...]), ...]"""
    db.session.expire_all()
    saida = []
    for t in TreinoVersao.query.filter_by(versao_id=versao_id).order_by(TreinoVersao.ordem):
        exs = [(e.exercicio_base_id, e.exercicio_usuario_id, e.ordem, e.observacao)
               for e in VersaoExercicio.query.filter_by(treino_versao_id=t.id).order_by(VersaoExercicio.ordem)]
        saida.append((t.codigo, t.nome_treino, exs))
    return saida


# ======================================================================
# Serviço
# ======================================================================

class TestServicoClonar:

    def test_copia_treinos_e_exercicios_do_catalogo_com_observacao_e_ordem(self, cenario):
        prof, aluno = cenario
        b1, b2 = _base('Supino'), _base('Crucifixo')
        origem = _versao(prof, 'Peito e costas', validade=3)
        a = _treino(origem, 'A', 'Peito', 0, descricao='foco em carga')
        b = _treino(origem, 'B', 'Costas', 1)
        _ve(a, base=b1, ordem=0, obs='3x10')
        _ve(a, base=b2, ordem=1, obs='')
        _ve(b, base=b1, ordem=0)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert nova.id != origem and nova.user_id == aluno
        assert (nova.numero_versao, nova.descricao, nova.divisao) == (1, 'Peito e costas', 'LIVRE')
        assert nova.data_fim is None and nova.data_inicio is not None
        assert _estrutura(nova.id) == [
            ('A', 'Peito', [(b1, None, 0, '3x10'), (b2, None, 1, '')]),
            ('B', 'Costas', [(b1, None, 0, None)]),
        ]
        assert TreinoVersao.query.filter_by(versao_id=nova.id, codigo='A').one().descricao_treino == 'foco em carga'

    def test_origem_fica_intacta(self, cenario):
        prof, aluno = cenario
        origem = _versao(prof)
        t = _treino(origem)
        _ve(t, base=_base())
        antes = _estrutura(origem)

        VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert _estrutura(origem) == antes
        assert VersaoGlobal.query.filter_by(user_id=prof).count() == 1

    def test_nao_copia_historico_de_registros(self, cenario):
        prof, aluno = cenario
        origem = _versao(prof)
        t = _treino(origem)
        _ve(t, base=_base())

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert RegistroTreino.query.filter_by(versao_id=nova.id).count() == 0

    def test_numero_da_versao_continua_a_sequencia_do_aluno(self, cenario):
        prof, aluno = cenario
        _versao(aluno, 'antiga', numero=4, data_fim=date(2024, 6, 1))   # finalizada
        origem = _versao(prof)
        _treino(origem)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert nova.numero_versao == 5

    def test_descricao_e_truncada_em_200(self, cenario):
        prof, aluno = cenario
        origem = _versao(prof, 'x' * 300)
        _treino(origem)

        assert len(VersaoService.clonar_versao_de_professor(origem, prof, aluno).descricao) == 200

    # -- validade -------------------------------------------------------

    def test_validade_padrao_acompanha_a_da_origem(self, cenario):
        prof, aluno = cenario
        origem = _versao(prof, validade=6)

        assert VersaoService.clonar_versao_de_professor(origem, prof, aluno).validade_meses == 6

    @pytest.mark.parametrize('informado,esperado', [(2, 2), ('12', 12), (24, 24), ('', None), (None, None)])
    def test_validade_informada_sobrescreve(self, cenario, informado, esperado):
        prof, aluno = cenario
        origem = _versao(prof, validade=6)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno, validade_meses=informado)

        assert nova.validade_meses == esperado

    @pytest.mark.parametrize('ruim', [0, -1, 25, 'abc', '1.5'])
    def test_validade_invalida_levanta_e_nao_cria_nada(self, cenario, ruim):
        prof, aluno = cenario
        origem = _versao(prof)

        with pytest.raises(ValueError):
            VersaoService.clonar_versao_de_professor(origem, prof, aluno, validade_meses=ruim)

        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    # -- segurança / pré-condições ------------------------------------

    def test_versao_de_outro_professor_nao_pode_ser_clonada(self, cenario):
        prof, aluno = cenario
        outro = _user('prof_outro', 'professor')
        alheia = _versao(outro.id)
        _treino(alheia)

        with pytest.raises(ValueError, match='Ficha não encontrada'):
            VersaoService.clonar_versao_de_professor(alheia, prof, aluno)

        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_versao_inexistente(self, cenario):
        prof, aluno = cenario
        with pytest.raises(ValueError, match='Ficha não encontrada'):
            VersaoService.clonar_versao_de_professor(99999, prof, aluno)

    @pytest.mark.parametrize('prof_id,aluno_id', [(None, 1), (1, None), (0, 1), (None, None)])
    def test_ids_obrigatorios(self, app, prof_id, aluno_id):
        with pytest.raises(ValueError, match='obrigatórios'):
            VersaoService.clonar_versao_de_professor(1, prof_id, aluno_id)

    def test_aluno_com_versao_ativa_nao_recebe_outra(self, cenario):
        prof, aluno = cenario
        _versao(aluno, 'em andamento')
        origem = _versao(prof)

        with pytest.raises(ValueError, match='já tem uma ficha ativa'):
            VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 1

    def test_versao_finalizada_do_aluno_nao_impede(self, cenario):
        prof, aluno = cenario
        _versao(aluno, 'antiga', data_fim=date(2024, 3, 1))
        origem = _versao(prof)
        _treino(origem)

        assert VersaoService.clonar_versao_de_professor(origem, prof, aluno).user_id == aluno

    def test_falha_no_meio_faz_rollback_total(self, cenario, monkeypatch):
        prof, aluno = cenario
        origem = _versao(prof)
        t = _treino(origem)
        _ve(t, base=_base())
        monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('boom')))

        with pytest.raises(ValueError, match='Não foi possível clonar'):
            VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        monkeypatch.undo()
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0
        assert TreinoVersao.query.count() == 1             # só o da origem


# ======================================================================
# Exercícios personalizados do professor -> cópia do aluno
# ======================================================================

class TestRemapeamentoDeExercicios:

    def test_cria_copia_para_o_aluno_e_aponta_para_ela(self, cenario):
        prof, aluno = cenario
        ex_prof = _ex_usuario(prof, 'Remada do Zé', descricao='d', observacoes='o')
        origem = _versao(prof)
        _ve(_treino(origem), usuario=ex_prof, obs='lento')

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        copia = ExercicioUsuario.query.filter_by(usuario_id=aluno, nome='Remada do Zé').one()
        assert (copia.copiado_de_professor_id, copia.copiado_de_exercicio_id) == (prof, ex_prof)
        assert (copia.descricao, copia.observacoes) == ('d', 'o')
        assert _estrutura(nova.id) == [('A', 'Treino A', [(None, copia.id, 0, 'lento')])]
        assert copia.id != ex_prof

    def test_nunca_aponta_para_o_exercicio_do_professor(self, cenario):
        prof, aluno = cenario
        ex_prof = _ex_usuario(prof, 'Exclusivo')
        origem = _versao(prof)
        _ve(_treino(origem), usuario=ex_prof)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        ids = {e.exercicio_usuario_id for e in VersaoExercicio.query.join(TreinoVersao).filter(TreinoVersao.versao_id == nova.id)}
        assert ex_prof not in ids

    def test_reaproveita_copia_ja_propagada(self, cenario):
        prof, aluno = cenario
        ex_prof = _ex_usuario(prof, 'Agachamento X')
        ja_tem = _ex_usuario(aluno, 'Agachamento X', copiado_de_professor_id=prof, copiado_de_exercicio_id=ex_prof)
        origem = _versao(prof)
        _ve(_treino(origem), usuario=ex_prof)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert ExercicioUsuario.query.filter_by(usuario_id=aluno).count() == 1
        assert _estrutura(nova.id)[0][2][0][1] == ja_tem

    def test_reaproveita_exercicio_do_aluno_com_mesmo_nome_ignorando_caixa(self, cenario):
        prof, aluno = cenario
        ex_prof = _ex_usuario(prof, 'Rosca Direta')
        do_aluno = _ex_usuario(aluno, 'rosca direta')
        origem = _versao(prof)
        _ve(_treino(origem), usuario=ex_prof)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert ExercicioUsuario.query.filter_by(usuario_id=aluno).count() == 1
        assert _estrutura(nova.id)[0][2][0][1] == do_aluno

    def test_mesmo_exercicio_em_dois_treinos_gera_uma_unica_copia(self, cenario):
        prof, aluno = cenario
        ex_prof = _ex_usuario(prof, 'Prancha')
        origem = _versao(prof)
        _ve(_treino(origem, 'A', 'A', 0), usuario=ex_prof)
        _ve(_treino(origem, 'B', 'B', 1), usuario=ex_prof)

        VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert ExercicioUsuario.query.filter_by(usuario_id=aluno, nome='Prancha').count() == 1

    def test_exercicio_de_terceiro_dentro_da_versao_e_pulado(self, cenario):
        """Dado corrompido/malicioso: item da versão do professor aponta para
        exercício de OUTRA pessoa. Não pode vazar para o aluno."""
        prof, aluno = cenario
        terceiro = _user('terceiro')
        ex_alheio = _ex_usuario(terceiro.id, 'Segredo')
        base = _base()
        origem = _versao(prof)
        t = _treino(origem)
        _ve(t, usuario=ex_alheio, ordem=0)
        _ve(t, base=base, ordem=1)

        nova = VersaoService.clonar_versao_de_professor(origem, prof, aluno)

        assert _estrutura(nova.id) == [('A', 'Treino A', [(base, None, 1, None)])]
        assert ExercicioUsuario.query.filter_by(usuario_id=aluno).count() == 0


class TestResolverExercicioDoAluno:

    def test_cache_evita_nova_consulta_e_guarda_none_para_invalidos(self, cenario):
        prof, aluno = cenario
        terceiro = _user('t2')
        alheio = _ex_usuario(terceiro.id, 'Alheio')
        cache = {}

        assert VersaoService._resolver_exercicio_do_aluno(alheio, prof, aluno, cache) is None
        assert cache == {alheio: None}
        assert VersaoService._resolver_exercicio_do_aluno(alheio, prof, aluno, cache) is None

    def test_cache_hit_devolve_o_valor_guardado_sem_tocar_no_banco(self, app):
        assert VersaoService._resolver_exercicio_do_aluno(1, 2, 3, {1: 777}) == 777


# ======================================================================
# Rota
# ======================================================================

def _post(client, aluno, **form):
    return client.post(URL.format(aluno), data=form)


class TestRota:

    def test_get_lista_as_versoes_do_professor(self, client, cenario):
        prof, aluno = cenario
        _versao(prof, 'MODELO-DO-PROF-XYZ')
        _login(client, 'prof_clone')

        resp = client.get(URL.format(aluno))

        assert resp.status_code == 200
        assert 'MODELO-DO-PROF-XYZ' in resp.get_data(as_text=True)

    def test_get_nao_lista_versoes_de_outros(self, client, cenario):
        prof, aluno = cenario
        outro = _user('prof_o2', 'professor')
        _versao(outro.id, 'MODELO-ALHEIO-QWE')
        _login(client, 'prof_clone')

        assert 'MODELO-ALHEIO-QWE' not in client.get(URL.format(aluno)).get_data(as_text=True)

    def test_post_clona_e_redireciona_para_a_nova_versao(self, client, cenario):
        prof, aluno = cenario
        origem = _versao(prof, 'Full body', validade=3)
        _ve(_treino(origem), base=_base())
        _login(client, 'prof_clone')

        resp = _post(client, aluno, versao_id=str(origem))

        nova = VersaoGlobal.query.filter_by(user_id=aluno).one()
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(f'/professor/aluno/{aluno}/versao/{nova.id}')
        assert any(c == 'success' and 'v1' in m for c, m in _flashes(client))
        assert nova.validade_meses == 3                 # campo vazio = mantém

    def test_post_com_validade_sobrescreve(self, client, cenario):
        prof, aluno = cenario
        origem = _versao(prof, validade=3)
        _login(client, 'prof_clone')

        _post(client, aluno, versao_id=str(origem), validade_meses='9')

        assert VersaoGlobal.query.filter_by(user_id=aluno).one().validade_meses == 9

    def test_post_validade_invalida_mostra_erro_e_nao_clona(self, client, cenario):
        prof, aluno = cenario
        origem = _versao(prof)
        _login(client, 'prof_clone')

        resp = _post(client, aluno, versao_id=str(origem), validade_meses='99')

        assert resp.status_code == 200
        assert 'entre 1 e 24' in resp.get_data(as_text=True)
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    @pytest.mark.parametrize('versao_id', ['', 'abc', '99999'])
    def test_post_versao_id_ausente_ou_invalido(self, client, cenario, versao_id):
        _, aluno = cenario
        _login(client, 'prof_clone')

        resp = _post(client, aluno, versao_id=versao_id)

        assert resp.status_code == 200
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_post_com_versao_de_outro_professor_e_recusado(self, client, cenario):
        prof, aluno = cenario
        outro = _user('prof_o3', 'professor')
        alheia = _versao(outro.id)
        _login(client, 'prof_clone')

        resp = _post(client, aluno, versao_id=str(alheia))

        assert 'Ficha não encontrada.' in resp.get_data(as_text=True)
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_aluno_com_versao_ativa_e_redirecionado_com_aviso(self, client, cenario):
        prof, aluno = cenario
        ativa = _versao(aluno, 'ativa')
        origem = _versao(prof)
        _login(client, 'prof_clone')

        resp = _post(client, aluno, versao_id=str(origem))

        assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/versao/{ativa}')
        assert any(c == 'info' and 'já tem uma ficha ativa' in m for c, m in _flashes(client))
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 1

    def test_professor_nao_clona_para_aluno_de_outro_professor(self, client, cenario):
        prof, _ = cenario
        outro = _user('prof_o4', 'professor')
        aluno_alheio = _user('aluno_alheio')
        db.session.add(AlunoProfessor(aluno_id=aluno_alheio.id, professor_id=outro.id, ativo=True))
        db.session.commit()
        origem = _versao(prof)
        _login(client, 'prof_clone')

        resp = _post(client, aluno_alheio.id, versao_id=str(origem))

        assert resp.status_code == 302 and resp.headers['Location'].endswith('/professor/alunos')
        assert ('danger', 'Você não tem permissão para acessar este aluno.') in _flashes(client)
        assert VersaoGlobal.query.filter_by(user_id=aluno_alheio.id).count() == 0

    def test_aluno_inexistente_da_404(self, client, cenario):
        _login(client, 'prof_clone')
        assert client.get(URL.format(99999)).status_code == 404

    def test_aluno_logado_nao_acessa(self, client, cenario):
        prof, aluno = cenario
        origem = _versao(prof)
        _login(client, 'aluno_clone')

        resp = _post(client, aluno, versao_id=str(origem))

        assert resp.status_code in (302, 403)
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_anonimo_vai_para_o_login(self, app, cenario):
        _, aluno = cenario
        with app.app_context():
            resp = app.test_client().post(URL.format(aluno), data={'versao_id': '1'})
        assert resp.status_code == 302 and '/auth/login' in resp.headers['Location']
        assert VersaoGlobal.query.filter_by(user_id=aluno).count() == 0

    def test_erro_inesperado_vira_mensagem_generica(self, client, cenario, monkeypatch):
        prof, aluno = cenario
        origem = _versao(prof)
        _login(client, 'prof_clone')

        def _boom(**kw):
            raise RuntimeError('detalhe interno')

        monkeypatch.setattr(VersaoService, 'clonar_versao_de_professor', staticmethod(_boom))

        resp = _post(client, aluno, versao_id=str(origem))

        corpo = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'Não foi possível concluir a operação.' in corpo
        assert 'detalhe interno' not in corpo

    def test_admin_pode_clonar_a_versao_de_um_professor_para_o_aluno(self, client, cenario):
        """_aluno_ou_negar libera admin; a origem, porém, precisa ser do
        usuário logado -- então o admin só clona versões dele mesmo."""
        prof, aluno = cenario
        adm = _user('adm_clone', 'professor')
        adm.is_admin = True
        db.session.commit()
        minha = _versao(adm.id, 'do admin')
        _login(client, 'adm_clone')

        _post(client, aluno, versao_id=str(minha))

        assert VersaoGlobal.query.filter_by(user_id=aluno, descricao='do admin').count() == 1
