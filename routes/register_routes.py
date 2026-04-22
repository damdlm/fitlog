from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, timezone
from services.treino_service import TreinoService
from services.versao_service import VersaoService
from services.exercicio_service import ExercicioService
from services.registro_service import RegistroService
from utils.date_utils import data_para_periodo, data_para_semana, formatar_data_br, validar_data
import logging

register_bp = Blueprint('register', __name__)
logger = logging.getLogger(__name__)

@register_bp.route("/registrar-treino", methods=["GET"])
@login_required
def registrar_treino():
    """
    Página de registro de treino - Nova versão com seleção por data
    Agora os treinos são filtrados pela versão ativa na data selecionada
    """
    data_selecionada_str = request.args.get("data") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    treino_selecionado = request.args.get("treino")
    
    exercicios = []
    registros_map = {}
    historico_series = {}
    versao_info = None
    erro_versao = None
    treinos_disponiveis = []
    
    # Validar a data e converter para objeto date
    data_valida, data_obj = validar_data(data_selecionada_str)
    if not data_valida:
        flash(data_obj, "danger")
        data_obj = datetime.now().date()
        data_selecionada_str = data_obj.strftime("%Y-%m-%d")
    else:
        data_obj = data_obj
    
    # Buscar versão ativa na data
    versao_ativa = VersaoService.get_ativa_por_data(data_obj)
    
    if not versao_ativa:
        erro_versao = f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}"
        logger.warning(f"Tentativa de registro sem versão ativa para data {data_obj}")
    else:
        # Buscar treinos disponíveis nesta versão
        treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
        
        versao_info = {
            'id': versao_ativa.id,
            'numero': versao_ativa.numero_versao,
            'descricao': versao_ativa.descricao,
            'divisao': versao_ativa.divisao
        }
        
        # Se um treino foi selecionado, carregar seus exercícios
        if treino_selecionado:
            # Verificar se o treino selecionado está na versão ativa
            treino_valido = False
            treino_codigo = None
            for t in treinos_disponiveis:
                if str(t['id']) == str(treino_selecionado):
                    treino_valido = True
                    treino_codigo = t['codigo']  # ← PEGA O CÓDIGO (A, B, C...)
                    break
            
            if not treino_valido:
                flash(f"Treino não encontrado na versão ativa para esta data!", "warning")
                treino_selecionado = None
            else:
                # Buscar exercícios do treino nesta versão usando o CÓDIGO
                exercicios = VersaoService.get_exercicios(versao_ativa.id, treino_codigo)
                
                logger.info(f"Buscando exercícios para versão {versao_ativa.id}, treino {treino_codigo}")
                logger.info(f"Encontrados {len(exercicios)} exercícios")
                
                # Buscar registros existentes para esta data
                registros = RegistroService.get_by_data(
                    treino_id=treino_selecionado,  # ← USA ID (correto para registros)
                    versao_id=versao_ativa.id,
                    data=data_obj
                )
                registros_map = {r.exercicio_id: r for r in registros}
                
                # Buscar histórico para sugestão de cargas (últimos 3 registros)
                for ex in exercicios:
                    ultimas = ExercicioService.get_ultimas_series(
                        ex.id, 
                        versao_id=versao_ativa.id, 
                        limite=3
                    )
                    if ultimas:
                        historico_series[ex.id] = ultimas
    
    return render_template(
        "register/registrar_treino.html",
        treinos_disponiveis=treinos_disponiveis,
        treino_selecionado=treino_selecionado,
        data_selecionada=data_obj,  # ← AGORA É OBJETO DATE
        data_selecionada_str=data_selecionada_str,  # ← STRING PARA INPUT
        exercicios=exercicios,
        registros=registros_map,
        historico_series=historico_series,
        versao_info=versao_info,
        erro_versao=erro_versao
    )


@register_bp.route("/registrar-treino", methods=["POST"])
@login_required
def salvar_registro():
    """
    Salva o treino do dia
    """
    treino_id = request.form.get("treino")
    data_registro = request.form.get("data")
    
    # Validações básicas
    if not treino_id or not data_registro:
        flash("Treino e data são obrigatórios", "danger")
        return redirect(url_for("register.registrar_treino"))
    
    # Validar data
    data_valida, data_obj = validar_data(data_registro)
    if not data_valida:
        flash(data_obj, "danger")
        return redirect(url_for("register.registrar_treino"))
    
    # Descobrir versão ativa na data
    versao_ativa = VersaoService.get_ativa_por_data(data_obj)
    
    if not versao_ativa:
        flash(f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}", "danger")
        return redirect(url_for("register.registrar_treino", 
                              data=data_registro))
    
    if versao_ativa.data_fim and versao_ativa.data_fim < data_obj:
        flash(f"A versão {versao_ativa.numero_versao} foi finalizada em {versao_ativa.data_fim.strftime('%d/%m/%Y')}", "danger")
        return redirect(url_for("register.registrar_treino", 
                              data=data_registro))
    
    # Verificar se o treino pertence à versão ativa
    treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
    treino_valido = False
    treino_codigo = None
    for t in treinos_disponiveis:
        if str(t['id']) == str(treino_id):
            treino_valido = True
            treino_codigo = t['codigo']
            break
    
    if not treino_valido:
        flash(f"Treino não encontrado na versão ativa!", "danger")
        return redirect(url_for("register.registrar_treino", 
                              data=data_registro))
    
    # Calcular período e semana a partir da data
    periodo = data_para_periodo(data_obj)
    semana = data_para_semana(data_obj)
    
    # Buscar exercícios do treino nesta versão usando o CÓDIGO
    exercicios = VersaoService.get_exercicios(versao_ativa.id, treino_codigo)
    
    # Processar dados dos exercícios
    dados_exercicios = {}
    
    for ex in exercicios:
        carga = request.form.get(f"carga_{ex.id}")
        reps = request.form.get(f"reps_{ex.id}")
        
        if carga and reps and carga.strip() and reps.strip():
            try:
                carga_float = float(carga)
                reps_int = int(reps)
                num_series = int(request.form.get(f"num_series_{ex.id}", 3))
                
                if carga_float >= 0 and reps_int >= 0 and 1 <= num_series <= 10:
                    dados_exercicios[ex.id] = {
                        'carga': carga_float,
                        'repeticoes': reps_int,
                        'num_series': num_series,
                        'data_registro': data_obj
                    }
            except (ValueError, TypeError):
                continue
    
    if dados_exercicios:
        if RegistroService.salvar_registros(
            treino_id=treino_id,
            versao_id=versao_ativa.id,
            periodo=periodo,
            semana=semana,
            dados_exercicios=dados_exercicios
        ):
            logger.info(f"Treino {treino_id} salvo para {data_registro} (versão {versao_ativa.numero_versao})")
            flash(f"✅ Treino salvo para {data_obj.strftime('%d/%m/%Y')}!", "success")
            return redirect(url_for("main.index"))
        else:
            flash("❌ Erro ao salvar registros!", "danger")
    else:
        flash("⚠️ Nenhum dado válido para salvar!", "warning")
    
    return redirect(url_for("register.registrar_treino", 
                          treino=treino_id, 
                          data=data_registro))


@register_bp.route("/api/treinos-por-data")
@login_required
def api_treinos_por_data():
    """
    API para buscar treinos disponíveis em uma data específica
    Retorna os treinos da versão ativa na data
    """
    data_str = request.args.get("data")
    
    if not data_str:
        return jsonify({"success": False, "error": "Data não fornecida"}), 400
    
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        versao_ativa = VersaoService.get_ativa_por_data(data_obj)
        
        if not versao_ativa:
            return jsonify({
                "success": False, 
                "error": f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}"
            }), 404
        
        # Buscar treinos disponíveis nesta versão
        treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
        
        return jsonify({
            "success": True,
            "versao": {
                "id": versao_ativa.id,
                "numero": versao_ativa.numero_versao,
                "descricao": versao_ativa.descricao,
                "divisao": versao_ativa.divisao
            },
            "treinos": treinos_disponiveis
        })
        
    except Exception as e:
        logger.error(f"Erro na API treinos-por-data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500