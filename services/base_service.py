"""Classe base para todos os serviços com suporte a acesso de professores"""

from flask_login import current_user
from models import db, User, AlunoProfessor
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
        
        assocs = AlunoProfessor.query.filter_by(
            professor_id=professor_id,
            ativo=True
        ).all()
        
        alunos = []
        for assoc in assocs:
            aluno = User.query.get(assoc.aluno_id)
            if aluno and aluno.ativo:
                alunos.append(aluno)
        
        return alunos
    
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
        
        assoc = AlunoProfessor.query.filter_by(
            aluno_id=aluno_id,
            ativo=True
        ).first()
        
        if assoc:
            return User.query.get(assoc.professor_id)
        return None

# Importar serviços para facilitar acesso
from .treino_service import TreinoService
from .exercicio_service import ExercicioService
from .musculo_service import MusculoService
from .versao_service import VersaoService
from .registro_service import RegistroService
from .estatistica_service import EstatisticaService
from .aluno_service import AlunoService
from .professor_service import ProfessorService

__all__ = [
    'BaseService',
    'TreinoService',
    'ExercicioService',
    'MusculoService',
    'VersaoService',
    'RegistroService',
    'EstatisticaService',
    'AlunoService',
    'ProfessorService',
    'CacheService',
    'cached'
]