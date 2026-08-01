from flask import render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import User, RegistroTreino
from services.treino_service import TreinoService
from services.estatistica_service import EstatisticaService
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/estatisticas')
@login_required
def estatisticas():
    """Estatísticas detalhadas do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    musculo_stats = EstatisticaService.calcular_por_musculo(user_id=current_user.id)
    
    treinos = TreinoService.get_all(user_id=current_user.id)
    registros = RegistroTreino.query.filter_by(user_id=current_user.id).all()
    treino_stats = {t.id: {
        "codigo": t.codigo, "nome": t.nome, "descricao": t.descricao,
        "qtd_exercicios": len(set(r.exercicio_id for r in registros if r.treino_id == t.id)),
        "qtd_registros": len([r for r in registros if r.treino_id == t.id]),
        "volume_total": sum(float(s.carga) * s.repeticoes for r in registros if r.treino_id == t.id for s in r.series),
        "total_series": sum(1 for r in registros if r.treino_id == t.id for s in r.series)
    } for t in treinos}

    # Músculo com maior volume total -- usado no destaque do cabeçalho
    musculo_destaque = None
    if musculo_stats:
        musculos_com_volume = {k: v for k, v in musculo_stats.items() if v['volume_total'] > 0}
        if musculos_com_volume:
            musculo_destaque = max(musculos_com_volume, key=lambda k: musculos_com_volume[k]['volume_total'])

    volume_maximo_musculo = max((v['volume_total'] for v in musculo_stats.values()), default=0)
    
    return render_template('aluno/estatisticas.html',
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats,
                         musculo_destaque=musculo_destaque,
                         volume_maximo_musculo=volume_maximo_musculo)

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