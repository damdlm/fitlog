"""Página do mapa de professores, para o aluno buscar por região --
alternativa visual a /aluno/buscar-professores (busca por nome), que já
existe em routes/aluno/main.py. Acessível mesmo pra quem já tem um
professor vinculado (pode querer trocar ou conhecer outros).

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

    return render_template('aluno/mapa_professores.html')