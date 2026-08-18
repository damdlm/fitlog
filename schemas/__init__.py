"""Schemas para serialização de dados"""

from .treino_schema import TreinoSchema, TreinoSimplificadoSchema
# NOTA: ExercicioSchema (exercicio_schema.py) não é importado aqui porque
# referencia um modelo `Exercicio` que não existe mais em models.py
# (substituído por ExercicioUsuario/ExercicioSistema). Ver nota equivalente
# em repositories/__init__.py.
from .versao_schema import VersaoSchema, VersaoSimplificadoSchema

__all__ = [
    'TreinoSchema', 'TreinoSimplificadoSchema',
    'VersaoSchema', 'VersaoSimplificadoSchema'
]