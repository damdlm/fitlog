from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
import logging

logger = logging.getLogger(__name__)

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
    
    return render_template('aluno/treinos.html',
                         treinos=treinos,
                         exercicios_por_treino=exercicios_por_treino)

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
        
        treino_atualizado = TreinoService.update(
            treino_id,
            codigo=novo_codigo,
            nome=nome,
            descricao=descricao,
            user_id=current_user.id
        )
        if treino_atualizado:
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
        flash(f'Treino {treino.codigo} excluído!', 'success')
    else:
        flash('Erro ao excluir treino!', 'danger')
    
    return redirect(url_for('aluno.treinos'))
