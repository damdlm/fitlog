"""Testes unitários para utils/version_utils.py

NOTA IMPORTANTE: a maior parte das funções deste módulo (get_versoes_globais,
get_versao_ativa, get_treinos_da_versao, get_exercicios_do_treino,
get_todos_exercicios_da_versao, adicionar_treino_na_versao,
verificar_versao_ativa, editar_treino_na_versao, remover_treino_da_versao,
adicionar_exercicio_ao_treino, remover_exercicio_do_treino,
reordenar_exercicios_do_treino, get_ultimas_series) importa de
``utils.db_utils``, um módulo que não existe neste repositório -- e
``migrar_versoes_para_novo_formato`` importa de ``utils.file_utils``, que
também não existe. Chamar qualquer uma dessas funções sempre lança
ImportError. A única função realmente usada pela aplicação (chamada em
routes/admin_routes.py) é ``verificar_exercicio_em_versoes``, que não
depende desses módulos ausentes e funciona normalmente. Este arquivo testa
o que de fato funciona e documenta o ImportError nas demais.
"""
from datetime import date

import pytest

from models import db, User, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioUsuario
from utils.version_utils import (
    verificar_exercicio_em_versoes,
    get_versoes_treino_antigo,
    get_versao_ativa_antiga,
    get_exercicios_por_versao_antiga,
    get_versoes_globais,
    get_versao_ativa,
    verificar_versao_ativa,
    adicionar_treino_na_versao,
    migrar_versoes_para_novo_formato,
)


def _criar_cenario_com_exercicio(username, tipo='usuario'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()

    v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                      data_inicio=date(2024, 1, 1), user_id=u.id)
    db.session.add(v)
    db.session.commit()

    tv = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='Treino A',
                       descricao_treino='desc')
    db.session.add(tv)
    db.session.commit()

    ex = ExercicioUsuario(usuario_id=u.id, nome='Supino')
    db.session.add(ex)
    db.session.commit()

    if tipo == 'usuario':
        ve = VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0)
    else:
        ve = VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=ex.id, ordem=0)
    db.session.add(ve)
    db.session.commit()

    return u, v, tv, ex


class TestVerificarExercicioEmVersoes:
    """A única função de version_utils.py realmente usada pela aplicação."""

    def test_encontra_exercicio_de_usuario(self, app):
        with app.app_context():
            u, v, tv, ex = _criar_cenario_com_exercicio('vu_verif_1', tipo='usuario')

            resultado = verificar_exercicio_em_versoes(ex.id, 'usuario')
            assert len(resultado) == 1
            assert resultado[0]['tipo'] == 'usuario'
            assert resultado[0]['versao_id'] == v.id
            assert resultado[0]['treino_id'] == 'A'

    def test_encontra_exercicio_com_tipo_none_busca_ambos(self, app):
        with app.app_context():
            u, v, tv, ex = _criar_cenario_com_exercicio('vu_verif_2', tipo='usuario')

            resultado = verificar_exercicio_em_versoes(ex.id, tipo_exercicio=None)
            assert len(resultado) == 1

    def test_vazio_para_exercicio_nao_usado(self, app):
        with app.app_context():
            resultado = verificar_exercicio_em_versoes(99999)
            assert resultado == []

    def test_nao_encontra_tipo_base_quando_e_usuario(self, app):
        with app.app_context():
            u, v, tv, ex = _criar_cenario_com_exercicio('vu_verif_3', tipo='usuario')

            resultado = verificar_exercicio_em_versoes(ex.id, 'base')
            assert resultado == []

    def test_inclui_datas_formatadas(self, app):
        with app.app_context():
            u, v, tv, ex = _criar_cenario_com_exercicio('vu_verif_4', tipo='usuario')

            resultado = verificar_exercicio_em_versoes(ex.id, 'usuario')
            assert resultado[0]['data_inicio'] == '2024-01-01'
            assert resultado[0]['data_fim'] is None


class TestFuncoesDeCompatibilidade:
    """Stubs mantidos por compatibilidade -- sempre retornam valores fixos."""

    def test_get_versoes_treino_antigo_retorna_vazio(self, app):
        with app.app_context():
            assert get_versoes_treino_antigo() == []
            assert get_versoes_treino_antigo(treino_id=1) == []

    def test_get_versao_ativa_antiga_retorna_none(self, app):
        with app.app_context():
            assert get_versao_ativa_antiga(1, 'Janeiro/2024') is None

    def test_get_exercicios_por_versao_antiga_retorna_vazio(self, app):
        with app.app_context():
            assert get_exercicios_por_versao_antiga(1) == []


class TestFuncoesQuebradasPorDependenciaAusente:
    """
    Documentam que estas funções lançam ImportError hoje, por dependerem
    de utils.db_utils / utils.file_utils, módulos ausentes do repositório.
    """

    def test_get_versoes_globais_lanca_importerror(self, app):
        with app.app_context():
            with pytest.raises(ImportError):
                get_versoes_globais()

    def test_get_versao_ativa_lanca_importerror(self, app):
        with app.app_context():
            with pytest.raises(ImportError):
                get_versao_ativa('Janeiro/2024')

    def test_verificar_versao_ativa_lanca_importerror(self, app):
        with app.app_context():
            with pytest.raises(ImportError):
                verificar_versao_ativa()

    def test_adicionar_treino_na_versao_lanca_importerror(self, app):
        with app.app_context():
            with pytest.raises(ImportError):
                adicionar_treino_na_versao(1, 'A', 'Treino A', 'desc', [])

    def test_migrar_versoes_lanca_importerror(self, app):
        with app.app_context():
            with pytest.raises(ImportError):
                migrar_versoes_para_novo_formato()
