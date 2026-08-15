from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone, date
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


# ============================================================================
# PROGRESSO E GRÁFICOS
# ============================================================================

@api_bp.route("/progresso")
@login_required
def api_progresso():
    """
    API de dados de progresso para o gráfico de evolução.
    Retorna apenas os últimos 30 dias corridos (calendário real), com os
    dias sem registro preenchidos em 0 para o gráfico ficar contínuo.
    """
    treino = request.args.get("treino")

    dados = EstatisticaService.get_progresso_ultimos_30_dias(treino if treino != 'todos' else None)

    if not dados:
        # Sem nenhum registro nos últimos 30 dias: mantém a resposta vazia
        # para o front-end mostrar o estado "ainda não há treinos" (em vez
        # de um gráfico com uma linha zerada).
        return jsonify({"semanas": [], "volumes": [], "cargas_medias": []})

    # dia -> (volume_total, carga_media), vindo do banco (chave pode ser
    # date ou string dependendo do driver/backend do SQLAlchemy)
    por_dia = {}
    for item in dados:
        chave = item.dia if isinstance(item.dia, date) else datetime.strptime(str(item.dia), "%Y-%m-%d").date()
        por_dia[chave] = item

    hoje = datetime.now(timezone.utc).date()
    dias_janela = [hoje - timedelta(days=i) for i in range(29, -1, -1)]

    semanas = []
    volumes = []
    cargas_medias = []

    for dia in dias_janela:
        item = por_dia.get(dia)
        semanas.append(dia.strftime("%d/%m"))
        volumes.append(float(item.volume_total) if item and item.volume_total else 0)
        cargas_medias.append(float(item.carga_media) if item and item.carga_media else 0)

    return jsonify({
        "semanas": semanas,
        "volumes": volumes,
        "cargas_medias": cargas_medias
    })


# ============================================================================
# BUSCA DE MÚSCULOS E EXERCÍCIOS
# ============================================================================

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


_CATALOGO_EXERCICIOS_CACHE = None


def _get_catalogo_exercicios():
    """
    Carrega e cacheia em memória o catálogo de exercícios (JSON estático,
    somente leitura). Antes, o arquivo era reaberto e re-parseado do disco
    em TODA chamada a /buscar-exercicios — medido em ~215ms de parse só
    pra abrir o arquivo (catálogo de referência de ~1300 itens/2.2MB usado
    como proxy, já que o arquivo real de produção não está neste
    checkout), fora o loop de comparação de string sobre o catálogo
    inteiro a cada tecla digitada numa busca type-ahead.

    Cada worker do Gunicorn mantém sua própria cópia em memória (arquivo é
    estático e pequeno o bastante pra isso ser trivial — não precisa de
    Redis/Postgres pra um catálogo somente-leitura que não muda em
    runtime).
    """
    global _CATALOGO_EXERCICIOS_CACHE
    if _CATALOGO_EXERCICIOS_CACHE is not None:
        return _CATALOGO_EXERCICIOS_CACHE

    catalogo_path = Path("storage/exercises-ptbr-full-translation.json")
    if not catalogo_path.exists():
        logger.error(f"Catálogo não encontrado: {catalogo_path}")
        return []

    with open(catalogo_path, 'r', encoding='utf-8') as f:
        _CATALOGO_EXERCICIOS_CACHE = json.load(f)
    return _CATALOGO_EXERCICIOS_CACHE


@api_bp.route("/buscar-exercicios")
@login_required
def api_buscar_exercicios():
    """API para buscar exercícios no catálogo"""
    termo = request.args.get("termo", "").strip()

    termo_normalizado = remover_acentos(termo.lower())

    try:
        catalogo = _get_catalogo_exercicios()
        if not catalogo:
            return jsonify([])

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
                    id_hash = int(hashlib.md5(nome.encode(), usedforsecurity=False).hexdigest()[:8], 16)
                    resultados.append({
                        "id": id_hash,
                        "nome": nome,
                        "musculo": musculo_exibicao
                    })
            else:
                if len(resultados) < 200:
                    id_hash = int(hashlib.md5(nome.encode(), usedforsecurity=False).hexdigest()[:8], 16)
                    resultados.append({
                        "id": id_hash,
                        "nome": nome,
                        "musculo": musculo_exibicao
                    })
        
        return jsonify(resultados)
        
    except Exception:
        logger.exception("Erro ao buscar catálogo")
        return jsonify([])


# ============================================================================
# VERIFICAÇÕES
# ============================================================================

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
        musculo_nome = ex.musculo_nome or "Não especificado"
        resultado.append({
            "id": ex.id,
            "nome": ex.nome,
            "musculo": musculo_nome
        })
    
    return jsonify(resultado)


# ============================================================================
# EVOLUÇÃO E ESTATÍSTICAS
# ============================================================================

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


# ============================================================================
# CRIAÇÃO DE EXERCÍCIOS
# ============================================================================

@api_bp.route("/criar-exercicio", methods=["POST"])
@login_required
def api_criar_exercicio():
    """Cria um exercício via API"""
    data = request.json
    
    if not data or not data.get("nome"):
        return jsonify({"success": False, "error": "Nome é obrigatório"}), 400
    
    novo_exercicio = ExercicioService.criar_exercicio_customizado(
        user_id=current_user.id,
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
# CATÁLOGO DE EXERCÍCIOS
# ============================================================================

@api_bp.route("/catalogo/todos")
@login_required
def api_catalogo_todos():
    """Retorna todos os exercícios do catálogo"""
    from services.catalogo_service import CatalogoService

    # CORREÇÃO seção 14 (hardening de segurança): "limite" vinha direto
    # do cliente sem teto e ia parar num LIMIT de SQL -- um valor
    # gigante (ou negativo) força o banco a preparar/varrer muito mais
    # linhas do que a tela realmente usa. Trava em MAX_LIMITE, validação
    # local O(1), sem custo de query extra.
    MAX_LIMITE = 500
    limite = request.args.get("limite", MAX_LIMITE, type=int) or MAX_LIMITE
    limite = max(1, min(limite, MAX_LIMITE))

    try:
        exercicios = CatalogoService.get_todos_exercicios(limite=limite)
        return jsonify(exercicios)
    except Exception:
        logger.exception("Erro ao buscar catálogo")
        return jsonify([])


@api_bp.route("/catalogo/buscar")
@login_required
def api_catalogo_buscar():
    """Busca exercícios no catálogo"""
    termo = request.args.get("termo", "").strip()
    musculo = request.args.get("musculo", "").strip()
    
    from services.catalogo_service import CatalogoService
    
    try:
        resultados = CatalogoService.buscar_exercicios(
            termo=termo if termo else None,
            musculo=musculo if musculo else None
        )
        return jsonify(resultados)
    except Exception:
        logger.exception("Erro ao buscar no catálogo")
        return jsonify([])


@api_bp.route("/catalogo/musculos")
@login_required
def api_catalogo_musculos():
    """Retorna lista de músculos disponíveis no catálogo"""
    from services.catalogo_service import CatalogoService
    
    try:
        musculos = CatalogoService.get_musculos_disponiveis()
        return jsonify(musculos)
    except Exception:
        logger.exception("Erro ao buscar músculos do catálogo")
        return jsonify([])


# ============================================================================
# REORDENAR EXERCÍCIOS
# ============================================================================

@api_bp.route("/reordenar-exercicios", methods=["POST"])
@login_required
def api_reordenar_exercicios():
    """API para reordenar exercícios de um treino na versão"""
    try:
        data = request.get_json()
        
        versao_id = data.get('versao_id')
        user_id = current_user.id
        treino_codigo = data.get('treino_codigo')
        nova_ordem = data.get('nova_ordem')
        
        if not versao_id or not treino_codigo or not nova_ordem:
            return jsonify({
                "success": False, 
                "error": "Dados incompletos"
            }), 400
        
        from services.exercicio_service import ExercicioService
        
        sucesso = ExercicioService.reordenar_exercicios(
            versao_id=versao_id,
            treino_codigo=treino_codigo,
            nova_ordem_ids=nova_ordem,
            user_id=current_user.id
        )
        
        if sucesso:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Erro ao reordenar"}), 500
        
    except Exception as e:
        logger.exception("Erro na API reordenar-exercicios")
        # CORREÇÃO seção 13 (hardening de segurança): não devolver
        # str(e) ao cliente -- pode vazar detalhes internos (SQL, nomes
        # de tabela/coluna, caminhos do servidor). O detalhe real já foi
        # logado no server acima via logger.exception.
        return jsonify({"success": False, "error": "Não foi possível concluir a operação."}), 500


# ============================================================================
# DEBUG (OPCIONAL)
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