"""Testes para TreinoService"""

import pytest
from services.treino_service import TreinoService
from models import User

def test_criar_treino(app, db):
    """Testa criação de treino"""
    with app.app_context():
        # Criar usuário de teste
        user = User(username='teste', email='teste@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        
        # Testar criação
        treino = TreinoService.create('A', 'Treino A', 'Teste', user.id)
        assert treino is not None
        assert treino.codigo == 'A'
        assert treino.nome == 'Treino A'
        
        # Testar duplicata
        treino2 = TreinoService.create('A', 'Outro', 'Teste', user.id)
        assert treino2 is None

def test_buscar_treino(app, db):
    """Testa busca de treino"""
    with app.app_context():
        user = User(username='teste2', email='teste2@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        
        TreinoService.create('B', 'Treino B', 'Teste', user.id)
        
        treino = TreinoService.get_by_codigo('B', user.id)
        assert treino is not None
        assert treino.codigo == 'B'

def test_atualizar_treino(app, db):
    """Testa atualização de treino"""
    with app.app_context():
        user = User(username='teste3', email='teste3@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        
        treino = TreinoService.create('C', 'Treino C', 'Teste', user.id)
        
        atualizado = TreinoService.update(treino.id, nome='Treino C Atualizado', user_id=user.id)
        assert atualizado.nome == 'Treino C Atualizado'