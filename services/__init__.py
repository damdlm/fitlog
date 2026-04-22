"""Camada de serviços da aplicação"""

# Primeiro, importar a base (não depende de outros serviços)
from .base_service import BaseService, CacheService, cached

# Agora importar os serviços que dependem de BaseService
from .treino_service import TreinoService
from .exercicio_service import ExercicioService
from .musculo_service import MusculoService
from .versao_service import VersaoService
from .registro_service import RegistroService
from .estatistica_service import EstatisticaService
from .aluno_service import AlunoService
from .professor_service import ProfessorService

# Opcional: também expor a base
__all__ = [
    'BaseService',
    'CacheService',
    'cached',
    'TreinoService',
    'ExercicioService',
    'MusculoService',
    'VersaoService',
    'RegistroService',
    'EstatisticaService',
    'AlunoService',
    'ProfessorService',
]