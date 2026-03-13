from flask import Blueprint, render_template
from services.treino_service import TreinoService
from services.registro_service import RegistroService

main_bp = Blueprint('main', __name__)

@main_bp.route("/")
def index():
    """Página inicial"""
    treinos = TreinoService.get_all()
    registros = RegistroService.get_all()
    
    total_registros = len(registros)
    semanas_treinadas = len(set((r.periodo, r.semana) for r in registros))
    
    ultima_semana = "N/A"
    if registros:
        ultimo = registros[-1]
        ultima_semana = f"{ultimo.periodo} - Semana {ultimo.semana}"
    
    return render_template("index.html",
                         treinos=treinos,
                         total_registros=total_registros,
                         semanas_treinadas=semanas_treinadas,
                         ultima_semana=ultima_semana)