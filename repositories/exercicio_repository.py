"""Repositório para operações com exercícios"""

from models import Exercicio, HistoricoTreino, RegistroTreino
from sqlalchemy.orm import joinedload
from .base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)

class ExercicioRepository(BaseRepository):
    """Repositório para gerenciar exercícios"""
    
    def __init__(self):
        super().__init__(Exercicio)
    
    def get_by_treino(self, treino_id, user_id=None):
        """Retorna exercícios de um treino"""
        try:
            query = self.model_class.query.filter_by(treino_id=treino_id)
            query = self.filter_by_user(query, user_id)
            return query.all()
        except Exception as e:
            logger.error(f"Erro ao buscar exercícios do treino {treino_id}: {e}")
            return []
    
    def get_with_relations(self, exercicio_id, user_id=None):
        """Retorna exercício com músculo e treino"""
        try:
            query = self.model_class.query.options(
                joinedload(Exercicio.musculo_ref),
                joinedload(Exercicio.treino_ref)
            ).filter_by(id=exercicio_id)
            query = self.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            logger.error(f"Erro ao buscar exercício com relações {exercicio_id}: {e}")
            return None
    
    def get_ultima_carga(self, exercicio_id, user_id=None):
        """Retorna última carga do exercício"""
        try:
            from models import RegistroTreino
            
            query = RegistroTreino.query.filter_by(exercicio_id=exercicio_id)
            query = self.filter_by_user(query, user_id)
            registro = query.order_by(RegistroTreino.data_registro.desc()).first()
            
            if registro and registro.series:
                primeira_serie = registro.series[0]
                return float(primeira_serie.carga)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar última carga {exercicio_id}: {e}")
            return None
    
    def get_ultimas_series(self, exercicio_id, versao_id=None, limite=1, user_id=None):
        """Retorna últimas séries do exercício"""
        try:
            query = HistoricoTreino.query\
                .join(RegistroTreino)\
                .filter(RegistroTreino.exercicio_id == exercicio_id)
            
            query = self.filter_by_user(query, user_id)
            
            if versao_id:
                query = query.filter(RegistroTreino.versao_id == versao_id)
            
            series = query.order_by(RegistroTreino.data_registro.desc())\
                .limit(limite).all()
            
            resultado = []
            for serie in series:
                resultado.append({
                    'carga': float(serie.carga),
                    'repeticoes': serie.repeticoes
                })
            
            return resultado
        except Exception as e:
            logger.error(f"Erro ao buscar últimas séries {exercicio_id}: {e}")
            return []
    
    def search_by_nome(self, termo, user_id=None, limite=50):
        """Busca exercícios por nome"""
        try:
            query = self.model_class.query.filter(
                Exercicio.nome.ilike(f'%{termo}%')
            )
            query = self.filter_by_user(query, user_id)
            return query.limit(limite).all()
        except Exception as e:
            logger.error(f"Erro ao buscar exercícios por nome {termo}: {e}")
            return []