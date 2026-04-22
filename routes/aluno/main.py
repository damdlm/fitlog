from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, User, AlunoProfessor, SolicitacaoVinculo, Treino, ExercicioCustomizado, VersaoGlobal, RegistroTreino
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    # Estatísticas básicas
    total_treinos = Treino.query.filter_by(user_id=current_user.id).count()
    total_exercicios = ExercicioCustomizado.query.filter_by(usuario_id=current_user.id).count()
    total_versoes = VersaoGlobal.query.filter_by(user_id=current_user.id).count()
    total_registros = RegistroTreino.query.filter_by(user_id=current_user.id).count()
    
    # Últimos registros
    ultimos_registros = RegistroTreino.query.filter_by(user_id=current_user.id)\
        .order_by(RegistroTreino.data_registro.desc())\
        .limit(5).all()
    
    return render_template('aluno/dashboard.html',
                         total_treinos=total_treinos,
                         total_exercicios=total_exercicios,
                         total_versoes=total_versoes,
                         total_registros=total_registros,
                         ultimos_registros=ultimos_registros)

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
    
    return render_template('aluno/buscar_professores.html', 
                         professores=professores,
                         termo=termo)

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
        aluno_id=current_user.id,
        professor_id=professor_id,
        status='pendente'
    ).first()
    
    if solicitacao_existente:
        flash('Você já possui uma solicitação pendente para este professor.', 'warning')
        return redirect(url_for('aluno.buscar_professores'))
    
    solicitacao = SolicitacaoVinculo(
        aluno_id=current_user.id,
        professor_id=professor_id,
        status='pendente',
        data_solicitacao=datetime.now(timezone.utc)
    )
    db.session.add(solicitacao)
    db.session.commit()
    
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
