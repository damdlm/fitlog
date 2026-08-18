import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app import create_app
from models import db as _db
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Habilita a checagem/aplicação de FOREIGN KEY no SQLite dos testes.

    O SQLite não aplica `ondelete='CASCADE'` (nem qualquer outra
    constraint de FK) a menos que `PRAGMA foreign_keys=ON` seja
    executado por conexão -- diferente do Postgres (produção), onde o
    cascade é sempre aplicado no nível do banco. Sem isso, um
    `Query.delete()` em massa não apaga as linhas filhas (ex.:
    historico_treino ao deletar registro_treino), e como o SQLite
    reaproveita o menor ID livre, um INSERT seguinte pode reaproveitar
    o ID do registro apagado e "herdar" as linhas órfãs antigas --
    mascarando bugs e fazendo os testes divergirem do comportamento
    real de produção.
    """
    if dbapi_connection.__class__.__module__.startswith('sqlite3'):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db(app):
    return _db

@pytest.fixture
def auth_client(client):
    """Cliente com usuário logado"""
    from models import User
    
    with client.application.app_context():
        user = User(username='teste', email='teste@teste.com', is_admin=True)
        user.set_password('123456')
        _db.session.add(user)
        _db.session.commit()
        
        client.post('/auth/login', data={
            'username': 'teste',
            'password': '123456'
        })
    
    return client