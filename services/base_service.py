"""Classe base para todos os serviços com suporte a acesso de professores"""

from flask_login import current_user
from models import db, User, AlunoProfessor
import logging
import time
from functools import wraps

from extensions import cache as flask_cache

logger = logging.getLogger(__name__)


class CacheService:
    """Wrapper sobre Flask-Caching — funciona com Redis (prod) ou SimpleCache (dev)."""

    @classmethod
    def get(cls, key: str):
        return flask_cache.get(key)

    @classmethod
    def set(cls, key: str, value, ttl_seconds: int = 300):
        flask_cache.set(key, value, timeout=ttl_seconds)

    @classmethod
    def invalidate(cls, key: str):
        flask_cache.delete(key)

    @classmethod
    def invalidate_pattern(cls, pattern: str):
        try:
            flask_cache.delete_many(*[
                k for k in (flask_cache.cache._cache.keys()
                             if hasattr(flask_cache, 'cache') else [])
                if pattern in str(k)
            ])
        except Exception:
            pass


def cached(ttl_seconds: int = 300, key_prefix: str = ''):
    """Decorator de cache — delega ao Flask-Caching."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            key = f"{key_prefix}_{f.__name__}_{args}_{kwargs}"
            result = flask_cache.get(key)
            if result is None:
                result = f(*args, **kwargs)
                flask_cache.set(key, result, timeout=ttl_seconds)
            return result
        return decorated_function
    return decorator


class BaseService:
    """Classe base para todos os serviços"""
    
    @staticmethod
    def get_current_user():
        """Retorna o usuário atual"""
        return current_user if current_user and current_user.is_authenticated else None
    
    @staticmethod
    def get_current_user_id():
        """Retorna ID do usuário atual"""
        user = BaseService.get_current_user()
        return user.id if user else None
    
    @staticmethod
    def get_target_user_id(target_user_id=None):
        """
        Retorna o ID do usuário alvo considerando permissões do professor
        
        Se target_user_id for fornecido e o usuário atual for professor,
        verifica se pode acessar dados do aluno.
        Caso contrário, retorna o ID do usuário atual.
        
        Args:
            target_user_id: ID do usuário alvo (opcional)
        
        Returns:
            int: ID do usuário que deve ser usado na consulta
        """
        current_user = BaseService.get_current_user()
        if not current_user:
            return None
        
        # Se não especificou alvo, retorna próprio ID
        if not target_user_id:
            return current_user.id
        
        # Admin pode acessar qualquer usuário
        if current_user.is_admin:
            return target_user_id
        
        # Professor pode acessar dados de seus alunos
        if current_user.is_professor():
            # Verifica se o alvo é aluno deste professor
            assoc = AlunoProfessor.query.filter_by(
                aluno_id=target_user_id,
                professor_id=current_user.id,
                ativo=True
            ).first()
            if assoc:
                return target_user_id
            logger.warning(f"Professor {current_user.id} tentou acessar dados do aluno {target_user_id} sem permissão")
            return current_user.id
        
        # Aluno só pode acessar próprios dados
        return current_user.id
    
    @staticmethod
    def filter_by_user(query, target_user_id=None):
        """
        Aplica filtro de usuário à query considerando permissões
        
        Args:
            query: Query SQLAlchemy
            target_user_id: ID do usuário alvo (opcional)
        
        Returns:
            Query filtrada
        """
        user_id = BaseService.get_target_user_id(target_user_id)
        if user_id:
            return query.filter_by(user_id=user_id)
        return query
    
    @staticmethod
    def handle_error(e, message="Erro na operação"):
        """Tratamento padronizado de erros"""
        logger.error(f"{message}: {str(e)}", exc_info=True)
        db.session.rollback()
        return None
    
    @staticmethod
    def get_alunos_do_professor(professor_id=None):
        """
        Retorna lista de alunos de um professor
        
        Args:
            professor_id: ID do professor (usa atual se None)
        
        Returns:
            list: Lista de objetos User (alunos)
        """
        if not professor_id:
            professor = BaseService.get_current_user()
            if not professor or not professor.is_professor():
                return []
            professor_id = professor.id
        
        return (User.query
                .join(AlunoProfessor, AlunoProfessor.aluno_id == User.id)
                .filter(
                    AlunoProfessor.professor_id == professor_id,
                    AlunoProfessor.ativo == True,
                    User.ativo == True,
                )
                .order_by(User.nome_completo)
                .all())
    
    @staticmethod
    def get_professor_do_aluno(aluno_id=None):
        """
        Retorna o professor de um aluno
        
        Args:
            aluno_id: ID do aluno (usa atual se None)
        
        Returns:
            User: Objeto professor ou None
        """
        if not aluno_id:
            aluno = BaseService.get_current_user()
            if not aluno or not aluno.is_aluno():
                return None
            aluno_id = aluno.id
        
        return (User.query
                .join(AlunoProfessor, AlunoProfessor.professor_id == User.id)
                .filter(
                    AlunoProfessor.aluno_id == aluno_id,
                    AlunoProfessor.ativo == True,
                )
                .first())