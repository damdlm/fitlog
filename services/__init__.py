"""Camada de serviços da aplicação"""

from flask_login import current_user
from models import db
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

class CacheService:
    """Serviço simples de cache em memória"""
    
    _cache = {}
    _ttl = {}
    
    @classmethod
    def get(cls, key):
        """Retorna valor do cache se ainda válido"""
        if key in cls._cache:
            if time.time() < cls._ttl.get(key, 0):
                return cls._cache[key]
            else:
                cls.invalidate(key)
        return None
    
    @classmethod
    def set(cls, key, value, ttl_seconds=300):
        """Armazena valor no cache com TTL"""
        cls._cache[key] = value
        cls._ttl[key] = time.time() + ttl_seconds
    
    @classmethod
    def invalidate(cls, key):
        """Remove item do cache"""
        cls._cache.pop(key, None)
        cls._ttl.pop(key, None)
    
    @classmethod
    def invalidate_pattern(cls, pattern):
        """Remove todos os itens que correspondem ao padrão"""
        keys_to_remove = [k for k in cls._cache.keys() if pattern in k]
        for key in keys_to_remove:
            cls.invalidate(key)

def cached(ttl_seconds=300, key_prefix=''):
    """Decorator para cache de funções"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Criar chave única baseada na função e argumentos
            key = f"{key_prefix}_{f.__name__}_{str(args)}_{str(kwargs)}"
            
            # Tentar obter do cache
            cached_result = CacheService.get(key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_result
            
            # Executar função e armazenar resultado
            logger.debug(f"Cache miss: {key}")
            result = f(*args, **kwargs)
            CacheService.set(key, result, ttl_seconds)
            return result
        return decorated_function
    return decorator

class BaseService:
    """Classe base para todos os serviços"""
    
    @staticmethod
    def get_current_user_id():
        """Retorna ID do usuário atual"""
        return current_user.id if current_user and current_user.is_authenticated else None
    
    @staticmethod
    def filter_by_user(query, user_id=None):
        """Aplica filtro de usuário à query"""
        if user_id is None:
            user_id = BaseService.get_current_user_id()
        if user_id:
            return query.filter_by(user_id=user_id)
        return query
    
    @staticmethod
    def handle_error(e, message="Erro na operação"):
        """Tratamento padronizado de erros"""
        logger.error(f"{message}: {str(e)}", exc_info=True)
        db.session.rollback()
        return None

# Importar serviços para facilitar acesso
from .treino_service import TreinoService
from .exercicio_service import ExercicioService
from .musculo_service import MusculoService
from .versao_service import VersaoService
from .registro_service import RegistroService
from .estatistica_service import EstatisticaService

__all__ = [
    'BaseService',
    'TreinoService',
    'ExercicioService',
    'MusculoService',
    'VersaoService',
    'RegistroService',
    'EstatisticaService',
    'CacheService',
    'cached'
]