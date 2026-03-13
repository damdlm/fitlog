"""Schemas para serialização de dados"""

from .treino_schema import TreinoSchema, TreinoSimplificadoSchema
from .exercicio_schema import ExercicioSchema, ExercicioSimplificadoSchema
from .versao_schema import VersaoSchema, VersaoSimplificadoSchema

__all__ = [
    'TreinoSchema', 'TreinoSimplificadoSchema',
    'ExercicioSchema', 'ExercicioSimplificadoSchema',
    'VersaoSchema', 'VersaoSimplificadoSchema'
]