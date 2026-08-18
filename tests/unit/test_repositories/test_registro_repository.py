"""Testes unitários para repositories/registro_repository.py"""
from datetime import date, datetime

from models import db, User, Treino, VersaoGlobal, ExercicioUsuario, RegistroTreino, HistoricoTreino
from repositories.registro_repository import RegistroRepository


def _criar_cenario(username):
    """Cria usuário + treino + versão + exercício + 1 registro com 1 série,
    sem passar por salvar_sessao (que tem um bug conhecido -- ver
    TestSalvarSessao)."""
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()

    t = Treino(codigo='A', nome='A', descricao='d', user_id=u.id)
    db.session.add(t)
    db.session.commit()

    v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                      data_inicio=date(2024, 1, 1), user_id=u.id)
    db.session.add(v)
    db.session.commit()

    ex = ExercicioUsuario(usuario_id=u.id, nome='Supino')
    db.session.add(ex)
    db.session.commit()

    reg = RegistroTreino(treino_id=t.id, versao_id=v.id, periodo='Janeiro/2024',
                          semana=1, exercicio_usuario_id=ex.id,
                          data_registro=datetime.now(), user_id=u.id)
    db.session.add(reg)
    db.session.commit()

    serie = HistoricoTreino(registro_id=reg.id, carga=50, repeticoes=10, ordem=1)
    db.session.add(serie)
    db.session.commit()

    return u, t, v, ex, reg


class TestGetAllWithFilters:
    def test_retorna_registros_do_usuario(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_filters_1')
            repo = RegistroRepository()

            resultado = repo.get_all_with_filters(user_id=u.id)
            assert len(resultado) == 1
            assert resultado[0].id == reg.id

    def test_filtra_por_treino_id(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_filters_2')
            repo = RegistroRepository()

            resultado = repo.get_all_with_filters(filtros={'treino_id': t.id}, user_id=u.id)
            assert len(resultado) == 1

            resultado_vazio = repo.get_all_with_filters(filtros={'treino_id': 99999}, user_id=u.id)
            assert resultado_vazio == []

    def test_filtra_por_periodo(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_filters_3')
            repo = RegistroRepository()

            resultado = repo.get_all_with_filters(filtros={'periodo': 'Janeiro/2024'}, user_id=u.id)
            assert len(resultado) == 1

            resultado_vazio = repo.get_all_with_filters(filtros={'periodo': 'Fevereiro/2024'}, user_id=u.id)
            assert resultado_vazio == []

    def test_filtra_por_semana_e_versao(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_filters_4')
            repo = RegistroRepository()

            resultado = repo.get_all_with_filters(
                filtros={'semana': 1, 'versao_id': v.id}, user_id=u.id)
            assert len(resultado) == 1

    def test_isolamento_entre_usuarios(self, app):
        with app.app_context():
            u1, *_ = _criar_cenario('rrepo_filters_iso1')
            u2, *_ = _criar_cenario('rrepo_filters_iso2')
            repo = RegistroRepository()

            assert len(repo.get_all_with_filters(user_id=u1.id)) == 1
            assert len(repo.get_all_with_filters(user_id=u2.id)) == 1

    def test_carrega_series_com_load_series(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_filters_5')
            repo = RegistroRepository()

            resultado = repo.get_all_with_filters(user_id=u.id, load_series=True)
            assert len(resultado[0].series) == 1


class TestGetBySessao:
    def test_encontra_sessao(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_sessao_1')
            repo = RegistroRepository()

            resultado = repo.get_by_sessao(t.id, 'Janeiro/2024', 1, v.id, user_id=u.id)
            assert len(resultado) == 1

    def test_vazio_para_sessao_inexistente(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_sessao_2')
            repo = RegistroRepository()

            resultado = repo.get_by_sessao(t.id, 'Marco/2024', 1, v.id, user_id=u.id)
            assert resultado == []


class TestGetPeriodosDistintos:
    def test_retorna_periodos_unicos_do_usuario(self, app):
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_periodos_1')
            repo = RegistroRepository()

            resultado = repo.get_periodos_distintos(user_id=u.id)
            assert resultado == ['Janeiro/2024']

    def test_vazio_sem_registros(self, app):
        with app.app_context():
            u = User(username='rrepo_periodos_2', email='rp2@teste.com', tipo_usuario='aluno')
            u.set_password('123456')
            db.session.add(u)
            db.session.commit()

            repo = RegistroRepository()
            assert repo.get_periodos_distintos(user_id=u.id) == []


class TestGetAgregadoPorSemana:
    def test_retorna_lista_vazia_bug_conhecido(self, app):
        """
        NOTA (bug conhecido): a query usa .join(HistoricoTreino) e depois
        BaseRepository.filter_by_user chama query.filter_by(user_id=...).
        Como a query resultante do .join() não está mais associada a uma
        única entidade, o SQLAlchemy resolve 'user_id' contra a última
        entidade do FROM (historico_treino), que não possui essa coluna,
        e lança InvalidRequestError -- capturado pelo try/except do
        método, que sempre retorna []. Este teste documenta o
        comportamento atual.
        """
        with app.app_context():
            u, t, v, ex, reg = _criar_cenario('rrepo_agregado_1')
            repo = RegistroRepository()

            resultado = repo.get_agregado_por_semana(user_id=u.id)
            assert resultado == []


class TestSalvarSessao:
    def test_sem_user_id_retorna_false(self, app):
        with app.app_context():
            repo = RegistroRepository()
            resultado = repo.salvar_sessao(1, 1, 'Janeiro/2024', 1, {}, user_id=None)
            assert resultado is False

    def test_com_exercicios_falha_bug_conhecido(self, app):
        """
        NOTA (bug conhecido): assim como VersaoRepository.adicionar_treino,
        salvar_sessao tenta instanciar RegistroTreino(exercicio_id=ex_id, ...)
        -- mas exercicio_id é uma @hybrid_property somente-leitura em
        RegistroTreino (deriva de exercicio_usuario_id/exercicio_base_id).
        Isso sempre lança AttributeError, capturado pelo try/except, que
        faz rollback e retorna False. Este teste documenta o comportamento
        atual.
        """
        with app.app_context():
            u = User(username='rrepo_salvar_1', email='rs1@teste.com', tipo_usuario='aluno')
            u.set_password('123456')
            db.session.add(u)
            db.session.commit()

            t = Treino(codigo='A', nome='A', descricao='d', user_id=u.id)
            db.session.add(t)
            db.session.commit()

            v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), user_id=u.id)
            db.session.add(v)
            db.session.commit()

            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino')
            db.session.add(ex)
            db.session.commit()

            repo = RegistroRepository()
            dados = {ex.id: {'carga': 50, 'repeticoes': 10, 'num_series': 3}}
            resultado = repo.salvar_sessao(t.id, v.id, 'Janeiro/2024', 1, dados, user_id=u.id)
            assert resultado is False

    def test_sem_dados_de_exercicios_retorna_true(self, app):
        with app.app_context():
            u = User(username='rrepo_salvar_2', email='rs2@teste.com', tipo_usuario='aluno')
            u.set_password('123456')
            db.session.add(u)
            db.session.commit()

            t = Treino(codigo='A', nome='A', descricao='d', user_id=u.id)
            db.session.add(t)
            db.session.commit()

            v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), user_id=u.id)
            db.session.add(v)
            db.session.commit()

            repo = RegistroRepository()
            resultado = repo.salvar_sessao(t.id, v.id, 'Janeiro/2024', 1, {}, user_id=u.id)
            assert resultado is True
