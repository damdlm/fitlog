"""Camada de repositórios para acesso a dados"""

from .base_repository import BaseRepository
from .treino_repository import TreinoRepository
from .exercicio_repository import ExercicioRepository
from .versao_repository import VersaoRepository
from .registro_repository import RegistroRepository

__all__ = [
    'BaseRepository',
    'TreinoRepository',
    'ExercicioRepository',
    'VersaoRepository',
    'RegistroRepository'
]