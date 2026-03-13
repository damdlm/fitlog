from flask import Blueprint, render_template, request
from flask_login import login_required
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
import logging

stats_bp = Blueprint('stats', __name__)
logger = logging.getLogger(__name__)

@stats_bp.route("/estatisticas")
@login_required
def estatisticas():
    """Página de estatísticas"""
    registros = RegistroService.get_all(load_series=True)
    exercicios = ExercicioService.get_exercicios_completos()
    treinos = TreinoService.get_all()
    
    musculos_obj = MusculoService.get_all()
    musculos = [m.nome_exibicao for m in musculos_obj]
    
    musculo_stats = EstatisticaService.calcular_por_musculo()
    treino_stats = EstatisticaService.calcular_por_treino()
    
    return render_template("stats/estatisticas.html",
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats,
                         treinos=treinos,
                         musculos=musculos)

@stats_bp.route("/visualizar/tabela")
@login_required
def visualizar_tabela():
    """Tabela de progresso"""
    treino_selecionado = request.args.get("treino", "")
    musculo_selecionado = request.args.get("musculo", "")
    ordenar = request.args.get("ordenar", "exercicio")
    semanas_filtro = request.args.get("semanas", "todas")
    
    registros = RegistroService.get_all(load_series=True)
    exercicios = ExercicioService.get_exercicios_completos()
    treinos = TreinoService.get_all()
    musculos_obj = MusculoService.get_all()
    musculos = [m.nome_exibicao for m in musculos_obj]
    
    # Filtrar exercícios
    exercicios_filtrados = []
    for ex in exercicios:
        if treino_selecionado and ex.treino_id != treino_selecionado:
            continue
        if musculo_selecionado:
            if not ex.musculo_ref or ex.musculo_ref.nome_exibicao != musculo_selecionado:
                continue
        exercicios_filtrados.append(ex)
    
    # Ordenar
    if ordenar == "musculo":
        exercicios_filtrados.sort(key=lambda x: (x.musculo_ref.nome_exibicao if x.musculo_ref else "", x.nome))
    else:
        exercicios_filtrados.sort(key=lambda x: (x.treino_id or "", x.nome))
    
    # Organizar dados para a tabela
    dados_tabela = EstatisticaService.preparar_dados_tabela(
        exercicios_filtrados, registros, semanas_filtro, request.args
    )
    
    return render_template("stats/visualizar_tabela.html",
                         treinos=treinos,
                         treino_selecionado=treino_selecionado,
                         musculos=musculos,
                         musculo_selecionado=musculo_selecionado,
                         ordenar=ordenar,
                         exercicios=exercicios_filtrados,
                         semanas=dados_tabela['semanas'],
                         registros_por_exercicio=dados_tabela['registros_por_exercicio'],
                         semanas_selecionadas=semanas_filtro,
                         semanas_selecionadas_lista=dados_tabela['semanas_selecionadas_lista'],
                         periodos_disponiveis=dados_tabela['periodos_disponiveis'])