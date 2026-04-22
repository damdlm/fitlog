"""Repositório para operações com treinos"""

from models import Treino
from .base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)

class TreinoRepository(BaseRepository):
    """Repositório para gerenciar treinos"""
    
    def __init__(self):
        super().__init__(Treino)
    
    def get_by_codigo(self, codigo, user_id=None):
        """Retorna treino por código"""
        try:
            query = self.model_class.query.filter_by(codigo=codigo.upper())
            query = self.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            logger.error(f"Erro ao buscar treino por código {codigo}: {e}")
            return None
    
    def get_with_exercicios(self, treino_id, user_id=None):
        """Retorna treino com seus exercícios"""
        try:
            from sqlalchemy.orm import joinedload
            query = self.model_class.query.options(
                joinedload(Treino.exercicios)
            ).filter_by(id=treino_id)
            query = self.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            logger.error(f"Erro ao buscar treino com exercícios {treino_id}: {e}")
            return None
    
    def get_all_with_counts(self, user_id=None):
        """Retorna todos os treinos com contagem de exercícios"""
        try:
            from sqlalchemy import func
            from models import Exercicio
            
            query = db.session.query(
                Treino,
                func.count(Exercicio.id).label('qtd_exercicios')
            ).outerjoin(
                Exercicio, Exercicio.treino_id == Treino.id
            )
            
            query = self.filter_by_user(query, user_id)
            
            return query.group_by(Treino.id).order_by(Treino.codigo).all()
        except Exception as e:
            logger.error(f"Erro ao buscar treinos com contagens: {e}")
            return []