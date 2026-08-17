from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/treinos')
@login_required
def treinos():
    """Lista todos os treinos do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    # Antes: um ExercicioService.get_by_treino() por treino (N+1). Agora:
    # 1 chamada que busca tudo da versão ativa de uma vez e agrupa por
    # treino_id (ver VersaoService.get_exercicios_agrupados_por_treino).
    exercicios_agrupados = VersaoService.get_exercicios_agrupados_por_treino(user_id=current_user.id)
    exercicios_por_treino = {treino.id: exercicios_agrupados.get(treino.id, []) for treino in treinos}
    
    return render_template('aluno/treinos.html',
                         treinos=treinos,
                         exercicios_por_treino=exercicios_por_treino)

@aluno_bp.route('/treino/novo')
@login_required
def novo_treino():
    """
    Treinos agora só existem dentro de uma versão (ver aluno.novo_treino_versao),
    então esta rota não cadastra nada diretamente -- ela só direciona o aluno
    para o lugar certo: a versão ativa, se existir, ou a tela de criar uma
    versão nova, caso ele ainda não tenha nenhuma.
    """
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    versao_ativa = VersaoService.get_ativa(user_id=current_user.id)
    if versao_ativa:
        return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_ativa.id))
    
    flash('Você ainda não tem uma versão de treino. Crie uma versão primeiro.', 'info')
    return redirect(url_for('aluno.nova_versao'))

@aluno_bp.route('/treino/<int:treino_id>', methods=['GET', 'POST'])
@login_required
def editar_treino(treino_id):
    """Edita um treino do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
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

@aluno_bp.route('/treino/<int:treino_id>/excluir', methods=['POST'])
@login_required
def excluir_treino(treino_id):
    """Exclui um treino do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
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