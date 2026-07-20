from .exercise_utils import get_series_from_registro, calcular_volume_total

def calcular_estatisticas_musculo(registros, exercicios):
    """Calcula estatísticas por músculo"""
    musculo_stats = {}
    for r in registros:
        ex = next(e for e in exercicios if e["id"] == r["exercicio_id"])
        musculo = ex["musculo"]
        if musculo not in musculo_stats:
            musculo_stats[musculo] = {
                "carga_total": 0, 
                "volume_total": 0, 
                "qtd_exercicios": 0,
                "qtd_registros": 0,
                "total_series": 0
            }
        
        series = get_series_from_registro(r)
        volume_exercicio = calcular_volume_total(series)
        musculo_stats[musculo]["volume_total"] += volume_exercicio
        musculo_stats[musculo]["qtd_registros"] += 1
        musculo_stats[musculo]["total_series"] += len(series)
    
    for e in exercicios:
        musculo = e["musculo"]
        if musculo in musculo_stats:
            musculo_stats[musculo]["qtd_exercicios"] += 1
    
    return musculo_stats

def calcular_estatisticas_treino(treinos, exercicios, registros):
    """Calcula estatísticas por treino"""
    treino_stats = {}
    for t in treinos:
        treino_id = t["id"]
        exercicios_treino = [e for e in exercicios if e["treino"] == treino_id]
        registros_treino = [r for r in registros if r["treino"] == treino_id]
        
        volume_total = 0
        total_series = 0
        for r in registros_treino:
            series = get_series_from_registro(r)
            volume_total += calcular_volume_total(series)
            total_series += len(series)
        
        treino_stats[treino_id] = {
            "descricao": t["descricao"],
            "qtd_exercicios": len(exercicios_treino),
            "qtd_registros": len(registros_treino),
            "volume_total": volume_total,
            "total_series": total_series
        }
    
    return treino_stats