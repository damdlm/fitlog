"""Página do mapa de professores, para o aluno buscar por região --
alternativa visual a /aluno/buscar-professores (busca por nome), que já
existe em routes/aluno/main.py. Mesma regra de acesso daquela rota: só
faz sentido para quem ainda não tem professor vinculado.

Este módulo é importado em routes/aluno/__init__.py (mesmo padrão dos
demais arquivos da pasta -- main, exercicio, stats, ranking...) e
registrado no aluno_bp, então a rota final é /aluno/mapa.
"""
from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from . import aluno_bp


@aluno_bp.route('/mapa')
@login_required
def mapa_professores():
    """Mapa do Brasil com os professores visíveis por região. Os dados
    em si vêm de /api/professores/mapa (ver routes/api_routes.py),
    carregado via fetch conforme o aluno navega -- esta rota só
    renderiza a página. O pino de cada professor usa o mesmo endpoint
    aluno.enviar_solicitacao já usado em buscar_professores.html."""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    if current_user.get_professor():
        flash('Você já está vinculado a um professor.', 'info')
        return redirect(url_for('aluno.meu_professor'))

    return render_template('aluno/mapa_professores.html')
