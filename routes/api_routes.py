from flask import Blueprint, jsonify, request
from flask_login import login_required
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
from services.registro_service import RegistroService
from services.estatistica_service import EstatisticaService
from utils.exercise_utils import buscar_musculo_no_catalogo, remover_acentos
import json
import hashlib
from pathlib import Path
import logging

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

@api_bp.route("/progresso")
@login_required
def api_progresso():
    """API de dados de progresso para gráficos"""
    treino = request.args.get("treino")
    
    dados = EstatisticaService.get_progresso_por_semana(treino if treino != 'todos' else None)
    
    semanas = []
    volumes = []
    cargas_medias = []
    
    # Ordenar por período e semana
    ordem_meses = {
        "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
        "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
        "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
    }
    
    def extrair_ordenacao(item):
        periodo = item.periodo
        mes_nome = periodo.split('/')[0] if '/' in periodo else periodo.split(' ')[0]
        ano = 2024
        if '/' in periodo and len(periodo.split('/')) > 1:
            try:
                ano = int(periodo.split('/')[1])
            except:
                pass
        return (ano, ordem_meses.get(mes_nome, 0), item.semana)
    
    dados_ordenados = sorted(dados, key=extrair_ordenacao)
    
    for item in dados_ordenados:
        semanas.append(f"{item.periodo} - S{item.semana}")
        volumes.append(float(item.volume_total) if item.volume_total else 0)
        cargas_medias.append(float(item.carga_media) if item.carga_media else 0)
    
    return jsonify({
        "semanas": semanas,
        "volumes": volumes,
        "cargas_medias": cargas_medias
    })

@api_bp.route("/buscar-musculo")
@login_required
def api_buscar_musculo():
    """API para buscar músculo de um exercício"""
    nome = request.args.get("nome", "").strip()
    
    if not nome:
        return jsonify({"encontrado": False, "mensagem": "Nome não fornecido"})
    
    musculo = buscar_musculo_no_catalogo(nome)
    
    if musculo:
        return jsonify({
            "encontrado": True, 
            "musculo": musculo,
            "mensagem": f"Músculo encontrado: {musculo}"
        })
    else:
        return jsonify({
            "encontrado": False, 
            "mensagem": "Músculo não encontrado no catálogo"
        })

@api_bp.route("/buscar-exercicios")
@login_required
def api_buscar_exercicios():
    """API para buscar exercícios no catálogo"""
    termo = request.args.get("termo", "").strip()
    
    # Caminho do catálogo
    catalogo_path = Path("storage/exercises-ptbr-full-translation.json")
    
    termo_normalizado = remover_acentos(termo.lower())
    
    if not catalogo_path.exists():
        logger.error(f"Catálogo não encontrado: {catalogo_path}")
        return jsonify([])
    
    try:
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            catalogo = json.load(f)
        
        resultados = []
        
        mapa_musculos = {
            'abdominais': 'Abdômen',
            'abductors': 'Abdutores',
            'adductors': 'Adutores',
            'biceps': 'Bíceps',
            'calves': 'Panturrilhas',
            'chest': 'Peitoral',
            'forearms': 'Antebraços',
            'glutes': 'Glúteos',
            'hamstrings': 'Posterior de Coxa',
            'lats': 'Dorsal',
            'lower back': 'Lombar',
            'middle back': 'Costas',
            'neck': 'Pescoço',
            'quadriceps': 'Quadríceps',
            'shoulders': 'Ombros',
            'traps': 'Trapézio',
            'triceps': 'Tríceps'
        }
        
        for ex in catalogo:
            nome = ex.get('name', '')
            primary_muscles = ex.get('primaryMuscles', [])
            musculo_original = primary_muscles[0] if primary_muscles else "Não especificado"
            
            nome_normalizado = remover_acentos(nome.lower())
            musculo_exibicao = mapa_musculos.get(musculo_original.lower(), musculo_original.title())
            
            if termo:
                if termo_normalizado in nome_normalizado:
                    id_hash = int(hashlib.md5(nome.encode()).hexdigest()[:8], 16)
                    resultados.append({
                        "id": id_hash,
                        "nome": nome,
                        "musculo": musculo_exibicao
                    })
            else:
                if len(resultados) < 200:
                    id_hash = int(hashlib.md5(nome.encode()).hexdigest()[:8], 16)
                    resultados.append({
                        "id": id_hash,
                        "nome": nome,
                        "musculo": musculo_exibicao
                    })
        
        return jsonify(resultados)
        
    except Exception as e:
        logger.error(f"Erro ao buscar catálogo: {e}")
        return jsonify([])

@api_bp.route("/verificar-treino")
@login_required
def api_verificar_treino():
    """Verifica se um código de treino já existe"""
    treino_id = request.args.get("id", "").upper()
    treino = TreinoService.get_by_codigo(treino_id)
    
    return jsonify({"existe": treino is not None})

@api_bp.route("/versao-exercicios/<int:versao_id>")
@login_required
def api_versao_exercicios(versao_id):
    """Retorna exercícios de uma versão"""
    exercicios = VersaoService.get_exercicios(versao_id)
    
    resultado = []
    for ex in exercicios:
        musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else "Não especificado"
        resultado.append({
            "id": ex.id,
            "nome": ex.nome,
            "musculo": musculo_nome,
            "treino": ex.treino_id
        })
    
    return jsonify(resultado)

@api_bp.route("/evolucao/<int:exercicio_id>")
@login_required
def api_evolucao_exercicio(exercicio_id):
    """Dados de evolução de um exercício"""
    exercicio = ExercicioService.get_by_id(exercicio_id)
    
    if not exercicio:
        return jsonify({"error": "Exercício não encontrado"}), 404
    
    registros = RegistroService.get_all({'exercicio_id': exercicio_id}, load_series=True)
    
    dados = []
    for r in registros:
        series_list = []
        for s in r.series:
            series_list.append({
                "carga": float(s.carga),
                "repeticoes": s.repeticoes
            })
        
        from utils.exercise_utils import calcular_media_series, calcular_volume_total
        media_carga, media_reps = calcular_media_series(series_list)
        volume_total = calcular_volume_total(series_list)
        
        dados.append({
            "sessao": f"{r.periodo} - S{r.semana}",
            "series": series_list,
            "media_carga": media_carga,
            "media_reps": media_reps,
            "volume_total": volume_total,
            "num_series": len(series_list)
        })
    
    return jsonify({
        "exercicio": exercicio.nome,
        "dados": dados
    })

@api_bp.route("/criar-exercicio", methods=["POST"])
@login_required
def api_criar_exercicio():
    """Cria um exercício via API"""
    data = request.json
    
    if not data or not data.get("nome"):
        return jsonify({"success": False, "error": "Nome é obrigatório"}), 400
    
    novo_exercicio = ExercicioService.create(
        nome=data["nome"],
        musculo_nome=data.get("musculo", "Outros"),
        treino_id=data.get("treino")
    )
    
    if novo_exercicio:
        logger.info(f"Exercício {data['nome']} criado via API")
        return jsonify({"success": True, "id": novo_exercicio.id})
    else:
        return jsonify({"success": False, "error": "Erro ao criar exercício"}), 500

# ============================================================================
# NOVAS ROTAS DO CATÁLOGO
# ============================================================================

@api_bp.route("/catalogo/todos")
@login_required
def api_catalogo_todos():
    """Retorna todos os exercícios do catálogo"""
    from services.catalogo_service import CatalogoService
    
    try:
        # Parâmetro opcional de limite
        limite = request.args.get("limite", 500, type=int)
        exercicios = CatalogoService.get_todos_exercicios(limite=limite)
        return jsonify(exercicios)
    except Exception as e:
        logger.error(f"Erro ao buscar catálogo: {e}")
        return jsonify([])

@api_bp.route("/catalogo/buscar")
@login_required
def api_catalogo_buscar():
    """Busca exercícios no catálogo JSON"""
    termo = request.args.get("termo", "").strip()
    musculo = request.args.get("musculo", "").strip()
    
    from services.catalogo_service import CatalogoService
    
    try:
        resultados = CatalogoService.buscar_exercicios(
            termo=termo if termo else None,
            musculo=musculo if musculo else None
        )
        return jsonify(resultados)
    except Exception as e:
        logger.error(f"Erro ao buscar no catálogo: {e}")
        return jsonify([])

@api_bp.route("/catalogo/musculos")
@login_required
def api_catalogo_musculos():
    """Retorna lista de músculos disponíveis no catálogo"""
    from services.catalogo_service import CatalogoService
    
    try:
        musculos = CatalogoService.get_musculos_disponiveis()
        return jsonify(musculos)
    except Exception as e:
        logger.error(f"Erro ao buscar músculos do catálogo: {e}")
        return jsonify([])

# ============================================================================
# ROTA PARA DEBUG (OPCIONAL)
# ============================================================================

@api_bp.route("/debug/rotas")
@login_required
def api_debug_rotas():
    """Retorna lista de todas as rotas da API (para debug)"""
    from flask import current_app
    
    rotas = []
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint.startswith('api.'):
            rotas.append({
                "endpoint": rule.endpoint,
                "methods": list(rule.methods),
                "path": str(rule)
            })
    
    return jsonify(rotas)