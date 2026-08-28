from flask import Blueprint

aluno_bp = Blueprint('aluno', __name__, url_prefix='/aluno')

# Importar as rotas para registrá-las no blueprint
from . import main
from . import exercicio
from . import cadastro_treinos
from . import stats
from . import ranking
