from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.versao_service import VersaoService
from services.billing_service import BillingService
from services.monitoring_service import MonitoringService
from utils.exercise_utils import buscar_musculo_no_catalogo
from utils.decorators import admin_required
from models import db, ExercicioCustomizado, ExercicioUsuario, Musculo, RegistroTreino, HistoricoTreino, ExercicioSistema, TreinoVersao, VersaoExercicio, Plano
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
    exercicios_usuario = ExercicioUsuario.query.filter_by(
        usuario_id=current_user.id
    ).order_by(ExercicioUsuario.id).all()

    musculos = MusculoService.get_all_nomes()

    # Mapa exercicio_id -> treino_id, derivado da versão ativa do usuário
    # (ExercicioUsuario/ExercicioCustomizado não têm mais treino_id direto;
    # a associação exercício-treino agora vive em VersaoExercicio, por versão)
    exercicio_treino_map = {}
    versao_ativa = VersaoService.get_ativa(user_id=current_user.id)
    if versao_ativa:
        treinos_versao_ativa = TreinoVersao.query.filter_by(versao_id=versao_ativa.id).all()
        tv_id_para_treino_id = {tv.id: tv.treino_id for tv in treinos_versao_ativa}
        if tv_id_para_treino_id:
            versao_exercicios = VersaoExercicio.query.filter(
                VersaoExercicio.treino_versao_id.in_(tv_id_para_treino_id.keys())
            ).all()
            for ve in versao_exercicios:
                if ve.exercicio_usuario_id:
                    exercicio_treino_map[ve.exercicio_usuario_id] = tv_id_para_treino_id[ve.treino_versao_id]

    # Contagem de exercícios por treino (baseada na versão ativa)
    exercicios_por_treino = {}
    for ex in exercicios_custom:
        t_id = exercicio_treino_map.get(ex.id)
        if t_id:
            exercicios_por_treino[t_id] = exercicios_por_treino.get(t_id, 0) + 1

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
        exercicio_treino_map=exercicio_treino_map,
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
    # O template gerenciar_treinos.html chama essa rota via fetch() e
    # espera response.json() com {success, message} -- mas a rota sempre
    # fazia redirect() (resposta HTML), então response.json() sempre
    # lançava um erro de parse no JS e a edição parecia "não fazer nada"
    # silenciosamente. eh_ajax detecta isso pelo header que o próprio JS
    # já envia (X-Requested-With), e só nesse caso responde JSON -- mantém
    # o comportamento antigo (redirect + flash) para qualquer chamador
    # que não seja essa tela.
    eh_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def responder(sucesso, mensagem, categoria):
        if eh_ajax:
            return jsonify({"success": sucesso, "message": mensagem})
        flash(mensagem, categoria)
        return redirect(url_for("admin.gerenciar"))

    exercicio_id = request.form.get("id", "").strip()
    nome_exercicio = request.form.get("nome", "").strip()
    musculo_nome = request.form.get("musculo", "").strip()
    treino_id = request.form.get("treino") or None
    descricao = request.form.get("descricao", "").strip()

    if not exercicio_id or not nome_exercicio:
        return responder(False, "Dados inválidos para edição.", "danger")

    exercicio_id = int(exercicio_id)

    # Auto-detect músculo se não informado
    musculo_auto_detectado = None
    if not musculo_nome:
        musculo_encontrado = buscar_musculo_no_catalogo(nome_exercicio)
        if musculo_encontrado:
            musculo_nome = musculo_encontrado
            musculo_auto_detectado = musculo_nome
            if not eh_ajax:
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
        mensagem = "Exercício atualizado com sucesso!"
        if musculo_auto_detectado:
            mensagem += f" (músculo detectado automaticamente: {musculo_auto_detectado})"
        return responder(True, mensagem, "success")

    # Tenta como exercício da base (personalização)
    exercicio_usuario = ExercicioUsuario.query.filter_by(
        id=exercicio_id, usuario_id=current_user.id
    ).first()

    if exercicio_usuario:
        # BUG encontrado ao escrever teste para este fix: o código
        # gravava em .nome_personalizado/.descricao_personalizada, que
        # não existem no modelo ExercicioUsuario (ele só tem .nome,
        # .descricao, .musculo_id -- ver models.py). Como não são
        # colunas reais, o commit() não dava erro nenhum, só não salvava
        # nada: o usuário editava e a edição desaparecia silenciosamente.
        exercicio_usuario.nome = nome_exercicio
        exercicio_usuario.descricao = descricao
        if musculo_obj:
            exercicio_usuario.musculo_id = musculo_obj.id
        db.session.commit()
        logger.info(f"Exercício usuário {exercicio_id} atualizado pelo usuário {current_user.id}")
        mensagem = "Exercício atualizado com sucesso!"
        if musculo_auto_detectado:
            mensagem += f" (músculo detectado automaticamente: {musculo_auto_detectado})"
        return responder(True, mensagem, "success")

    return responder(False, "Exercício não encontrado ou sem permissão.", "danger")


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
    """Detalhes de um exercício"""
    
    exercicio = None
    # Buscar em ambas as tabelas
    exercicio_usuario = ExercicioUsuario.query.filter_by(
        id=exercicio_id, usuario_id=current_user.id
    ).first()
    
    if exercicio_usuario:
        exercicio = exercicio_usuario
        exercicio.tipo = 'usuario'
    else:
        exercicio_base = ExercicioSistema.query.get(exercicio_id)
        if exercicio_base:
            exercicio = exercicio_base
            exercicio.tipo = 'base'
    
    if not exercicio:
        flash("Exercício não encontrado!", "danger")
        return redirect(url_for("admin.gerenciar"))
    
    from utils.version_utils import verificar_exercicio_em_versoes
    versoes = verificar_exercicio_em_versoes(exercicio_id, tipo_exercicio=exercicio.tipo)

    return render_template(
        "admin/exercicios_detalhes.html",
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

# =============================================
# COBRANÇA -- painel de contas (só admin)
# =============================================

@admin_bp.route("/contas")
@admin_required
def contas():
    """Lista alunos e professores com a situação de cobrança calculada,
    com filtros por tipo de usuário, plano e situação (inclusive
    'inadimplente', que junta past_due/blocked/pendente num filtro só).
    Ver BillingService.listar_contas para a lógica de cálculo."""
    tipo_usuario = request.args.get("tipo", "").strip() or None
    busca = request.args.get("busca", "").strip() or None
    situacao_codigo = request.args.get("situacao", "").strip() or None
    plano_codigo = request.args.get("plano", "").strip() or None

    contas_lista = BillingService.listar_contas(
        tipo_usuario=tipo_usuario,
        busca=busca,
        situacao_codigo=situacao_codigo,
        plano_codigo=plano_codigo,
    )

    total_inadimplentes = sum(1 for c in contas_lista if c["inadimplente"])
    planos = Plano.query.filter_by(ativo=True).order_by(Plano.tipo_usuario, Plano.preco_centavos).all()

    return render_template(
        "admin/contas.html",
        contas=contas_lista,
        total_inadimplentes=total_inadimplentes,
        planos=planos,
        filtro_tipo=tipo_usuario or "",
        filtro_busca=busca or "",
        filtro_situacao=situacao_codigo or "",
        filtro_plano=plano_codigo or "",
    )


# =============================================
# MONITORAMENTO -- painel de saúde da aplicação (só admin)
# =============================================

@admin_bp.route("/monitoramento")
@admin_required
def monitoramento():
    """Painel de monitoramento: CPU/memória do processo, saúde do
    banco (Postgres), do cache (Redis) e indicadores rápidos de uso da
    aplicação. Renderiza com os dados já coletados na primeira carga;
    a partir daí, o próprio template atualiza via /admin/api/monitoramento
    (evita servir uma página em branco enquanto o JS carrega)."""
    metricas = MonitoringService.get_all_metrics()
    return render_template("admin/monitoramento.html", metricas=metricas)


@admin_bp.route("/api/monitoramento")
@admin_required
def api_monitoramento():
    """Mesmo conteúdo da página acima, em JSON -- usado pelo
    auto-refresh no front-end (ver static/js/admin-monitoramento.js)."""
    return jsonify(MonitoringService.get_all_metrics())