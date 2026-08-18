"""Testes unitários para repositories/base_repository.py, exercitado
através de TreinoRepository (subclasse concreta simples)."""
from flask_login import login_user

from models import db, User, Treino
from repositories.treino_repository import TreinoRepository


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno')
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


class TestGetAll:
    def test_retorna_vazio_sem_registros(self, app):
        with app.app_context():
            u = _criar_usuario('base_getall_1')
            repo = TreinoRepository()
            assert repo.get_all(user_id=u.id) == []

    def test_retorna_registros_do_usuario(self, app):
        with app.app_context():
            u = _criar_usuario('base_getall_2')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)
            repo.create(codigo='B', nome='Treino B', descricao='d', user_id=u.id)

            resultado = repo.get_all(user_id=u.id)
            assert len(resultado) == 2

    def test_nao_retorna_registros_de_outro_usuario(self, app):
        with app.app_context():
            a = _criar_usuario('base_getall_a')
            b = _criar_usuario('base_getall_b')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='Treino de A', descricao='d', user_id=a.id)

            assert repo.get_all(user_id=b.id) == []

    def test_order_by(self, app):
        with app.app_context():
            u = _criar_usuario('base_getall_order')
            repo = TreinoRepository()
            repo.create(codigo='B', nome='B', descricao='d', user_id=u.id)
            repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)

            resultado = repo.get_all(user_id=u.id, order_by=Treino.codigo)
            assert [t.codigo for t in resultado] == ['A', 'B']

    def test_usa_current_user_quando_user_id_nao_informado(self, app):
        with app.app_context():
            u = _criar_usuario('base_getall_current')
            u_id = u.id
            repo = TreinoRepository()
            repo.create(codigo='A', nome='A', descricao='d', user_id=u_id)

        with app.test_request_context():
            login_user(db.session.get(User, u_id))
            resultado = TreinoRepository().get_all()
            assert len(resultado) == 1


class TestGetById:
    def test_encontra_registro(self, app):
        with app.app_context():
            u = _criar_usuario('base_getbyid_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)

            encontrado = repo.get_by_id(criado.id, user_id=u.id)
            assert encontrado is not None
            assert encontrado.id == criado.id

    def test_retorna_none_se_nao_existe(self, app):
        with app.app_context():
            u = _criar_usuario('base_getbyid_2')
            repo = TreinoRepository()
            assert repo.get_by_id(99999, user_id=u.id) is None

    def test_isolamento_entre_usuarios(self, app):
        with app.app_context():
            a = _criar_usuario('base_getbyid_a')
            b = _criar_usuario('base_getbyid_b')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=a.id)

            assert repo.get_by_id(criado.id, user_id=b.id) is None


class TestCreate:
    def test_cria_com_sucesso(self, app):
        with app.app_context():
            u = _criar_usuario('base_create_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='Treino A', descricao='d', user_id=u.id)

            assert criado is not None
            assert criado.id is not None
            assert criado.codigo == 'A'

    def test_falha_retorna_none_e_faz_rollback(self, app):
        with app.app_context():
            u = _criar_usuario('base_create_2')
            repo = TreinoRepository()
            # codigo é nullable=False -- omitir deve estourar erro no commit
            resultado = repo.create(nome='Sem codigo', descricao='d', user_id=u.id)
            assert resultado is None

    def test_preenche_user_id_do_current_user_quando_omitido(self, app):
        with app.app_context():
            u = _criar_usuario('base_create_current')
            u_id = u.id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))
            criado = TreinoRepository().create(codigo='A', nome='A', descricao='d')
            assert criado is not None
            assert criado.user_id == u_id


class TestUpdate:
    def test_atualiza_campos(self, app):
        with app.app_context():
            u = _criar_usuario('base_update_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='Original', descricao='d', user_id=u.id)

            atualizado = repo.update(criado, nome='Atualizado')
            assert atualizado.nome == 'Atualizado'

    def test_ignora_atributos_inexistentes(self, app):
        with app.app_context():
            u = _criar_usuario('base_update_2')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)

            resultado = repo.update(criado, campo_que_nao_existe='x')
            assert resultado is not None


class TestDelete:
    def test_remove_registro(self, app):
        with app.app_context():
            u = _criar_usuario('base_delete_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)
            criado_id = criado.id

            resultado = repo.delete(criado)
            assert resultado is True
            assert repo.get_by_id(criado_id, user_id=u.id) is None


class TestDeleteById:
    def test_remove_com_sucesso(self, app):
        with app.app_context():
            u = _criar_usuario('base_deletebyid_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)

            assert repo.delete_by_id(criado.id, user_id=u.id) is True

    def test_retorna_false_se_nao_encontrado(self, app):
        with app.app_context():
            u = _criar_usuario('base_deletebyid_2')
            repo = TreinoRepository()
            assert repo.delete_by_id(99999, user_id=u.id) is False


class TestCount:
    def test_conta_registros_do_usuario(self, app):
        with app.app_context():
            u = _criar_usuario('base_count_1')
            repo = TreinoRepository()
            repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)
            repo.create(codigo='B', nome='B', descricao='d', user_id=u.id)

            assert repo.count(user_id=u.id) == 2

    def test_zero_sem_registros(self, app):
        with app.app_context():
            u = _criar_usuario('base_count_2')
            repo = TreinoRepository()
            assert repo.count(user_id=u.id) == 0


class TestExists:
    def test_true_quando_existe(self, app):
        with app.app_context():
            u = _criar_usuario('base_exists_1')
            repo = TreinoRepository()
            criado = repo.create(codigo='A', nome='A', descricao='d', user_id=u.id)
            assert repo.exists(criado.id, user_id=u.id) is True

    def test_false_quando_nao_existe(self, app):
        with app.app_context():
            u = _criar_usuario('base_exists_2')
            repo = TreinoRepository()
            assert repo.exists(99999, user_id=u.id) is False


class TestBulkCreate:
    def test_cria_varios_registros(self, app):
        with app.app_context():
            u = _criar_usuario('base_bulk_1')
            repo = TreinoRepository()
            criados = repo.bulk_create([
                {'codigo': 'A', 'nome': 'A', 'descricao': 'd', 'user_id': u.id},
                {'codigo': 'B', 'nome': 'B', 'descricao': 'd', 'user_id': u.id},
            ])
            assert len(criados) == 2
            assert repo.count(user_id=u.id) == 2

    def test_falha_retorna_lista_vazia(self, app):
        with app.app_context():
            u = _criar_usuario('base_bulk_2')
            repo = TreinoRepository()
            # 'codigo' ausente -- nullable=False, deve falhar no commit
            criados = repo.bulk_create([
                {'nome': 'Sem codigo', 'descricao': 'd', 'user_id': u.id},
            ])
            assert criados == []


class TestGetOrCreate:
    def test_cria_quando_nao_existe(self, app):
        with app.app_context():
            u = _criar_usuario('base_getorcreate_1')
            repo = TreinoRepository()
            instancia, created = repo.get_or_create(
                codigo='A', user_id=u.id,
                defaults={'nome': 'A', 'descricao': 'd'}
            )
            assert created is True
            assert instancia is not None

    def test_retorna_existente_sem_criar(self, app):
        with app.app_context():
            u = _criar_usuario('base_getorcreate_2')
            repo = TreinoRepository()
            original = repo.create(codigo='A', nome='Original', descricao='d', user_id=u.id)

            instancia, created = repo.get_or_create(
                codigo='A', user_id=u.id,
                defaults={'nome': 'Outro nome'}
            )
            assert created is False
            assert instancia.id == original.id
            assert instancia.nome == 'Original'
