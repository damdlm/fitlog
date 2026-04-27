from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.versao_service import VersaoService
from utils.exercise_utils import buscar_musculo_no_catalogo
from models import db, ExercicioCustomizado, ExercicioUsuario, Musculo, RegistroTreino, HistoricoTreino, ExercicioBase
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


# =============================================
# GERENCIAR TREINOS E EXERCÍCIOS
# Acessível por admin, professor e aluno
# Cada usuário gerencia apenas seus próprios dados
# =============================================

@admin_bp.route("/gerenciar")
@login_required
def gerenciar():
    """Página de gerenciamento — acessível a todos os usuários logados"""
    treinos = TreinoService.get_all(user_id=current_user.id)

    # Exercícios customizados do usuário
    exercicios_custom = ExercicioCustomizado.query.options(
        joinedload(ExercicioCustomizado.musculo_ref)
    ).filter_by(usuario_id=current_user.id).order_by(ExercicioCustomizado.nome).all()

    # Exercícios da base adicionados pelo usuário
    exercicios_usuario = ExercicioUsuario.query.options(
        joinedload(ExercicioUsuario.exercicio_base_ref)
    ).filter_by(usuario_id=current_user.id).order_by(ExercicioUsuario.id).all()

    musculos = MusculoService.get_all_nomes()

    # Contagem de exercícios por treino
    exercicios_por_treino = {}
    for ex in exercicios_custom:
        if ex.treino_id:
            exercicios_por_treino[ex.treino_id] = exercicios_por_treino.get(ex.treino_id, 0) + 1

    # Últimas cargas
    ultimas_cargas = {}
    if exercicios_custom:
        ids_custom = [ex.id for ex in exercicios_custom]
        subq = db.session.query(
            RegistroTreino.exercicio_id,
            func.max(RegistroTreino.data_registro).label('max_data')
        ).filter(
            RegistroTreino.user_id == current_user.id,
            RegistroTreino.exercicio_id.in_(ids_custom)
        ).group_by(RegistroTreino.exercicio_id).subquery()

        cargas_query = db.session.query(
            RegistroTreino.exercicio_id,
            HistoricoTreino.carga
        ).join(
            subq,
            (RegistroTreino.exercicio_id == subq.c.exercicio_id) &
            (RegistroTreino.data_registro == subq.c.max_data)
        ).join(
            HistoricoTreino,
            HistoricoTreino.registro_id == RegistroTreino.id
        ).filter(HistoricoTreino.ordem == 1).all()

        ultimas_cargas = {ex_id: float(carga) for ex_id, carga in cargas_query}

    return render_template(
        "admin/gerenciar_treinos.html",
        treinos=treinos,
        exercicios=exercicios_custom,
        exercicios_usuario=exercicios_usuario,
        musculos=musculos,
        exercicios_por_treino=exercicios_por_treino,
        ultimas_cargas=ultimas_cargas
    )


# =============================================
# TREINOS
# =============================================

@admin_bp.route("/salvar/treino", methods=["POST"])
@login_required
def salvar_treino():
    """Salva um novo treino para o usuário atual"""
    codigo = request.form.get("id", "").strip().upper()
    nome = request.form.get("nome", codigo).strip()
    descricao = request.form.get("descricao", "").strip()

    if not codigo:
        flash("Código do treino é obrigatório.", "danger")
        return redirect(url_for("admin.gerenciar"))

    if TreinoService.get_by_codigo(codigo, user_id=current_user.id):
        flash(f"Treino {codigo} já existe!", "danger")
        return redirect(url_for("admin.gerenciar"))

    treino = TreinoService.create(codigo, nome, descricao, user_id=current_user.id)

    if treino:
        logger.info(f"Treino {codigo} criado pelo usuário {current_user.id} ({current_user.tipo_usuario})")
        flash(f"Treino {codigo} criado com sucesso!", "success")
    else:
        flash("Erro ao criar treino!", "danger")

    return redirect(url_for("admin.gerenciar"))


@admin_bp.route("/editar/treino", methods=["POST"])
@login_required
def editar_treino():
    """Edita um treino do usuário atual"""
    treino_id = request.form.get("id_original", "").strip()
    novo_codigo = request.form.get("id", "").strip().upper()
    novo_nome = request.form.get("nome", novo_codigo).strip()
    nova_descricao = request.form.get("descricao", "").strip()

    if not treino_id or not novo_codigo:
        flash("Dados inválidos para edição.", "danger")
        return redirect(url_for("admin.gerenciar"))

    # Confirma que o treino pertence ao usuário atual
    if not TreinoService.get_by_id(treino_id, user_id=current_user.id):
        flash("Treino não encontrado ou sem permissão.", "danger")
        return redirect(url_for("admin.gerenciar"))

    treino = TreinoService.update(treino_id, novo_codigo, novo_nome, nova_descricao, user_id=current_user.id)

    if treino:
        logger.info(f"Treino {treino_id} atualizado pelo usuário {current_user.id}")
        flash("Treino atualizado com sucesso!", "success")
    else:
        flash("Erro ao atualizar treino!", "danger")

    return redirect(url_for("admin.gerenciar"))


@admin_bp.route("/excluir/treino/<int:treino_id>", methods=["POST"])
@login_required
def excluir_treino(treino_id):
    """Exclui um treino do usuário atual"""
    if not TreinoService.get_by_id(treino_id, user_id=current_user.id):
        flash("Treino não encontrado ou sem permissão.", "danger")
        return redirect(url_for("admin.gerenciar"))

    if TreinoService.delete(treino_id, user_id=current_user.id):
        logger.info(f"Treino {treino_id} excluído pelo usuário {current_user.id}")
        flash("Treino excluído com sucesso!", "success")
    else:
        flash("Erro ao excluir treino!", "danger")

    return redirect(url_for("admin.gerenciar"))


# =============================================
# EXERCÍCIOS
# =============================================

@admin_bp.route("/salvar/exercicio", methods=["POST"])
@login_required
def salvar_exercicio():
    """Cria um novo exercício customizado para o usuário atual"""
    nome_exercicio = request.form.get("nome", "").strip()
    musculo = request.form.get("musculo", "").strip()
    treino_id = request.form.get("treino") or None
    descricao = request.form.get("descricao", "").strip()

    if not nome_exercicio:
        flash("Nome do exercício é obrigatório.", "danger")
        return redirect(url_for("admin.gerenciar"))

    # Resolver músculo automaticamente se não informado
    if not musculo:
        musculo_encontrado = buscar_musculo_no_catalogo(nome_exercicio)
        if musculo_encontrado:
            musculo = musculo_encontrado
            flash(f"Músculo '{musculo}' identificado automaticamente!", "info")
        else:
            musculo = "Outros"
            flash("Músculo não identificado, usando 'Outros'.", "warning")

    exercicio = ExercicioService.criar_exercicio_customizado(
        user_id=current_user.id,
        nome=nome_exercicio,
        musculo_nome=musculo,
        descricao=descricao,
        treino_id=treino_id
    )

    if exercicio:
        logger.info(f"Exercício '{nome_exercicio}' criado pelo usuário {current_user.id} ({current_user.tipo_usuario})")
        flash(f"Exercício '{nome_exercicio}' criado com sucesso!", "success")
    else:
        flash("Erro ao criar exercício!", "danger")

    return redirect(url_for("admin.gerenciar"))


@admin_bp.route("/editar/exercicio", methods=["POST"])
@login_required
def editar_exercicio():
    """Edita um exercício do usuário atual (customizado ou da base)"""
    exercicio_id = request.form.get("id", "").strip()
    nome_exercicio = request.form.get("nome", "").strip()
    musculo_nome = request.form.get("musculo", "").strip()
    treino_id = request.form.get("treino") or None
    descricao = request.form.get("descricao", "").strip()

    if not exercicio_id or not nome_exercicio:
        flash("Dados inválidos para edição.", "danger")
        return redirect(url_for("admin.gerenciar"))

    exercicio_id = int(exercicio_id)

    # Auto-detect músculo se não informado
    if not musculo_nome:
        musculo_encontrado = buscar_musculo_no_catalogo(nome_exercicio)
        if musculo_encontrado:
            musculo_nome = musculo_encontrado
            flash(f"Músculo atualizado para '{musculo_nome}'", "info")

    # Resolver/criar músculo no banco
    musculo_obj = None
    if musculo_nome:
        musculo_obj = Musculo.query.filter_by(nome_exibicao=musculo_nome).first()
        if not musculo_obj:
            musculo_obj = Musculo(nome=musculo_nome.lower(), nome_exibicao=musculo_nome)
            db.session.add(musculo_obj)
            db.session.flush()

    # Tenta como exercício customizado primeiro
    exercicio = ExercicioCustomizado.query.filter_by(
        id=exercicio_id, usuario_id=current_user.id
    ).first()

    if exercicio:
        exercicio.nome = nome_exercicio
        exercicio.descricao = descricao
        if musculo_obj:
            exercicio.musculo_id = musculo_obj.id
        db.session.commit()
        logger.info(f"Exercício customizado {exercicio_id} atualizado pelo usuário {current_user.id}")
        flash("Exercício atualizado com sucesso!", "success")
        return redirect(url_for("admin.gerenciar"))

    # Tenta como exercício da base (personalização)
    exercicio_usuario = ExercicioUsuario.query.filter_by(
        id=exercicio_id, usuario_id=current_user.id
    ).first()

    if exercicio_usuario:
        exercicio_usuario.nome_personalizado = nome_exercicio
        exercicio_usuario.descricao_personalizada = descricao
        if musculo_obj:
            exercicio_usuario.musculo_personalizado_id = musculo_obj.id
        db.session.commit()
        logger.info(f"Exercício usuário {exercicio_id} atualizado pelo usuário {current_user.id}")
        flash("Exercício atualizado com sucesso!", "success")
        return redirect(url_for("admin.gerenciar"))

    flash("Exercício não encontrado ou sem permissão.", "danger")
    return redirect(url_for("admin.gerenciar"))


@admin_bp.route("/excluir/exercicio/<int:exercicio_id>", methods=["POST"])
@login_required
def excluir_exercicio(exercicio_id):
    """Exclui um exercício do usuário atual"""
    # Tenta como customizado primeiro
    sucesso = ExercicioService.delete_exercicio_customizado(exercicio_id, user_id=current_user.id)

    # Tenta como ExercicioUsuario se necessário
    if not sucesso:
        sucesso = ExercicioService.delete_exercicio_usuario(exercicio_id, user_id=current_user.id)

    if sucesso:
        logger.info(f"Exercício {exercicio_id} excluído pelo usuário {current_user.id}")
        flash("Exercício excluído com sucesso!", "success")
    else:
        flash("Não foi possível excluir. O exercício pode estar em uso em uma versão de treino.", "danger")

    return redirect(url_for("admin.gerenciar"))


    @admin_bp.route("/exercicio/detalhes/<int:exercicio_id>")
    @login_required
    def exercicio_detalhes(exercicio_id):
        """Detalhes de um exercício - CORRIGIDO para suportar ambos os tipos"""
        
        # Tentar buscar primeiro como exercício do usuário
        exercicio_usuario = ExercicioUsuario.query.filter_by(
            id=exercicio_id, usuario_id=current_user.id
        ).first()
        
        if exercicio_usuario:
            exercicio = exercicio_usuario
            exercicio.tipo = 'usuario'
        else:
            # Tentar como exercício base
            exercicio = ExercicioBase.query.get(exercicio_id)
            if exercicio:
                exercicio.tipo = 'base'
        
        if not exercicio:
            flash("Exercício não encontrado!", "danger")
            return redirect(url_for("admin.gerenciar"))
        
        from utils.version_utils import verificar_exercicio_em_versoes
        
        # Passar o tipo para a função correta
        versoes = verificar_exercicio_em_versoes(exercicio_id, tipo_exercicio=exercicio.tipo)
    
        return render_template(
            "admin/exercicio_detalhes.html",
            exercicio=exercicio,
            versoes=versoes
        )


# =============================================
# APIS
# =============================================

@admin_bp.route("/api/verificar-treino")
@login_required
def api_verificar_treino():
    """Verifica se código de treino já existe para o usuário atual"""
    codigo = request.args.get("id", "").upper()
    treino = TreinoService.get_by_codigo(codigo, user_id=current_user.id)
    return jsonify({"existe": treino is not None})