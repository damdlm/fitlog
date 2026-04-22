import pytest
from app import create_app
from models import db as _db
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

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