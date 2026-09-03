"""Testes unitários para utils/version_utils.py

O módulo hoje só mantém o que a aplicação realmente usa:
``verificar_exercicio_em_versoes`` (chamada em routes/admin_routes.py) e os
3 stubs de compatibilidade que sempre retornaram valores fixos. As demais
funções que existiam aqui dependiam de ``utils.db_utils``/``utils.file_utils``
-- módulos que não existem neste repositório -- e por isso sempre lançaram
ImportError em qualquer chamada real; foram removidas (ver
routes/admin_routes.py e o restante do código-fonte: nenhum outro ponto as
importava).
"""
from datetime import date

from models import db, User, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioUsuario
from utils.version_utils import (
    verificar_exercicio_em_versoes,
    get_versoes_treino_antigo,
    get_versao_ativa_antiga,
    get_exercicios_por_versao_antiga,
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
