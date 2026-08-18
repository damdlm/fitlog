"""Testes unitários para repositories/versao_repository.py"""
from datetime import date

from models import db, User, VersaoGlobal
from repositories.versao_repository import VersaoRepository
from repositories.treino_repository import TreinoRepository


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno')
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _criar_treino(user_id, codigo='A'):
    return TreinoRepository().create(codigo=codigo, nome=f'Treino {codigo}',
                                      descricao='d', user_id=user_id)


class TestGetAtiva:
    def test_retorna_versao_sem_data_fim(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_ativa_1')
            repo = VersaoRepository()
            repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                        data_inicio=date(2024, 1, 1), user_id=u.id)

            ativa = repo.get_ativa(user_id=u.id)
            assert ativa is not None
            assert ativa.data_fim is None

    def test_none_se_todas_finalizadas(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_ativa_2')
            repo = VersaoRepository()
            repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                        data_inicio=date(2024, 1, 1), data_fim=date(2024, 2, 1),
                        user_id=u.id)

            assert repo.get_ativa(user_id=u.id) is None

    def test_none_sem_versoes(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_ativa_3')
            repo = VersaoRepository()
            assert repo.get_ativa(user_id=u.id) is None


class TestGetWithTreinos:
    def test_retorna_versao_com_relacionamento(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_treinos_1')
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)

            encontrada = repo.get_with_treinos(v.id, user_id=u.id)
            assert encontrada is not None
            assert encontrada.id == v.id

    def test_none_se_nao_encontrada(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_treinos_2')
            repo = VersaoRepository()
            assert repo.get_with_treinos(99999, user_id=u.id) is None


class TestGetProximoNumero:
    def test_primeiro_numero_e_1(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_proximo_1')
            repo = VersaoRepository()
            assert repo.get_proximo_numero(user_id=u.id) == 1

    def test_incrementa_a_partir_da_maior_existente(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_proximo_2')
            repo = VersaoRepository()
            repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                        data_inicio=date(2024, 1, 1), user_id=u.id)
            repo.create(numero_versao=5, descricao='v5', divisao='ABC',
                        data_inicio=date(2024, 2, 1), user_id=u.id)

            assert repo.get_proximo_numero(user_id=u.id) == 6

    def test_isolado_por_usuario(self, app):
        with app.app_context():
            a = _criar_usuario('vrepo_proximo_a')
            b = _criar_usuario('vrepo_proximo_b')
            repo = VersaoRepository()
            repo.create(numero_versao=10, descricao='v10', divisao='ABC',
                        data_inicio=date(2024, 1, 1), user_id=a.id)

            assert repo.get_proximo_numero(user_id=b.id) == 1


class TestAdicionarTreino:
    def test_com_lista_vazia_de_exercicios_funciona(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_add_1')
            t = _criar_treino(u.id)
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)

            resultado = repo.adicionar_treino(v.id, t.id, 'Treino A', 'desc', [],
                                               user_id=u.id)
            assert resultado is True

    def test_com_exercicios_falha_bug_conhecido(self, app):
        """
        NOTA (bug conhecido): VersaoExercicio.exercicio_id é uma @property
        somente-leitura (sem setter) -- ela deriva de exercicio_usuario_id/
        exercicio_base_id. adicionar_treino() tenta instanciar
        VersaoExercicio(exercicio_id=...), o que sempre lança
        AttributeError e é engolido pelo try/except, retornando False
        sempre que exercicios_ids não está vazio. Este teste documenta o
        comportamento atual (a versão em si não fica órfã: o treino/versão
        criados antes do erro permanecem, mas nenhum exercício é
        associado).
        """
        with app.app_context():
            u = _criar_usuario('vrepo_add_2')
            t = _criar_treino(u.id)
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)

            resultado = repo.adicionar_treino(v.id, t.id, 'Treino A', 'desc', [1, 2],
                                               user_id=u.id)
            assert resultado is False

    def test_nao_duplica_treino_na_mesma_versao(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_add_3')
            t = _criar_treino(u.id)
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)

            repo.adicionar_treino(v.id, t.id, 'Treino A', 'desc', [], user_id=u.id)
            resultado = repo.adicionar_treino(v.id, t.id, 'Treino A de novo', 'desc',
                                               [], user_id=u.id)
            assert resultado is False


class TestRemoverTreino:
    def test_remove_com_sucesso(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_rem_1')
            t = _criar_treino(u.id)
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)
            repo.adicionar_treino(v.id, t.id, 'Treino A', 'desc', [], user_id=u.id)

            assert repo.remover_treino(v.id, t.id, user_id=u.id) is True

    def test_retorna_false_se_nao_existe_na_versao(self, app):
        with app.app_context():
            u = _criar_usuario('vrepo_rem_2')
            t = _criar_treino(u.id)
            repo = VersaoRepository()
            v = repo.create(numero_versao=1, descricao='v1', divisao='ABC',
                            data_inicio=date(2024, 1, 1), user_id=u.id)

            assert repo.remover_treino(v.id, t.id, user_id=u.id) is False
