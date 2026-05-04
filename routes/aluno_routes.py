from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, AlunoProfessor, SolicitacaoVinculo, Treino, ExercicioCustomizado, Musculo, VersaoGlobal, RegistroTreino, TreinoVersao, HistoricoTreino
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload
from sqlalchemy import func, and_
import logging

# Services
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
from services.musculo_service import MusculoService

aluno_bp = Blueprint('aluno', __name__, url_prefix='/aluno')
logger = logging.getLogger(__name__)


# =============================================
# DASHBOARD DO ALUNO
# =============================================

@aluno_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    total_treinos = Treino.query.filter_by(user_id=current_user.id).count()
    total_exercicios = ExercicioCustomizado.query.filter_by(usuario_id=current_user.id).count()
    total_versoes = VersaoGlobal.query.filter_by(user_id=current_user.id).count()
    total_registros = RegistroTreino.query.filter_by(user_id=current_user.id).count()
    
    ultimos_registros = RegistroTreino.query.filter_by(user_id=current_user.id)\
        .order_by(RegistroTreino.data_registro.desc()).limit(5).all()
    
    return render_template('aluno/dashboard.html',
                         total_treinos=total_treinos,
                         total_exercicios=total_exercicios,
                         total_versoes=total_versoes,
                         total_registros=total_registros,
                         ultimos_registros=ultimos_registros)


# =============================================
# GERENCIAMENTO DE PROFESSOR
# =============================================

@aluno_bp.route('/meu-professor')
@login_required
def meu_professor():
    """Visualiza informações do professor vinculado"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    professor = current_user.get_professor()
    return render_template('aluno/meu_professor.html', professor=professor)


@aluno_bp.route('/buscar-professores')
@login_required
def buscar_professores():
    """Página para buscar professores disponíveis"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.get_professor():
        flash('Você já está vinculado a um professor.', 'info')
        return redirect(url_for('aluno.meu_professor'))
    
    termo = request.args.get('busca', '')
    professores = []
    if termo:
        professores = User.query.filter(
            User.tipo_usuario == 'professor',
            User.ativo == True,
            (User.nome_completo.ilike(f'%{termo}%') | User.username.ilike(f'%{termo}%'))
        ).all()
    
    return render_template('aluno/buscar_professores.html', professores=professores, termo=termo)


@aluno_bp.route('/enviar-solicitacao/<int:professor_id>', methods=['POST'])
@login_required
def enviar_solicitacao(professor_id):
    """Envia solicitação de vínculo para um professor"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.get_professor():
        flash('Você já tem um professor.', 'warning')
        return redirect(url_for('aluno.meu_professor'))
    
    professor = User.query.get_or_404(professor_id)
    if professor.tipo_usuario != 'professor':
        flash('Usuário não é um professor válido.', 'danger')
        return redirect(url_for('aluno.buscar_professores'))
    
    solicitacao_existente = SolicitacaoVinculo.query.filter_by(
        aluno_id=current_user.id, professor_id=professor_id, status='pendente'
    ).first()
    
    if solicitacao_existente:
        flash('Você já possui uma solicitação pendente para este professor.', 'warning')
        return redirect(url_for('aluno.buscar_professores'))
    
    solicitacao = SolicitacaoVinculo(
        aluno_id=current_user.id, professor_id=professor_id,
        status='pendente', data_solicitacao=datetime.now(timezone.utc)
    )
    db.session.add(solicitacao)
    db.session.commit()
    
    logger.info(f"Aluno {current_user.id} enviou solicitação para professor {professor_id}")
    flash(f'Solicitação enviada para {professor.nome_completo or professor.username}!', 'success')
    return redirect(url_for('aluno.meu_professor'))


@aluno_bp.route('/remover-vinculo', methods=['POST'])
@login_required
def remover_vinculo():
    """Remove vínculo com o professor atual"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    professor = current_user.get_professor()
    if not professor:
        flash('Você não está vinculado a nenhum professor.', 'warning')
        return redirect(url_for('aluno.meu_professor'))
    
    assoc = AlunoProfessor.query.filter_by(aluno_id=current_user.id, ativo=True).first()
    if assoc:
        assoc.ativo = False
        db.session.commit()
        flash(f'Vínculo com {professor.nome_completo or professor.username} removido com sucesso!', 'success')
    
    return redirect(url_for('aluno.meu_professor'))


# =============================================
# GERENCIAMENTO DE TREINOS DO ALUNO
# =============================================

@aluno_bp.route('/treinos')
@login_required
def treinos():
    """Lista todos os treinos do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    exercicios_por_treino = {}
    for treino in treinos:
        exercicios_por_treino[treino.id] = ExercicioService.get_by_treino(treino.id, user_id=current_user.id)
    
    return render_template('aluno/treinos.html', treinos=treinos, exercicios_por_treino=exercicios_por_treino)


@aluno_bp.route('/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino():
    """Cria um novo treino para o aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        if not codigo or not codigo.isalpha() or len(codigo) != 1:
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(url_for('aluno.novo_treino'))
        
        existente = TreinoService.get_by_codigo(codigo, user_id=current_user.id)
        if existente:
            flash(f'Treino {codigo} já existe!', 'danger')
            return redirect(url_for('aluno.novo_treino'))
        
        treino = TreinoService.create(codigo, nome, descricao, user_id=current_user.id)
        if treino:
            logger.info(f"Aluno {current_user.id} criou treino {treino.id}")
            flash(f'Treino {codigo} criado com sucesso!', 'success')
            return redirect(url_for('aluno.treinos'))
        else:
            flash('Erro ao criar treino!', 'danger')
    
    return render_template('aluno/novo_treino.html')


@aluno_bp.route('/treino/<int:treino_id>', methods=['GET', 'POST'])
@login_required
def editar_treino(treino_id):
    """Edita um treino do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('aluno.treinos'))
    
    if request.method == 'POST':
        novo_codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        treino_atualizado = TreinoService.update(treino_id, codigo=novo_codigo, nome=nome, descricao=descricao, user_id=current_user.id)
        if treino_atualizado:
            logger.info(f"Aluno {current_user.id} editou treino {treino_id}")
            flash('Treino atualizado!', 'success')
            return redirect(url_for('aluno.treinos'))
        else:
            flash('Erro ao atualizar treino!', 'danger')
    
    return render_template('aluno/editar_treino.html', treino=treino)


@aluno_bp.route('/treino/<int:treino_id>/excluir')
@login_required
def excluir_treino(treino_id):
    """Exclui um treino do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('aluno.treinos'))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão do treino {treino.codigo}.', 'warning')
        return redirect(url_for('aluno.treinos'))
    
    if TreinoService.delete(treino_id, user_id=current_user.id):
        logger.info(f"Aluno {current_user.id} excluiu treino {treino_id}")
        flash(f'Treino {treino.codigo} excluído!', 'success')
    else:
        flash('Erro ao excluir treino!', 'danger')
    
    return redirect(url_for('aluno.treinos'))


# =============================================
# GERENCIAMENTO DE EXERCÍCIOS DO ALUNO
# =============================================

@aluno_bp.route('/exercicios')
@login_required
def exercicios():
    """Lista os exercícios do aluno"""
    try:
        exercicios = ExercicioCustomizado.query \
            .filter_by(usuario_id=current_user.id) \
            .options(joinedload(ExercicioCustomizado.musculo_ref)) \
            .order_by(ExercicioCustomizado.nome).all()

        subq = db.session.query(
            RegistroTreino.exercicio_id,
            func.max(RegistroTreino.data_registro).label('max_data')
        ).filter_by(user_id=current_user.id).group_by(RegistroTreino.exercicio_id).subquery()

        cargas_query = db.session.query(
            RegistroTreino.exercicio_id,
            HistoricoTreino.carga
        ).join(subq, (RegistroTreino.exercicio_id == subq.c.exercicio_id) & 
                      (RegistroTreino.data_registro == subq.c.max_data))\
         .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
         .filter(HistoricoTreino.ordem == 1).all()

        ultimas_cargas = {ex_id: float(carga) for ex_id, carga in cargas_query}
        treinos = Treino.query.filter_by(user_id=current_user.id).all()

        return render_template('aluno/exercicios.html', exercicios=exercicios,
                             ultimas_cargas=ultimas_cargas, treinos=treinos)
    except Exception as e:
        flash(f'Erro ao carregar exercícios: {str(e)}', 'danger')
        return redirect(url_for('aluno.dashboard'))


@aluno_bp.route('/exercicio/novo', methods=['GET', 'POST'])
@login_required
def novo_exercicio():
    """Cria um novo exercício para o aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(url_for('aluno.novo_exercicio'))
        
        exercicio = ExercicioService.criar_exercicio_customizado(
            user_id=current_user.id, nome=nome,
            musculo_nome=musculo or 'Outros', descricao=descricao
        )
        if exercicio:
            logger.info(f"Aluno {current_user.id} criou exercício {exercicio.id}")
            flash(f'Exercício {nome} criado com sucesso!', 'success')
            return redirect(url_for('aluno.exercicios'))
        else:
            flash('Erro ao criar exercício!', 'danger')
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    musculos = MusculoService.get_all_nomes()
    return render_template('aluno/novo_exercicio.html', treinos=treinos, musculos=musculos)


@aluno_bp.route('/exercicio/<int:exercicio_id>', methods=['GET', 'POST'])
@login_required
def editar_exercicio(exercicio_id):
    """Edita um exercício do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=current_user.id, load_relations=True)
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('aluno.exercicios'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        if hasattr(exercicio, 'is_custom') and exercicio.is_custom:
            musculo_obj = MusculoService.get_or_create(musculo)
            exercicio_atualizado = ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=exercicio_id, user_id=current_user.id,
                nome=nome, descricao=descricao,
                musculo_id=musculo_obj.id if musculo_obj else None
            )
        else:
            musculo_obj = MusculoService.get_or_create(musculo)
            exercicio_atualizado = ExercicioService.update_exercicio_usuario(
                exercicio_usuario_id=exercicio_id, user_id=current_user.id,
                nome_personalizado=nome, descricao_personalizada=descricao,
                musculo_personalizado_id=musculo_obj.id if musculo_obj else None
            )
        
        if exercicio_atualizado:
            logger.info(f"Aluno {current_user.id} editou exercício {exercicio_id}")
            flash('Exercício atualizado!', 'success')
            return redirect(url_for('aluno.exercicios'))
        else:
            flash('Erro ao atualizar exercício!', 'danger')
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    musculos = MusculoService.get_all_nomes()
    return render_template('aluno/editar_exercicio.html', exercicio=exercicio, treinos=treinos, musculos=musculos)


@aluno_bp.route('/exercicio/<int:exercicio_id>/excluir')
@login_required
def excluir_exercicio(exercicio_id):
    """Exclui um exercício do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=current_user.id)
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('aluno.exercicios'))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão de "{exercicio.nome}".', 'warning')
        return redirect(url_for('aluno.exercicios'))
    
    if hasattr(exercicio, 'is_custom') and exercicio.is_custom:
        sucesso = ExercicioService.delete_exercicio_customizado(exercicio_id, user_id=current_user.id)
    else:
        sucesso = ExercicioService.delete_exercicio_usuario(exercicio_id, user_id=current_user.id)
    
    if sucesso:
        logger.info(f"Aluno {current_user.id} excluiu exercício {exercicio_id}")
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('aluno.exercicios'))


# =============================================
# GERENCIAMENTO DE VERSÕES DO ALUNO
# =============================================

@aluno_bp.route('/versoes')
@login_required
def versoes():
    """Lista todas as versões do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versoes = VersaoService.get_all(user_id=current_user.id)
    return render_template('aluno/versoes.html', versoes=versoes)


@aluno_bp.route('/versao/nova', methods=['GET', 'POST'])
@login_required
def nova_versao():
    """Cria uma nova versão para o aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        divisao = request.form.get('divisao', 'ABC')
        data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim = datetime.strptime(request.form.get('data_fim'), '%Y-%m-%d').date() if request.form.get('data_fim') else None
        
        versao_atual = VersaoService.get_ativa(user_id=current_user.id)
        if versao_atual and not data_fim:
            versao_atual.data_fim = data_inicio
            db.session.add(versao_atual)
        
        nova_versao = VersaoService.create(descricao=descricao, data_inicio=data_inicio, divisao=divisao, data_fim=data_fim, user_id=current_user.id)
        if nova_versao:
            logger.info(f"Aluno {current_user.id} criou versão {nova_versao.id}")
            flash('Versão criada com sucesso!', 'success')
            return redirect(url_for('aluno.versoes'))
        else:
            flash('Erro ao criar versão!', 'danger')
    
    return render_template('aluno/nova_versao.html')


@aluno_bp.route('/versao/<int:versao_id>', methods=['GET', 'POST'])
@login_required
def ver_versao(versao_id):
    """Visualiza e edita uma versão específica do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    if request.method == 'POST':
        versao.descricao = request.form.get('descricao')
        nova_divisao = request.form.get('divisao')
        if nova_divisao in ['ABC', 'ABCD', 'ABCDE']:
            versao.divisao = nova_divisao
        versao.data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim = request.form.get('data_fim')
        versao.data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date() if data_fim else None
        db.session.commit()
        flash('Versão atualizada!', 'success')
        return redirect(url_for('aluno.ver_versao', versao_id=versao.id))
    
    treinos_dict = VersaoService.get_treinos(versao.id, user_id=current_user.id)
    exercicios = ExercicioService.get_exercicios_completos(user_id=current_user.id)
    treinos_disponiveis = TreinoService.get_all(user_id=current_user.id)
    
    return render_template('aluno/ver_versao.html', versao=versao, treinos=treinos_dict, exercicios=exercicios, treinos_disponiveis=treinos_disponiveis)


@aluno_bp.route('/versao/<int:versao_id>/finalizar')
@login_required
def finalizar_versao(versao_id):
    """Finaliza uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    if versao.data_fim:
        flash('Versão já finalizada!', 'warning')
        return redirect(url_for('aluno.versoes'))
    
    if VersaoService.finalizar(versao_id, datetime.now().date(), user_id=current_user.id):
        logger.info(f"Aluno {current_user.id} finalizou versão {versao_id}")
        flash('Versão finalizada!', 'success')
    else:
        flash('Erro ao finalizar versão!', 'danger')
    return redirect(url_for('aluno.versoes'))


@aluno_bp.route('/versao/<int:versao_id>/clonar')
@login_required
def clonar_versao(versao_id):
    """Clona uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    if VersaoService.clone(versao_id, user_id=current_user.id):
        logger.info(f"Aluno {current_user.id} clonou versão {versao_id}")
        flash('Versão clonada com sucesso!', 'success')
    else:
        flash('Erro ao clonar versão!', 'danger')
    return redirect(url_for('aluno.versoes'))


@aluno_bp.route('/versao/<int:versao_id>/excluir')
@login_required
def excluir_versao(versao_id):
    """Exclui uma versão do aluno (se não tiver registros)"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    versao_ativa = VersaoService.get_ativa(user_id=current_user.id)
    if versao_ativa and versao_ativa.id == versao_id:
        flash('Não é possível excluir a versão ativa. Finalize-a primeiro.', 'warning')
        return redirect(url_for('aluno.versoes'))
    
    registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=current_user.id).first()
    if registros:
        flash('Não é possível excluir esta versão pois existem registros vinculados.', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash('⚠️ Clique novamente para confirmar a exclusão.', 'warning')
        return redirect(url_for('aluno.versoes'))
    
    if VersaoService.delete(versao_id, user_id=current_user.id):
        logger.info(f"Aluno {current_user.id} excluiu versão {versao_id}")
        flash('Versão excluída com sucesso!', 'success')
    else:
        flash('Erro ao excluir versão!', 'danger')
    return redirect(url_for('aluno.versoes'))


@aluno_bp.route('/versao/<int:versao_id>/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino_versao(versao_id):
    """Adiciona um treino existente a uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    if request.method == 'POST':
        treino_id = request.form.get('treino_id')
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        
        if not treino_id or not nome_treino:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_id))
        
        treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
        if not treino:
            flash('Treino não encontrado!', 'danger')
            return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_id))
        
        existe = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        if existe:
            flash(f'Treino {treino.codigo} já existe nesta versão!', 'warning')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        
        exercicios = ExercicioService.get_by_treino(treino.id, user_id=current_user.id)
        usuarios_ids = [ex.id for ex in exercicios]
        
        try:
            treino_versao = TreinoVersao(
                versao_id=versao_id, treino_id=treino.id,
                nome_treino=nome_treino, descricao_treino=descricao_treino,
                ordem=len(versao.treinos)
            )
            db.session.add(treino_versao)
            db.session.flush()
            
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, usuarios_ids, [])
            db.session.commit()
            
            logger.info(f"Aluno {current_user.id} adicionou treino {treino.codigo} à versão {versao_id}")
            flash(f'Treino {treino.codigo} adicionado à versão!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar treino à versão: {str(e)}")
            flash(f'Erro ao adicionar treino: {str(e)}', 'danger')
    
    treinos_disponiveis = TreinoService.get_all(user_id=current_user.id)
    treinos_na_versao = [tv.treino_id for tv in versao.treinos]
    treinos_livres = [t for t in treinos_disponiveis if t.id not in treinos_na_versao]
    return render_template('aluno/novo_treino_versao.html', versao=versao, treinos=treinos_livres)


# =============================================
# EDITAR TREINO NA VERSÃO
# =============================================

@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao(versao_id, treino_codigo):
    """Edita um treino específico dentro de uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    
    if request.method == 'POST':
        nome_treino = request.form.get('nome_treino', '').strip()
        descricao_treino = request.form.get('descricao_treino', '').strip()
        exercicios_raw = request.form.getlist('exercicios[]')
        
        usuarios_ids, bases_ids = VersaoService.processar_exercicios_formulario(exercicios_raw, current_user.id)
        
        if not usuarios_ids and not bases_ids:
            flash('Selecione pelo menos um exercício válido!', 'danger')
            return redirect(request.url)
        
        treino_versao.nome_treino = nome_treino
        treino_versao.descricao_treino = descricao_treino
        
        try:
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, usuarios_ids, bases_ids)
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado com sucesso!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao salvar: {str(e)}")
            flash(f'Erro ao atualizar treino: {str(e)}', 'danger')
            return redirect(request.url)
    
    exercicios_display, exercicios_atuais = VersaoService.get_exercicios_para_edicao(current_user.id, treino_versao)
    musculos = MusculoService.get_all_nomes()
    
    return render_template('aluno/editar_treino_versao.html',
                         versao=versao, treino_id=treino_codigo,
                         treino={"nome": treino_versao.nome_treino, "descricao": treino_versao.descricao_treino, "exercicios": exercicios_atuais},
                         exercicios=exercicios_display, musculos=musculos)


@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir')
@login_required
def excluir_treino_versao(versao_id, treino_codigo):
    """Remove um treino de uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    
    resultado = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino_ref.id).delete()
    if resultado:
        db.session.commit()
        logger.info(f"Aluno {current_user.id} removeu treino {treino_codigo} da versão {versao_id}")
        flash(f'Treino {treino_codigo} removido da versão!', 'success')
    else:
        flash(f'Erro ao remover treino {treino_codigo}!', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


# =============================================
# ESTATÍSTICAS DO ALUNO
# =============================================

@aluno_bp.route('/estatisticas')
@login_required
def estatisticas():
    """Estatísticas detalhadas do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    musculo_stats_raw = db.session.query(
        Musculo.nome_exibicao.label('musculo'),
        func.count(func.distinct(ExercicioCustomizado.id)).label('qtd_exercicios'),
        func.count(func.distinct(RegistroTreino.id)).label('qtd_registros'),
        func.count(HistoricoTreino.id).label('total_series'),
        func.coalesce(func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
    ).select_from(Musculo)\
     .outerjoin(ExercicioCustomizado, and_(ExercicioCustomizado.musculo_id == Musculo.id, ExercicioCustomizado.usuario_id == current_user.id))\
     .outerjoin(RegistroTreino, and_(RegistroTreino.exercicio_id == ExercicioCustomizado.id, RegistroTreino.user_id == current_user.id))\
     .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
     .group_by(Musculo.id, Musculo.nome_exibicao).all()
    
    musculo_stats = {}
    for r in musculo_stats_raw:
        musculo_stats[r.musculo] = {
            'qtd_exercicios': r.qtd_exercicios,
            'qtd_registros': r.qtd_registros,
            'total_series': r.total_series,
            'volume_total': float(r.volume_total)
        }
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    registros = RegistroTreino.query.filter_by(user_id=current_user.id).all()
    treino_stats = {}
    for t in treinos:
        registros_treino = [r for r in registros if r.treino_id == t.id]
        volume_total = sum(float(s.carga) * s.repeticoes for r in registros_treino for s in r.series)
        total_series = sum(1 for r in registros_treino for _ in r.series)
        exercicios_ids = {r.exercicio_id for r in registros_treino}
        treino_stats[t.id] = {
            "codigo": t.codigo, "nome": t.nome, "descricao": t.descricao,
            "qtd_exercicios": len(exercicios_ids), "qtd_registros": len(registros_treino),
            "volume_total": volume_total, "total_series": total_series
        }
    
    return render_template('aluno/estatisticas.html', musculo_stats=musculo_stats, treino_stats=treino_stats)


@aluno_bp.route('/calendario')
@login_required
def calendario():
    """Redireciona para o calendário do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    return redirect(url_for('calendar.calendario'))


@aluno_bp.route('/api/buscar-professores')
@login_required
def api_buscar_professores():
    """API para buscar professores (usado em selects)"""
    termo = request.args.get('termo', '').lower()
    query = User.query.filter_by(tipo_usuario='professor', ativo=True)
    if termo:
        query = query.filter((User.nome_completo.ilike(f'%{termo}%')) | (User.username.ilike(f'%{termo}%')) | (User.email.ilike(f'%{termo}%')))
    professores = query.limit(20).all()
    return jsonify([{'id': p.id, 'nome': p.nome_completo or p.username, 'username': p.username, 'email': p.email} for p in professores])