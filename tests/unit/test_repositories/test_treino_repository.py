"""Testes unitários para repositories/treino_repository.py"""
from models import db, User, Treino
from repositories.treino_repository import TreinoRepository


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno')
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


class TestGetByCodigo:
    def test_encontra_por_codigo_maiusculo(self, app):
        with app.app_context():
            u = _criar_usuario('trepo_codigo_1')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)

            encontrado = repo.get_by_codigo('A', user_id=u.id)
            assert encontrado is not None
            assert encontrado.codigo == 'A'

    def test_normaliza_para_maiusculo(self, app):
        with app.app_context():
            u = _criar_usuario('trepo_codigo_2')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)

            encontrado = repo.get_by_codigo('a', user_id=u.id)
            assert encontrado is not None

    def test_retorna_none_se_nao_existe(self, app):
        with app.app_context():
            u = _criar_usuario('trepo_codigo_3')
            repo = TreinoRepository()
            assert repo.get_by_codigo('Z', user_id=u.id) is None


class TestGetWithExercicios:
    def test_retorna_none_bug_conhecido(self, app):
        """
        NOTA (bug conhecido): get_with_exercicios tenta fazer
        joinedload(Treino.exercicios), mas o modelo Treino não tem um
        relacionamento chamado 'exercicios' (só 'versoes' e 'registros').
        O AttributeError é capturado pelo try/except do método, que
        sempre retorna None. Este teste documenta o comportamento atual.
        """
        with app.app_context():
            u = _criar_usuario('trepo_relac_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)

            encontrado = repo.get_with_exercicios(criado.id, user_id=u.id)
            assert encontrado is None

    def test_retorna_none_se_nao_encontrado(self, app):
        with app.app_context():
            u = _criar_usuario('trepo_relac_2')
            repo = TreinoRepository()
            assert repo.get_with_exercicios(99999, user_id=u.id) is None


class TestGetAllWithCounts:
    def test_retorna_lista_vazia(self, app):
        """
        NOTA: get_all_with_counts referencia um modelo `Exercicio` que não
        existe mais em models.py (foi substituído por ExercicioUsuario/
        ExercicioSistema num refactor anterior). O método está com um bug
        de import que é silenciosamente engolido pelo try/except e sempre
        retorna [] hoje -- este teste documenta o comportamento atual.
        """
        with app.app_context():
            u = _criar_usuario('trepo_counts_1')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)

            resultado = repo.get_all_with_counts(user_id=u.id)
            assert resultado == []
