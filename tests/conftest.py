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
        _seed_telas_controladas()
        yield app
        _db.session.remove()
        _db.drop_all()


def _seed_telas_controladas():
    """Espelha o seed da migration a1b2c3d4e5f6 -- os testes precisam
    ver o mesmo estado inicial que a aplicação real tem em produção
    (db.create_all() não roda migrations, só cria o schema vazio)."""
    from models import TelaControlada
    _db.session.bulk_save_objects([
        TelaControlada(chave='estatisticas', nome_exibicao='Estatísticas', bloqueia_sem_plano=True),
        TelaControlada(chave='tabela_progresso', nome_exibicao='Tabela de Progresso', bloqueia_sem_plano=True),
        TelaControlada(chave='fitbot', nome_exibicao='FitBot', bloqueia_sem_plano=True),
        TelaControlada(chave='calendario', nome_exibicao='Calendário', bloqueia_sem_plano=False),
        TelaControlada(chave='ranking', nome_exibicao='Ranking', bloqueia_sem_plano=False),
        TelaControlada(chave='dashboard', nome_exibicao='Dashboard', bloqueia_sem_plano=False),
    ])
    _db.session.commit()

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