from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone
from services.versao_service import VersaoService
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.catalogo_service import CatalogoService
from models import db, TreinoVersao, VersaoExercicio, ExercicioCustomizado, ExercicioBase
from utils.format_utils import formatar_data
import logging

logger = logging.getLogger(__name__)
version_bp = Blueprint('version', __name__)

# =============================================
# ROTAS EXISTENTES (MANTIDAS)
# =============================================

@version_bp.route("/gerenciar-versoes")
@login_required
def gerenciar_versoes_global():
    versoes = VersaoService.get_all()
    exercicios = ExercicioService.get_exercicios_completos()
    treinos = TreinoService.get_all()
    musculos = MusculoService.get_all_nomes()
    versoes_formatadas = []
    for v in versoes:
        versoes_formatadas.append({
            "id": v.id,
            "versao": v.numero_versao,
            "descricao": v.descricao,
            "data_inicio": v.data_inicio.isoformat() if v.data_inicio else None,
            "data_fim": v.data_fim.isoformat() if v.data_fim else None,
            "data_inicio_formatada": formatar_data(v.data_inicio.isoformat() if v.data_inicio else None),
            "data_fim_formatada": formatar_data(v.data_fim.isoformat() if v.data_fim else None),
            "treinos": VersaoService.get_treinos(v.id)
        })
    return render_template("version/gerenciar_versoes_global.html",
                         versoes=versoes_formatadas,
                         exercicios=exercicios,
                         treinos=treinos,
                         musculos=musculos)

@version_bp.route("/salvar/versao", methods=["POST"])
@login_required
def salvar_versao_global():
    descricao = request.form["descricao"]
    divisao = request.form.get("divisao", "ABC")
    data_inicio = datetime.strptime(request.form["data_inicio"], '%Y-%m-%d').date()
    data_fim_str = request.form.get("data_fim")
    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    versao_ativa = VersaoService.get_ativa()
    if versao_ativa and not data_fim:
        flash(f"Já existe uma versão ativa. Finalize-a antes de criar outra.", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    nova_versao = VersaoService.create(descricao, data_inicio, divisao, data_fim)
    if nova_versao:
        logger.info(f"Nova versão criada: {nova_versao.numero_versao} - Divisão {divisao}")
        flash(f"Nova versão criada com sucesso! Divisão: {divisao}", "success")
    else:
        flash("Erro ao criar versão!", "danger")
    return redirect(url_for("version.gerenciar_versoes_global"))

@version_bp.route("/ver/<int:versao_id>", methods=["GET", "POST"])
@login_required
def ver_versao(versao_id):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        flash("Versão não encontrada!", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    if request.method == "POST":
        versao.descricao = request.form["descricao"]
        nova_divisao = request.form.get("divisao")
        if nova_divisao in ['ABC', 'ABCD', 'ABCDE']:
            versao.divisao = nova_divisao
        versao.data_inicio = datetime.strptime(request.form["data_inicio"], '%Y-%m-%d').date()
        data_fim_str = request.form.get("data_fim")
        versao.data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        db.session.commit()
        logger.info(f"Versão {versao_id} atualizada")
        flash(f"Versão {versao.numero_versao} atualizada! Divisão: {versao.divisao}", "success")
        return redirect(url_for("version.ver_versao", versao_id=versao_id))
    treinos_dict = VersaoService.get_treinos(versao_id)
    versao_dict = {
        "id": versao.id,
        "versao": versao.numero_versao,
        "descricao": versao.descricao,
        "divisao": versao.divisao,
        "data_inicio": versao.data_inicio.isoformat() if versao.data_inicio else None,
        "data_fim": versao.data_fim.isoformat() if versao.data_fim else None,
        "data_inicio_formatada": formatar_data(versao.data_inicio.isoformat() if versao.data_inicio else None),
        "data_fim_formatada": formatar_data(versao.data_fim.isoformat() if versao.data_fim else None),
        "treinos": treinos_dict
    }
    exercicios = ExercicioService.get_exercicios_completos()
    treinos = TreinoService.get_all()
    musculos = MusculoService.get_all_nomes()
    return render_template("version/ver_versao.html",
                         versao=versao_dict,
                         exercicios=exercicios,
                         treinos=treinos,
                         musculos=musculos)

@version_bp.route("/finalizar/<int:versao_id>")
@login_required
def finalizar_versao_global(versao_id):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        flash("Versão não encontrada!", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    if versao.data_fim:
        flash(f"Versão já finalizada em {formatar_data(versao.data_fim.isoformat())}.", "warning")
        return redirect(url_for("version.gerenciar_versoes_global"))
    data_atual = datetime.now().date()
    if VersaoService.finalizar(versao_id, data_atual):
        logger.info(f"Versão {versao_id} finalizada")
        flash(f"Versão {versao.numero_versao} finalizada!", "success")
    else:
        flash(f"Erro ao finalizar versão!", "danger")
    return redirect(url_for("version.gerenciar_versoes_global"))

@version_bp.route("/clonar/<int:versao_id>")
@login_required
def clonar_versao_global(versao_id):
    if VersaoService.clone(versao_id):
        logger.info(f"Versão {versao_id} clonada")
        flash(f"Versão clonada com sucesso!", "success")
    else:
        flash(f"Erro ao clonar versão!", "danger")
    return redirect(url_for("version.gerenciar_versoes_global"))

@version_bp.route("/api/criar-treino", methods=["POST"])
@login_required
def api_criar_treino():
    data = request.get_json()
    treino_codigo = data.get('id', '').upper()
    nome = data.get('nome', '')
    descricao = data.get('descricao', '')
    if not treino_codigo or not nome:
        return jsonify({"success": False, "error": "ID e nome são obrigatórios"}), 400
    existente = TreinoService.get_by_codigo(treino_codigo)
    if existente:
        return jsonify({"success": False, "error": f"Treino {treino_codigo} já existe!"}), 400
    novo_treino = TreinoService.create(treino_codigo, nome, descricao)
    if novo_treino:
        return jsonify({"success": True, "id": novo_treino.id, "codigo": novo_treino.codigo, "nome": novo_treino.nome})
    else:
        return jsonify({"success": False, "error": "Erro ao salvar no banco de dados"}), 500

# =============================================
# NOVAS ROTAS (ADICIONADAS)
# =============================================

@version_bp.route("/versao/<int:versao_id>/novo-treino", methods=["GET", "POST"])
@login_required
def novo_treino_na_versao(versao_id):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        flash("Versão não encontrada!", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    treinos_atuais = TreinoVersao.query.filter_by(versao_id=versao_id).count()
    max_treinos = 3
    if hasattr(versao, 'divisao'):
        if versao.divisao == 'ABCD':
            max_treinos = 4
        elif versao.divisao == 'ABCDE':
            max_treinos = 5
    if request.method == "POST":
        treino_codigo = request.form.get("treino_id", "").upper()
        nome_treino = request.form.get("nome_treino")
        descricao_treino = request.form.get("descricao_treino", "")
        tipo_criacao = request.form.get("tipo_criacao", "vazio")
        if not treino_codigo or not treino_codigo.isalpha() or len(treino_codigo) != 1:
            flash("ID do treino deve ser uma única letra!", "danger")
            return redirect(url_for("version.novo_treino_na_versao", versao_id=versao_id))
        letras_permitidas = list(versao.divisao)
        if treino_codigo not in letras_permitidas:
            flash(f"Para divisão {versao.divisao}, o treino deve ser uma das letras: {', '.join(letras_permitidas)}", "danger")
            return redirect(url_for("version.novo_treino_na_versao", versao_id=versao_id))
        if treinos_atuais >= max_treinos:
            flash(f"Limite de {max_treinos} treinos atingido para esta versão!", "danger")
            return redirect(url_for("version.ver_versao", versao_id=versao_id))
        treinos_existentes = {}
        for tv in versao.treinos:
            treino = TreinoService.get_by_id(tv.treino_id)
            if treino:
                treinos_existentes[treino.codigo] = tv
        if treino_codigo in treinos_existentes:
            flash(f"Treino {treino_codigo} já existe nesta versão!", "danger")
            return redirect(url_for("version.novo_treino_na_versao", versao_id=versao_id))
        exercicios_ids = []
        if tipo_criacao == "padrao" and request.form.get("treino_padrao"):
            treino_padrao_id = request.form.get("treino_padrao")
            exercicios_padrao = ExercicioService.get_by_treino(treino_padrao_id)
            exercicios_ids = [ex.id for ex in exercicios_padrao]
        if VersaoService.adicionar_treino(versao_id, treino_codigo, nome_treino, descricao_treino, exercicios_ids):
            logger.info(f"Treino {treino_codigo} adicionado à versão {versao_id}")
            flash(f"Treino {treino_codigo} adicionado com sucesso!", "success")
            return redirect(url_for("version.ver_versao", versao_id=versao_id))
        else:
            flash("Erro ao adicionar treino!", "danger")
            return redirect(url_for("version.novo_treino_na_versao", versao_id=versao_id))
    treinos_padrao = TreinoService.get_all()
    versao_dict = {
        "id": versao.id,
        "versao": versao.numero_versao,
        "descricao": versao.descricao,
        "divisao": versao.divisao if hasattr(versao, 'divisao') else 'ABC',
        "data_inicio_formatada": versao.data_inicio.strftime("%d/%m/%Y") if versao.data_inicio else "",
        "data_fim_formatada": versao.data_fim.strftime("%d/%m/%Y") if versao.data_fim else ""
    }
    return render_template("version/novo_treino_versao.html",
                         versao=versao_dict,
                         treinos_padrao=treinos_padrao,
                         treinos_atuais=treinos_atuais,
                         max_treinos=max_treinos)

# ==========================================================
# ROTA EDITAR TREINO NA VERSÃO (REFATORADA)
# ==========================================================
@version_bp.route("/versao/<int:versao_id>/treino/<string:treino_codigo>/editar", methods=["GET", "POST"])
@login_required
def editar_treino_na_versao(versao_id, treino_codigo):
    if request.method == "POST":
        nome_treino = request.form.get("nome_treino")
        descricao_treino = request.form.get("descricao_treino", "")
        valores = request.form.getlist("exercicios[]")
        usuarios_ids = []
        bases_ids = []
        for val in valores:
            if val.startswith('u_'):
                usuarios_ids.append(int(val[2:]))
            elif val.startswith('b_'):
                bases_ids.append(int(val[2:]))
        
        if not usuarios_ids and not bases_ids:
            flash("Selecione pelo menos um exercício!", "danger")
            return redirect(request.url)
        
        # Validar IDs
        from models import ExercicioUsuario, ExercicioBase
        usuarios_ids_validos = [eid for eid in usuarios_ids if ExercicioUsuario.query.get(eid)]
        bases_ids_validos = [eid for eid in bases_ids if ExercicioBase.query.get(eid)]
        
        try:
            versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
            if not versao:
                flash("Versão não encontrada!", "danger")
                return redirect(request.url)
            
            treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)
            if not treino_ref:
                flash("Treino não encontrado!", "danger")
                return redirect(request.url)
            
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino_ref.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                flash("Treino não encontrado nesta versão!", "danger")
                return redirect(request.url)
            
            treino_versao.nome_treino = nome_treino
            treino_versao.descricao_treino = descricao_treino
            
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id,
                usuarios_ids_validos,
                bases_ids_validos
            )
            
            db.session.commit()
            flash(f"Treino {treino_codigo} atualizado com sucesso!", "success")
            return redirect(url_for("version.ver_versao", versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao editar treino: {e}")
            flash(str(e), "danger")
            return redirect(request.url)
    
    # GET - exibir formulário (mantenha o código existente, mas ajuste para incluir 'tipo' nos exercícios)
    # ... (código GET já existente, apenas garanta que 'tipo' está sendo passado)

@version_bp.route("/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir")
@login_required
def excluir_treino_da_versao(versao_id, treino_codigo):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        flash("Versão não encontrada!", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    treino_ref = TreinoService.get_by_codigo(treino_codigo)
    if not treino_ref:
        flash(f"Treino {treino_codigo} não encontrado!", "danger")
        return redirect(url_for("version.ver_versao", versao_id=versao_id))
    resultado = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino_ref.id).delete()
    if resultado:
        db.session.commit()
        logger.info(f"Treino {treino_codigo} removido da versão {versao_id}")
        flash(f"Treino {treino_codigo} removido da versão!", "success")
    else:
        flash(f"Erro ao remover treino {treino_codigo}!", "danger")
    return redirect(url_for("version.ver_versao", versao_id=versao_id))

@version_bp.route("/versao/<int:versao_id>/treino/<string:treino_codigo>/reordenar", methods=["POST"])
@login_required
def reordenar_exercicios(versao_id, treino_codigo):
    data = request.get_json()
    nova_ordem = data.get("nova_ordem", [])
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        return jsonify({"success": False, "error": "Versão não encontrada"}), 404
    treino_ref = TreinoService.get_by_codigo(treino_codigo)
    if not treino_ref:
        return jsonify({"success": False, "error": "Treino não encontrado"}), 404
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        return jsonify({"success": False, "error": "Treino não encontrado na versão"}), 404
    for ordem, ex_id in enumerate(nova_ordem):
        for ve in treino_versao.exercicios:
            if ve.exercicio_id == ex_id:
                ve.ordem = ordem
                break
    db.session.commit()
    return jsonify({"success": True})

@version_bp.route("/versao/<int:versao_id>/treino/<string:treino_codigo>/exercicio/adicionar", methods=["POST"])
@login_required
def adicionar_exercicio_na_versao(versao_id, treino_codigo):
    data = request.get_json()
    exercicio_id = data.get("exercicio_id")
    if not exercicio_id:
        return jsonify({"success": False, "error": "ID do exercício não fornecido"}), 400
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        return jsonify({"success": False, "error": "Versão não encontrada"}), 404
    treino_ref = TreinoService.get_by_codigo(treino_codigo)
    if not treino_ref:
        return jsonify({"success": False, "error": "Treino não encontrado"}), 404
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        return jsonify({"success": False, "error": "Treino não encontrado na versão"}), 404
    for ve in treino_versao.exercicios:
        if ve.exercicio_id == exercicio_id:
            return jsonify({"success": True, "message": "Exercício já existe"})
    nova_ordem = len(treino_versao.exercicios)
    VersaoService.adicionar_exercicio_a_treino_versao(treino_versao.id, exercicio_id, nova_ordem)
    return jsonify({"success": True})

@version_bp.route("/versao/<int:versao_id>/treino/<string:treino_codigo>/exercicio/<int:exercicio_id>/remover", methods=["POST"])
@login_required
def remover_exercicio_da_versao(versao_id, treino_codigo, exercicio_id):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        return jsonify({"success": False, "error": "Versão não encontrada"}), 404
    treino_ref = TreinoService.get_by_codigo(treino_codigo)
    if not treino_ref:
        return jsonify({"success": False, "error": "Treino não encontrado"}), 404
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        return jsonify({"success": False, "error": "Treino não encontrado na versão"}), 404
    resultado = VersaoExercicio.query.filter_by(
        treino_versao_id=treino_versao.id,
        exercicio_id=exercicio_id
    ).delete()
    if resultado:
        db.session.commit()
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Exercício não encontrado"}), 404

@version_bp.route("/excluir/<int:versao_id>")
@login_required
def excluir_versao_global(versao_id):
    versao = VersaoService.get_by_id(versao_id)
    if not versao:
        logger.warning(f"Tentativa de excluir versão inexistente: {versao_id}")
        flash("Versão não encontrada!", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    versao_ativa = VersaoService.get_ativa()
    if versao_ativa and versao_ativa.id == versao_id:
        flash("Não é possível excluir a versão ativa. Finalize-a primeiro.", "warning")
        return redirect(url_for("version.gerenciar_versoes_global"))
    from models import RegistroTreino
    registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=current_user.id).first()
    if registros:
        flash("Não é possível excluir esta versão pois existem registros de treino vinculados a ela. Exclua os registros primeiro ou arquive a versão.", "danger")
        return redirect(url_for("version.gerenciar_versoes_global"))
    confirmado = request.args.get("confirmar", "false").lower() == "true"
    if not confirmado:
        flash(f"⚠️ Clique novamente em 'Excluir' para confirmar a exclusão da versão {versao.numero_versao} - {versao.descricao}. Esta ação não pode ser desfeita!", "warning")
        return redirect(url_for("version.gerenciar_versoes_global"))
    if VersaoService.delete(versao_id):
        logger.info(f"Versão {versao_id} excluída pelo usuário {current_user.id}")
        flash(f"✅ Versão {versao.numero_versao} - {versao.descricao} excluída com sucesso!", "success")
    else:
        flash("❌ Erro ao excluir versão!", "danger")
    return redirect(url_for("version.gerenciar_versoes_global"))