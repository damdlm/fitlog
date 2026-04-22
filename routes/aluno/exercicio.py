from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, ExercicioCustomizado, RegistroTreino, HistoricoTreino, Treino
from services.exercicio_service import ExercicioService
from services.treino_service import TreinoService
from services.musculo_service import MusculoService
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/exercicios')
@login_required
def exercicios():
    """Lista os exercícios do aluno"""
    try:
        exercicios = ExercicioCustomizado.query \
            .filter_by(usuario_id=current_user.id) \
            .options(joinedload(ExercicioCustomizado.musculo_ref)) \
            .order_by(ExercicioCustomizado.nome) \
            .all()

        subq = db.session.query(
            RegistroTreino.exercicio_id,
            func.max(RegistroTreino.data_registro).label('max_data')
        ).filter_by(user_id=current_user.id).group_by(RegistroTreino.exercicio_id).subquery()

        cargas_query = db.session.query(
            RegistroTreino.exercicio_id,
            HistoricoTreino.carga
        ).join(
            subq,
            (RegistroTreino.exercicio_id == subq.c.exercicio_id) &
            (RegistroTreino.data_registro == subq.c.max_data)
        ).join(
            HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id
        ).filter(HistoricoTreino.ordem == 1).all()

        ultimas_cargas = {ex_id: float(carga) for ex_id, carga in cargas_query}
        treinos = Treino.query.filter_by(user_id=current_user.id).all()

        return render_template('aluno/exercicios.html',
                             exercicios=exercicios,
                             ultimas_cargas=ultimas_cargas,
                             treinos=treinos)
    except Exception as e:
        logger.error(f"Erro ao carregar exercícios: {e}")
        flash(f'Erro ao carregar exercícios.', 'danger')
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
        treino_id = request.form.get('treino') or None
        descricao = request.form.get('descricao', '')
        
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(url_for('aluno.novo_exercicio'))
        
        exercicio = ExercicioService.criar_exercicio_customizado(
            user_id=current_user.id,
            nome=nome,
            musculo_nome=musculo or 'Outros',
            descricao=descricao,
            treino_id=treino_id
        )
        
        if exercicio:
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
        
        musculo_obj = MusculoService.get_or_create(musculo)
        if hasattr(exercicio, 'is_custom') and exercicio.is_custom:
            exercicio_atualizado = ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=exercicio_id,
                user_id=current_user.id,
                nome=nome,
                descricao=descricao,
                musculo_id=musculo_obj.id if musculo_obj else None
            )
        else:
            exercicio_atualizado = ExercicioService.update_exercicio_usuario(
                exercicio_usuario_id=exercicio_id,
                user_id=current_user.id,
                nome_personalizado=nome,
                descricao_personalizada=descricao,
                musculo_personalizado_id=musculo_obj.id if musculo_obj else None
            )
        
        if exercicio_atualizado:
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
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('aluno.exercicios'))
