from flask import Blueprint

aluno_bp = Blueprint('aluno', __name__, url_prefix='/aluno')

# Importar as rotas para registrá-las no blueprint
from . import main
from . import treino
from . import exercicio
from . import versao
from . import stats
