"""
Testes de ExercicioService -- o código VIVO que ainda estava sem cobertura:

- buscar_por_chaves (exercícios avulsos da tela de registrar treino; recebe
  texto digitado/enviado pelo usuário, então precisa tolerar lixo e respeitar IDOR)
- get_by_id / get_exercicios_completos / get_exercicios_dos_treinos / get_by_treino
- delete_exercicio_usuario / delete_exercicio_customizado / update_exercicio_customizado
- reordenar_exercicios
- get_ultima_sessao_series / get_ultima_sessao_series_em_lote / get_ultimas_series

Detalhe que atravessa vários testes: exercicios_usuario e exercicios_sistema têm
sequências de ID INDEPENDENTES (o mesmo número pode existir nas duas tabelas).
Por isso vários cenários criam um exercício de cada tabela com o mesmo id.
"""

import itertools
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect as sa_inspect

import services.exercicio_service as mod
from models import (
    db, User, Musculo, ExercicioSistema, ExercicioUsuario, VersaoGlobal, TreinoVersao,
    VersaoExercicio, RegistroTreino, HistoricoTreino,
)
from services.exercicio_service import ExercicioService

_seq = itertools.count(1)


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _user(username):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u.id


def _musculo(nome='peito', exibicao='Peito'):
    m = Musculo(nome=nome, nome_exibicao=exibicao)
    db.session.add(m)
    db.session.commit()
    return m.id


def _base(nome='Supino Reto', grupo='Peito', instrucao='  empurre a barra  ', secundarios=None):
    ex = ExercicioSistema(id_original=f'ex{next(_seq):04d}', nome=nome, grupo_muscular=grupo,
                          instrucao_pt=instrucao, musculos_secundarios=secundarios)
    db.session.add(ex)
    db.session.commit()
    return ex.id


def _meu(user_id, nome='Rosca', musculo_id=None, descricao=None):
    ex = ExercicioUsuario(usuario_id=user_id, nome=nome, musculo_id=musculo_id, descricao=descricao)
    db.session.add(ex)
    db.session.commit()
    return ex.id


def _versao(user_id, numero=1, inicio=date(2024, 1, 1), fim=None):
    v = VersaoGlobal(numero_versao=numero, descricao=f'v{numero}', divisao='LIVRE',
                     data_inicio=inicio, data_fim=fim, user_id=user_id)
    db.session.add(v)
    db.session.commit()
    return v.id


def _treino(versao_id, codigo='A'):
    t = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=f'Treino {codigo}', ordem=0)
    db.session.add(t)
    db.session.commit()
    return t.id


def _ve(treino_id, usuario_id=None, base_id=None, ordem=0):
    ve = VersaoExercicio(treino_versao_id=treino_id, exercicio_usuario_id=usuario_id,
                         exercicio_base_id=base_id, ordem=ordem)
    db.session.add(ve)
    db.session.commit()
    return ve.id


def _registro(user_id, versao_id, treino_id, series, usuario_id=None, base_id=None, dias_atras=0):
    r = RegistroTreino(
        user_id=user_id, versao_id=versao_id, treino_versao_id=treino_id,
        periodo='2026-11', semana=1, exercicio_usuario_id=usuario_id, exercicio_base_id=base_id,
        data_registro=datetime.now(timezone.utc) - timedelta(days=dias_atras),
    )
    db.session.add(r)
    db.session.flush()
    for ordem, (carga, reps) in enumerate(series):
        db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=ordem))
    db.session.commit()
    return r.id


# ------------------------------------------------------------------
# buscar_por_chaves
# ------------------------------------------------------------------

class TestBuscarPorChaves:

    @pytest.mark.parametrize('entrada', [None, [], ()])
    def test_sem_chaves_retorna_dict_vazio(self, app, entrada):
        assert ExercicioService.buscar_por_chaves(entrada, user_id=1) == {}

    @pytest.mark.parametrize('lixo', [
        None, '', 5, 3.2, ['u_1'], 'x_1', 'u_', 'b_', 'u_abc', 'b_1x', 'u_-1', 'u_1.5',
        'U_1', ' u_1', 'u_ 1', 'u__1', "u_1'; DROP TABLE users;--",
    ])
    def test_chaves_invalidas_sao_ignoradas_sem_derrubar_a_pagina(self, app, lixo):
        """A chave vem da URL/form: lixo nunca pode virar 500 (int() solto)."""
        uid = _user('lixo')
        _meu(uid, 'Rosca')
        _base('Supino')

        assert ExercicioService.buscar_por_chaves([lixo], user_id=uid) == {}

    def test_resolve_exercicio_do_proprio_usuario_com_os_atributos_do_card(self, app):
        uid = _user('dono')
        mid = _musculo('biceps', 'Bíceps')
        ex_id = _meu(uid, 'Rosca Direta', musculo_id=mid, descricao='  pegada supinada  ')

        r = ExercicioService.buscar_por_chaves([f'u_{ex_id}'], user_id=uid)

        ex = r[f'u_{ex_id}']
        assert ex.nome == 'Rosca Direta'
        assert (ex.tipo, ex.prefixo, ex.avulso) == ('usuario', 'u_', True)
        assert ex.musculo == ex.musculo_nome == 'Bíceps'
        assert ex.descricao_completa == 'pegada supinada'
        assert ex.musculos_secundarios_lista == []
        assert ex.observacao_treino is None

    def test_exercicio_sem_musculo_mostra_na(self, app):
        uid = _user('semmusculo')
        ex_id = _meu(uid, 'Sem músculo', musculo_id=None, descricao=None)

        ex = ExercicioService.buscar_por_chaves([f'u_{ex_id}'], user_id=uid)[f'u_{ex_id}']

        assert ex.musculo == 'N/A'
        assert ex.descricao_completa == ''

    def test_idor_exercicio_de_outro_usuario_nao_resolve(self, app):
        dono, intruso = _user('dono2'), _user('intruso2')
        alheio = _meu(dono, 'Exercício privado')

        r = ExercicioService.buscar_por_chaves([f'u_{alheio}'], user_id=intruso)

        assert r == {}

    def test_resolve_exercicio_do_catalogo_global_sem_checar_dono(self, app):
        uid = _user('qualquer')
        b = _base('Agachamento', grupo='Pernas', instrucao='  desça até 90°  ',
                  secundarios=['Glúteos', 'Core'])

        ex = ExercicioService.buscar_por_chaves([f'b_{b}'], user_id=uid)[f'b_{b}']

        assert (ex.tipo, ex.prefixo, ex.avulso) == ('base', 'b_', True)
        assert ex.musculo == 'Pernas'
        assert ex.descricao_completa == 'desça até 90°'
        assert ex.musculos_secundarios_lista == ['Glúteos', 'Core']

    def test_base_sem_grupo_nem_instrucao_nem_secundarios_usa_padroes(self, app):
        uid = _user('padroes')
        b = _base('Misterioso', grupo=None, instrucao=None, secundarios=None)

        ex = ExercicioService.buscar_por_chaves([f'b_{b}'], user_id=uid)[f'b_{b}']

        assert ex.musculo == 'N/A'
        assert ex.descricao_completa == ''
        assert ex.musculos_secundarios_lista == []

    def test_mistura_u_e_b_com_mesmo_numero_de_id_sem_colidir(self, app):
        """u_1 e b_1 são exercícios DIFERENTES (tabelas distintas)."""
        uid = _user('colide')
        u = _meu(uid, 'Meu Exercício')
        b = _base('Exercício do Catálogo')
        assert u == b == 1

        r = ExercicioService.buscar_por_chaves(['u_1', 'b_1'], user_id=uid)

        assert set(r) == {'u_1', 'b_1'}
        assert r['u_1'].nome == 'Meu Exercício'
        assert r['b_1'].nome == 'Exercício do Catálogo'

    def test_chaves_repetidas_e_ids_inexistentes(self, app):
        uid = _user('dup')
        u = _meu(uid, 'Rosca')

        r = ExercicioService.buscar_por_chaves([f'u_{u}', f'u_{u}', 'u_9999', 'b_9999'], user_id=uid)

        assert list(r) == [f'u_{u}']

    def test_so_u_ou_so_b_nao_consulta_a_outra_tabela(self, app):
        uid = _user('so')
        u = _meu(uid, 'Só meu')
        b = _base('Só base')

        assert list(ExercicioService.buscar_por_chaves([f'u_{u}'], user_id=uid)) == [f'u_{u}']
        assert list(ExercicioService.buscar_por_chaves([f'b_{b}'], user_id=uid)) == [f'b_{b}']

    def test_objetos_saem_da_sessao_e_nao_sujam_o_banco(self, app):
        """Os atributos extras (tipo/prefixo/...) NÃO podem virar UPDATE
        pendente no catálogo global (causa histórica de WORKER TIMEOUT)."""
        uid = _user('limpo')
        u, b = _meu(uid, 'Meu'), _base('Base')

        r = ExercicioService.buscar_por_chaves([f'u_{u}', f'b_{b}'], user_id=uid)

        assert all(sa_inspect(ex).detached for ex in r.values())
        assert not db.session.dirty


# ------------------------------------------------------------------
# get_by_id
# ------------------------------------------------------------------

class TestGetById:

    def test_exercicio_base_vem_marcado_e_destacado_da_sessao(self, app):
        b = _base('Supino', grupo='Peito')

        ex = ExercicioService.get_by_id(b, user_id=None)

        assert (ex.tipo, ex.prefixo, ex.is_custom, ex.musculo) == ('base', 'b_', False, 'Peito')
        assert sa_inspect(ex).detached

    def test_base_sem_grupo_muscular_vira_nao_especificado(self, app):
        b = _base('Sem grupo', grupo=None)
        assert ExercicioService.get_by_id(b).musculo == 'Não especificado'

    def test_exercicio_do_usuario_quando_nao_existe_no_catalogo(self, app):
        """Ids de exercício de usuário só são alcançados se o mesmo número
        NÃO existir no catálogo (get_by_id consulta o catálogo primeiro)."""
        uid = _user('byid')
        mid = _musculo('costas', 'Costas')
        _base('Ocupa o id 1')                                   # catálogo ocupa o id 1
        _meu(uid, 'Remada A')                                   # usuario id 1
        u2 = _meu(uid, 'Remada B', musculo_id=mid)              # usuario id 2 (livre no catálogo)

        ex = ExercicioService.get_by_id(u2, user_id=uid, load_relations=True)

        assert ex.nome == 'Remada B'
        assert (ex.tipo, ex.prefixo, ex.is_custom) == ('usuario', 'u_', True)
        assert ex.musculo == ex.musculo_nome == 'Costas'

    def test_exercicio_do_usuario_sem_load_relations_tambem_resolve(self, app):
        uid = _user('byid2')
        _base('Ocupa o id 1')
        _meu(uid, 'Remada A')
        u2 = _meu(uid, 'Remada B')

        ex = ExercicioService.get_by_id(u2, user_id=uid)

        assert ex is not None and ex.nome == 'Remada B'

    def test_idor_nao_devolve_exercicio_de_outro_usuario(self, app):
        dono, intruso = _user('dono3'), _user('intruso3')
        _base('Ocupa o id 1')
        _meu(dono, 'a')
        alheio = _meu(dono, 'Privado')

        assert ExercicioService.get_by_id(alheio, user_id=intruso) is None

    def test_sem_usuario_so_enxerga_o_catalogo(self, app):
        uid = _user('anon')
        _base('Ocupa o id 1')
        _meu(uid, 'a')
        so_meu = _meu(uid, 'Só meu')

        assert ExercicioService.get_by_id(so_meu, user_id=None) is None

    def test_inexistente_retorna_none(self, app):
        assert ExercicioService.get_by_id(424242, user_id=_user('nada')) is None

    def test_erro_inesperado_retorna_none_sem_propagar(self, app, monkeypatch):
        class _Quebrado:
            class query:
                @staticmethod
                def get(_):
                    raise RuntimeError('banco fora do ar')

        monkeypatch.setattr(mod, 'ExercicioSistema', _Quebrado)
        assert ExercicioService.get_by_id(1, user_id=1) is None


# ------------------------------------------------------------------
# get_exercicios_completos
# ------------------------------------------------------------------

class TestGetExerciciosCompletos:

    def test_sem_usuario_retorna_lista_vazia(self, app):
        assert ExercicioService.get_exercicios_completos(user_id=None) == []

    def test_junta_catalogo_e_pessoais_ordenados_por_nome_sem_diferenciar_caixa(self, app):
        uid = _user('comp')
        mid = _musculo('biceps', 'Bíceps')
        _base('agachamento', grupo='Pernas')
        _base('Supino', grupo='Peito')
        _meu(uid, 'Barra fixa')
        _meu(uid, 'rosca', musculo_id=mid)

        r = ExercicioService.get_exercicios_completos(user_id=uid)

        assert [e.nome for e in r] == ['agachamento', 'Barra fixa', 'rosca', 'Supino']

    def test_atributos_de_cada_tipo(self, app):
        uid = _user('attrs')
        mid = _musculo('biceps', 'Bíceps')
        _base('Base A', grupo='Pernas')
        _base('Base B', grupo=None)
        _meu(uid, 'Meu A', musculo_id=mid)
        _meu(uid, 'Meu B')

        r = {e.nome: e for e in ExercicioService.get_exercicios_completos(user_id=uid)}

        assert (r['Base A'].tipo, r['Base A'].prefixo, r['Base A'].is_custom) == ('base', 'b_', False)
        assert r['Base A'].musculo == 'Pernas'
        assert r['Base B'].musculo == 'Não especificado'
        assert (r['Meu A'].tipo, r['Meu A'].prefixo, r['Meu A'].is_custom) == ('usuario', 'u_', True)
        assert r['Meu A'].musculo == 'Bíceps'
        assert r['Meu B'].musculo == 'Não especificado'

    def test_nao_inclui_exercicios_pessoais_de_outros_usuarios(self, app):
        a, b = _user('ua'), _user('ub')
        _meu(a, 'Do A')
        _meu(b, 'Do B')

        assert [e.nome for e in ExercicioService.get_exercicios_completos(user_id=a)] == ['Do A']

    def test_registros_do_catalogo_global_sao_contados_so_do_usuario(self, app):
        """O catálogo é global: ex.registros não pode somar o histórico de
        TODOS os usuários (vazamento de dado + contagem errada)."""
        a, b = _user('ra'), _user('rb')
        base = _base('Supino')
        va, vb = _versao(a), _versao(b)
        ta, tb = _treino(va), _treino(vb)
        _registro(a, va, ta, [(50, 10)], base_id=base)
        _registro(a, va, ta, [(55, 8)], base_id=base, dias_atras=1)
        _registro(b, vb, tb, [(80, 5)], base_id=base)

        ex_a = ExercicioService.get_exercicios_completos(user_id=a)[0]
        ex_b = ExercicioService.get_exercicios_completos(user_id=b)[0]

        assert len(ex_a.registros) == 2
        assert len(ex_b.registros) == 1

    def test_registros_do_exercicio_pessoal(self, app):
        uid = _user('rp')
        meu = _meu(uid, 'Meu')
        v = _versao(uid)
        t = _treino(v)
        _registro(uid, v, t, [(20, 12)], usuario_id=meu)

        ex = ExercicioService.get_exercicios_completos(user_id=uid)[0]

        assert len(ex.registros) == 1

    def test_objetos_destacados_e_sessao_limpa(self, app):
        uid = _user('limpo2')
        _base('Base')
        _meu(uid, 'Meu')

        r = ExercicioService.get_exercicios_completos(user_id=uid)

        assert all(sa_inspect(e).detached for e in r)
        assert not db.session.dirty

    def test_erro_inesperado_retorna_lista_vazia(self, app, monkeypatch):
        class _Quebrado:
            class query:
                @staticmethod
                def order_by(*a, **k):
                    raise RuntimeError('boom')
            nome = None

        monkeypatch.setattr(mod, 'ExercicioSistema', _Quebrado)
        assert ExercicioService.get_exercicios_completos(user_id=1) == []


# ------------------------------------------------------------------
# get_exercicios_dos_treinos
# ------------------------------------------------------------------

class TestGetExerciciosDosTreinos:

    def test_sem_usuario_retorna_vazio(self, app):
        assert ExercicioService.get_exercicios_dos_treinos(user_id=None) == []

    def test_so_traz_exercicios_que_estao_em_algum_treino(self, app):
        uid = _user('dt1')
        usado, nao_usado = _meu(uid, 'Usado'), _meu(uid, 'Nunca usado')
        base_usado = _base('Base usada')
        _base('Base nunca usada')
        v = _versao(uid)
        t = _treino(v)
        _ve(t, usuario_id=usado, ordem=0)
        _ve(t, base_id=base_usado, ordem=1)

        r = ExercicioService.get_exercicios_dos_treinos(user_id=uid)

        assert [e.nome for e in r] == ['Base usada', 'Usado']

    def test_ordena_por_nome_ignorando_caixa(self, app):
        uid = _user('dt2')
        v = _versao(uid)
        t = _treino(v)
        for i, nome in enumerate(['zebra', 'Abdominal', 'barra']):
            _ve(t, usuario_id=_meu(uid, nome), ordem=i)

        assert [e.nome for e in ExercicioService.get_exercicios_dos_treinos(user_id=uid)] == \
            ['Abdominal', 'barra', 'zebra']

    def test_exercicio_que_mudou_de_treino_fica_no_treino_da_versao_mais_recente(self, app):
        uid = _user('dt3')
        rosca = _meu(uid, 'Rosca')
        v_velha = _versao(uid, 1, inicio=date(2024, 1, 1), fim=date(2024, 6, 1))
        v_nova = _versao(uid, 2, inicio=date(2025, 1, 1))
        t_velho = _treino(v_velha, 'A')
        t_novo = _treino(v_nova, 'B')
        _ve(t_velho, usuario_id=rosca)
        _ve(t_novo, usuario_id=rosca)

        r = ExercicioService.get_exercicios_dos_treinos(user_id=uid)

        assert len(r) == 1
        assert r[0].treino_id == t_novo
        assert r[0].treino_ref.codigo == 'B'

    def test_atributos_de_cada_tipo(self, app):
        uid = _user('dt4')
        mid = _musculo('biceps', 'Bíceps')
        meu = _meu(uid, 'Meu', musculo_id=mid)
        sem = _meu(uid, 'Sem músculo')
        base = _base('Base', grupo='Pernas')
        sem_grupo = _base('Base sem grupo', grupo=None)
        v = _versao(uid)
        t = _treino(v)
        for i, kw in enumerate([{'usuario_id': meu}, {'usuario_id': sem},
                                {'base_id': base}, {'base_id': sem_grupo}]):
            _ve(t, ordem=i, **kw)

        r = {e.nome: e for e in ExercicioService.get_exercicios_dos_treinos(user_id=uid)}

        assert (r['Meu'].tipo, r['Meu'].prefixo, r['Meu'].is_custom, r['Meu'].musculo) == \
            ('usuario', 'u_', True, 'Bíceps')
        assert r['Sem músculo'].musculo == 'Não especificado'
        assert (r['Base'].tipo, r['Base'].prefixo, r['Base'].is_custom, r['Base'].musculo) == \
            ('base', 'b_', False, 'Pernas')
        assert r['Base sem grupo'].musculo == 'Não especificado'

    def test_nao_mistura_treinos_de_outros_usuarios(self, app):
        a, b = _user('dta'), _user('dtb')
        ex_a, ex_b = _meu(a, 'Do A'), _meu(b, 'Do B')
        _ve(_treino(_versao(a)), usuario_id=ex_a)
        _ve(_treino(_versao(b)), usuario_id=ex_b)

        assert [e.nome for e in ExercicioService.get_exercicios_dos_treinos(user_id=a)] == ['Do A']

    def test_usuario_sem_treinos_retorna_vazio(self, app):
        assert ExercicioService.get_exercicios_dos_treinos(user_id=_user('dt5')) == []


# ------------------------------------------------------------------
# get_by_treino (orquestração -- os serviços chamados são testados à parte)
# ------------------------------------------------------------------

class TestGetByTreino:

    @pytest.fixture
    def servicos(self, monkeypatch):
        from services.treino_service import TreinoService
        from services.versao_service import VersaoService
        estado = SimpleNamespace(chamadas=[], treino=SimpleNamespace(codigo='B'),
                                 versao=SimpleNamespace(id=77), exercicios=['ex1', 'ex2'])

        monkeypatch.setattr(TreinoService, 'get_by_id',
                            staticmethod(lambda treino_id, user_id=None: estado.treino))
        monkeypatch.setattr(VersaoService, 'get_ativa_por_data',
                            staticmethod(lambda data, user_id=None: estado.versao))

        def _get_exercicios(versao_id, treino_codigo=None, user_id=None):
            estado.chamadas.append((versao_id, treino_codigo, user_id))
            return estado.exercicios

        monkeypatch.setattr(VersaoService, 'get_exercicios', staticmethod(_get_exercicios))
        return estado

    def test_sem_usuario_retorna_vazio(self, app, servicos):
        assert ExercicioService.get_by_treino(1, user_id=None) == []
        assert servicos.chamadas == []

    def test_treino_inexistente_retorna_vazio(self, app, servicos):
        servicos.treino = None
        assert ExercicioService.get_by_treino(1, user_id=5) == []
        assert servicos.chamadas == []

    def test_sem_versao_ativa_retorna_vazio(self, app, servicos):
        servicos.versao = None
        assert ExercicioService.get_by_treino(1, user_id=5) == []
        assert servicos.chamadas == []

    def test_caminho_feliz_busca_na_versao_ativa_pelo_codigo_do_treino(self, app, servicos):
        r = ExercicioService.get_by_treino(1, user_id=5)

        assert r == ['ex1', 'ex2']
        assert servicos.chamadas == [(77, 'B', 5)]

    def test_erro_inesperado_retorna_vazio(self, app, servicos, monkeypatch):
        from services.versao_service import VersaoService

        def _boom(*a, **k):
            raise RuntimeError('boom')

        monkeypatch.setattr(VersaoService, 'get_exercicios', staticmethod(_boom))
        assert ExercicioService.get_by_treino(1, user_id=5) == []


# ------------------------------------------------------------------
# delete_* / update_exercicio_customizado
# ------------------------------------------------------------------

@pytest.mark.parametrize('deletar', [
    ExercicioService.delete_exercicio_usuario,
    ExercicioService.delete_exercicio_customizado,
], ids=['delete_exercicio_usuario', 'delete_exercicio_customizado'])
class TestDeleteExercicio:

    def test_remove_exercicio_proprio_que_nao_esta_em_uso(self, app, deletar):
        uid = _user('del1')
        ex = _meu(uid, 'Descartável')

        assert deletar(ex, user_id=uid) is True
        assert db.session.get(ExercicioUsuario, ex) is None

    def test_nao_remove_se_esta_em_uso_em_algum_treino(self, app, deletar):
        uid = _user('del2')
        ex = _meu(uid, 'Em uso')
        _ve(_treino(_versao(uid)), usuario_id=ex)

        assert deletar(ex, user_id=uid) is False
        assert db.session.get(ExercicioUsuario, ex) is not None

    def test_idor_nao_remove_exercicio_de_outro_usuario(self, app, deletar):
        dono, intruso = _user('del3'), _user('del4')
        ex = _meu(dono, 'Do dono')

        assert deletar(ex, user_id=intruso) is False
        assert db.session.get(ExercicioUsuario, ex) is not None

    def test_inexistente_retorna_false(self, app, deletar):
        assert deletar(999999, user_id=_user('del5')) is False

    def test_sem_usuario_retorna_false(self, app, deletar):
        uid = _user('del6')
        ex = _meu(uid, 'Intacto')

        assert deletar(ex, user_id=None) is False
        assert db.session.get(ExercicioUsuario, ex) is not None


class TestUpdateExercicioCustomizado:

    def test_atualiza_so_os_campos_enviados(self, app):
        uid = _user('up1')
        m1, m2 = _musculo('peito', 'Peito'), _musculo('costas', 'Costas')
        ex = _meu(uid, 'Nome antigo', musculo_id=m1, descricao='desc antiga')

        r = ExercicioService.update_exercicio_customizado(ex, user_id=uid, nome='Nome novo', musculo_id=m2)

        assert r.nome == 'Nome novo'
        assert r.musculo_id == m2
        assert r.descricao == 'desc antiga'              # não enviada: intacta
        db.session.expire_all()
        assert db.session.get(ExercicioUsuario, ex).nome == 'Nome novo'

    def test_atualiza_descricao(self, app):
        uid = _user('up2')
        ex = _meu(uid, 'X')

        ExercicioService.update_exercicio_customizado(ex, user_id=uid, descricao='nova')

        db.session.expire_all()
        assert db.session.get(ExercicioUsuario, ex).descricao == 'nova'

    def test_idor_nao_atualiza_exercicio_de_outro_usuario(self, app):
        dono, intruso = _user('up3'), _user('up4')
        ex = _meu(dono, 'Original')

        assert ExercicioService.update_exercicio_customizado(ex, user_id=intruso, nome='Invadido') is None
        db.session.expire_all()
        assert db.session.get(ExercicioUsuario, ex).nome == 'Original'

    def test_inexistente_retorna_none(self, app):
        assert ExercicioService.update_exercicio_customizado(999999, user_id=_user('up5'), nome='x') is None

    def test_sem_usuario_retorna_none(self, app):
        uid = _user('up6')
        ex = _meu(uid, 'Intacto')

        assert ExercicioService.update_exercicio_customizado(ex, user_id=None, nome='x') is None
        db.session.expire_all()
        assert db.session.get(ExercicioUsuario, ex).nome == 'Intacto'


# ------------------------------------------------------------------
# reordenar_exercicios
# ------------------------------------------------------------------

class TestReordenarExercicios:

    @pytest.fixture
    def cenario(self, app):
        uid = _user('ord')
        u1, u2 = _meu(uid, 'U1'), _meu(uid, 'U2')
        b1 = _base('B1')
        v = _versao(uid)
        t = _treino(v, 'A')
        for i, kw in enumerate([{'usuario_id': u1}, {'usuario_id': u2}, {'base_id': b1}]):
            _ve(t, ordem=i, **kw)
        return SimpleNamespace(uid=uid, u1=u1, u2=u2, b1=b1, versao=v, treino=t)

    def _ordens(self, c):
        db.session.expire_all()
        rows = VersaoExercicio.query.filter_by(treino_versao_id=c.treino).all()
        return {(f'u_{r.exercicio_usuario_id}' if r.exercicio_usuario_id else f'b_{r.exercicio_base_id}'): r.ordem
                for r in rows}

    def test_reordena_misturando_exercicios_de_usuario_e_do_catalogo(self, app, cenario):
        c = cenario
        nova = [f'b_{c.b1}', f'u_{c.u2}', f'u_{c.u1}']

        assert ExercicioService.reordenar_exercicios(c.versao, 'A', nova, user_id=c.uid) is True

        assert self._ordens(c) == {f'b_{c.b1}': 0, f'u_{c.u2}': 1, f'u_{c.u1}': 2}

    def test_codigo_do_treino_nao_diferencia_caixa(self, app, cenario):
        c = cenario
        assert ExercicioService.reordenar_exercicios(
            c.versao, 'a', [f'u_{c.u2}', f'u_{c.u1}', f'b_{c.b1}'], user_id=c.uid) is True
        assert self._ordens(c)[f'u_{c.u2}'] == 0

    def test_item_sem_prefixo_conhecido_e_ignorado(self, app, cenario):
        c = cenario
        ExercicioService.reordenar_exercicios(c.versao, 'A', ['x_7', f'u_{c.u2}', f'u_{c.u1}'], user_id=c.uid)
        assert self._ordens(c)[f'u_{c.u2}'] == 0 and self._ordens(c)[f'u_{c.u1}'] == 1

    def test_id_nao_numerico_retorna_false_e_nao_altera_nada(self, app, cenario):
        c = cenario
        antes = self._ordens(c)

        assert ExercicioService.reordenar_exercicios(c.versao, 'A', ['u_abc'], user_id=c.uid) is False
        assert self._ordens(c) == antes

    def test_idor_versao_de_outro_usuario_retorna_false(self, app, cenario):
        c = cenario
        intruso = _user('ord_intruso')
        antes = self._ordens(c)

        assert ExercicioService.reordenar_exercicios(
            c.versao, 'A', [f'u_{c.u2}', f'u_{c.u1}'], user_id=intruso) is False
        assert self._ordens(c) == antes

    def test_treino_inexistente_retorna_false(self, app, cenario):
        c = cenario
        assert ExercicioService.reordenar_exercicios(c.versao, 'Z', [], user_id=c.uid) is False

    def test_codigo_vazio_ou_none_retorna_false(self, app, cenario):
        c = cenario
        assert ExercicioService.reordenar_exercicios(c.versao, None, [], user_id=c.uid) is False
        assert ExercicioService.reordenar_exercicios(c.versao, '', [], user_id=c.uid) is False

    def test_versao_inexistente_retorna_false(self, app, cenario):
        assert ExercicioService.reordenar_exercicios(424242, 'A', [], user_id=cenario.uid) is False

    def test_sem_usuario_retorna_false(self, app, cenario):
        c = cenario
        assert ExercicioService.reordenar_exercicios(c.versao, 'A', [f'u_{c.u1}'], user_id=None) is False


# ------------------------------------------------------------------
# Últimas séries (sugestão de carga/reps na tela de registrar treino)
# ------------------------------------------------------------------

@pytest.fixture
def historico(app):
    """Mesmo número de id nas duas tabelas (u=1 e b=1) para provar que `tipo`
    separa o histórico. Última sessão do usuário-1 tem 2 séries; a anterior, 3."""
    uid = _user('hist')
    u = _meu(uid, 'Meu exercício')
    b = _base('Do catálogo')
    assert u == b == 1
    v = _versao(uid)
    t = _treino(v)
    _registro(uid, v, t, [(10, 12), (10, 10), (10, 8)], usuario_id=u, dias_atras=7)   # sessão antiga (3 séries)
    _registro(uid, v, t, [(12, 10), (12, 8)], usuario_id=u, dias_atras=1)             # sessão recente (2 séries)
    _registro(uid, v, t, [(100, 5)], base_id=b, dias_atras=2)                         # outro exercício, mesmo id
    return SimpleNamespace(uid=uid, u=u, b=b, versao=v, treino=t)


class TestUltimaSessaoSeries:

    def test_retorna_todas_as_series_so_da_sessao_mais_recente(self, historico):
        h = historico
        r = ExercicioService.get_ultima_sessao_series(h.u, tipo='usuario', user_id=h.uid)

        assert r == [{'carga': 12.0, 'repeticoes': 10}, {'carga': 12.0, 'repeticoes': 8}]

    def test_tipo_separa_exercicios_com_o_mesmo_numero_de_id(self, historico):
        h = historico

        assert ExercicioService.get_ultima_sessao_series(h.b, tipo='base', user_id=h.uid) == \
            [{'carga': 100.0, 'repeticoes': 5}]
        assert ExercicioService.get_ultima_sessao_series(h.u, tipo='usuario', user_id=h.uid) != \
            ExercicioService.get_ultima_sessao_series(h.b, tipo='base', user_id=h.uid)

    def test_series_vem_ordenadas_pela_coluna_ordem(self, app):
        uid = _user('hist_ord')
        u = _meu(uid, 'X')
        v = _versao(uid)
        t = _treino(v)
        rid = _registro(uid, v, t, [(1, 1), (2, 2), (3, 3)], usuario_id=u)
        # embaralha a ordem gravada
        for s, ordem in zip(HistoricoTreino.query.filter_by(registro_id=rid).order_by(HistoricoTreino.id), (2, 0, 1)):
            s.ordem = ordem
        db.session.commit()

        r = ExercicioService.get_ultima_sessao_series(u, tipo='usuario', user_id=uid)

        assert [s['carga'] for s in r] == [2.0, 3.0, 1.0]

    def test_filtra_por_versao(self, historico):
        h = historico
        outra = _versao(h.uid, numero=2, inicio=date(2025, 1, 1))

        assert ExercicioService.get_ultima_sessao_series(h.u, tipo='usuario', versao_id=outra, user_id=h.uid) == []
        assert len(ExercicioService.get_ultima_sessao_series(
            h.u, tipo='usuario', versao_id=h.versao, user_id=h.uid)) == 2

    def test_historico_de_outro_usuario_nao_aparece(self, historico):
        outro = _user('hist_outro')
        assert ExercicioService.get_ultima_sessao_series(historico.u, tipo='usuario', user_id=outro) == []

    def test_sem_historico_ou_sem_usuario_retorna_vazio(self, historico):
        h = historico
        assert ExercicioService.get_ultima_sessao_series(999, tipo='usuario', user_id=h.uid) == []
        assert ExercicioService.get_ultima_sessao_series(h.u, tipo='usuario', user_id=None) == []

    def test_sem_tipo_usa_a_regra_antiga_de_compatibilidade(self, app):
        uid = _user('hist_compat')
        u = _meu(uid, 'Único')
        v = _versao(uid)
        t = _treino(v)
        _registro(uid, v, t, [(30, 6)], usuario_id=u)

        assert ExercicioService.get_ultima_sessao_series(u, user_id=uid) == [{'carga': 30.0, 'repeticoes': 6}]


class TestUltimasSeries:

    def test_mais_recentes_primeiro_respeitando_o_limite(self, historico):
        h = historico
        r = ExercicioService.get_ultimas_series(h.u, tipo='usuario', limite=2, user_id=h.uid)

        assert len(r) == 2
        assert all(s['carga'] == 12.0 for s in r)                # as 2 da sessão mais recente

    def test_limite_maior_que_a_sessao_puxa_series_da_sessao_anterior(self, historico):
        """Comportamento documentado: é uma JANELA de linhas, não uma sessão
        (por isso get_ultima_sessao_series existe)."""
        h = historico
        r = ExercicioService.get_ultimas_series(h.u, tipo='usuario', limite=3, user_id=h.uid)

        assert len(r) == 3
        assert r[-1]['carga'] == 10.0

    def test_tipo_base_nao_mistura_com_usuario(self, historico):
        h = historico
        assert ExercicioService.get_ultimas_series(h.b, tipo='base', user_id=h.uid) == \
            [{'carga': 100.0, 'repeticoes': 5}]

    def test_filtra_por_versao(self, historico):
        h = historico
        outra = _versao(h.uid, numero=2, inicio=date(2025, 1, 1))
        assert ExercicioService.get_ultimas_series(h.u, tipo='usuario', versao_id=outra, user_id=h.uid) == []

    def test_sem_tipo_usa_compatibilidade(self, app):
        uid = _user('us_compat')
        u = _meu(uid, 'Único')
        v = _versao(uid)
        t = _treino(v)
        _registro(uid, v, t, [(40, 4)], usuario_id=u)

        assert ExercicioService.get_ultimas_series(u, user_id=uid) == [{'carga': 40.0, 'repeticoes': 4}]

    def test_sem_usuario_retorna_vazio(self, historico):
        assert ExercicioService.get_ultimas_series(historico.u, tipo='usuario', user_id=None) == []


class TestUltimaSessaoEmLote:

    def _ex(self, id_, tipo):
        return SimpleNamespace(id=id_, tipo=tipo, prefixo='u_' if tipo == 'usuario' else 'b_')

    def test_resolve_varios_exercicios_numa_chamada_sem_colidir_ids(self, historico):
        h = historico
        r = ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(h.u, 'usuario'), self._ex(h.b, 'base')], versao_id=h.versao, user_id=h.uid)

        assert r == {
            'u_1': [{'carga': 12.0, 'repeticoes': 10}, {'carga': 12.0, 'repeticoes': 8}],
            'b_1': [{'carga': 100.0, 'repeticoes': 5}],
        }

    def test_so_a_sessao_mais_recente_de_cada_exercicio(self, historico):
        h = historico
        r = ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(h.u, 'usuario')], versao_id=None, user_id=h.uid)

        assert len(r['u_1']) == 2

    def test_lista_so_de_um_tipo(self, historico):
        h = historico
        assert list(ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(h.b, 'base')], versao_id=h.versao, user_id=h.uid)) == ['b_1']

    def test_exercicio_sem_historico_fica_fora_do_resultado(self, historico):
        h = historico
        r = ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(h.u, 'usuario'), self._ex(999, 'usuario')], versao_id=h.versao, user_id=h.uid)

        assert set(r) == {'u_1'}

    def test_registro_sem_series_fica_fora(self, app):
        uid = _user('lote_vazio')
        u = _meu(uid, 'Sem séries')
        v = _versao(uid)
        t = _treino(v)
        _registro(uid, v, t, [], usuario_id=u)

        assert ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(u, 'usuario')], versao_id=v, user_id=uid) == {}

    def test_filtra_por_versao(self, historico):
        h = historico
        outra = _versao(h.uid, numero=2, inicio=date(2025, 1, 1))
        assert ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(h.u, 'usuario')], versao_id=outra, user_id=h.uid) == {}

    def test_historico_de_outro_usuario_nao_vaza(self, historico):
        outro = _user('lote_outro')
        assert ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(historico.u, 'usuario')], versao_id=None, user_id=outro) == {}

    def test_lista_vazia_ou_sem_usuario_retorna_dict_vazio(self, historico):
        assert ExercicioService.get_ultima_sessao_series_em_lote([], versao_id=None, user_id=historico.uid) == {}
        assert ExercicioService.get_ultima_sessao_series_em_lote(
            [self._ex(historico.u, 'usuario')], versao_id=None, user_id=None) == {}

    def test_entrada_invalida_retorna_dict_vazio_em_vez_de_quebrar(self, historico):
        assert ExercicioService.get_ultima_sessao_series_em_lote(None, versao_id=None, user_id=historico.uid) == {}
