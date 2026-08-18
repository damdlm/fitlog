"""Camada de repositórios para acesso a dados"""

from .base_repository import BaseRepository
from .treino_repository import TreinoRepository
# NOTA: ExercicioRepository (exercicio_repository.py) não é importado aqui
# porque referencia um modelo `Exercicio` que não existe mais em models.py
# (substituído por ExercicioUsuario/ExercicioSistema num refactor anterior).
# O import quebrava todo o pacote `repositories`, que já não é usado em
# nenhum lugar da aplicação. Ver docs/CONTRIBUTING.md ou avaliar remover
# exercicio_repository.py, que está desatualizado em relação ao schema atual.
from .versao_repository import VersaoRepository
from .registro_repository import RegistroRepository

__all__ = [
    'BaseRepository',
    'TreinoRepository',
    'VersaoRepository',
    'RegistroRepository'
]