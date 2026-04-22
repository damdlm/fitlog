from flask import render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, User, Musculo, ExercicioCustomizado, RegistroTreino, HistoricoTreino
from services.treino_service import TreinoService
from sqlalchemy import func, and_
import logging

logger = logging.getLogger(__name__)

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
     .group_by(Musculo.id, Musculo.nome_exibicao)\
     .all()
    
    musculo_stats = {r.musculo: {
        'qtd_exercicios': r.qtd_exercicios,
        'qtd_registros': r.qtd_registros,
        'total_series': r.total_series,
        'volume_total': float(r.volume_total)
    } for r in musculo_stats_raw}
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    registros = RegistroTreino.query.filter_by(user_id=current_user.id).all()
    treino_stats = {t.id: {
        "codigo": t.codigo, "nome": t.nome, "descricao": t.descricao,
        "qtd_exercicios": len(set(r.exercicio_id for r in registros if r.treino_id == t.id)),
        "qtd_registros": len([r for r in registros if r.treino_id == t.id]),
        "volume_total": sum(float(s.carga) * s.repeticoes for r in registros if r.treino_id == t.id for s in r.series),
        "total_series": sum(1 for r in registros if r.treino_id == t.id for s in r.series)
    } for t in treinos}
    
    return render_template('aluno/estatisticas.html', musculo_stats=musculo_stats, treino_stats=treino_stats)

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
