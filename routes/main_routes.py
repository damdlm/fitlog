from flask import Blueprint, render_template
from flask_login import login_required
from services.treino_service import TreinoService

main_bp = Blueprint('main', __name__)

@main_bp.route("/")
@login_required
def index():
    """Página inicial"""
    treinos = TreinoService.get_all()

    return render_template("index.html", treinos=treinos)