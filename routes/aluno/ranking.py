from flask import render_template
from flask_login import login_required, current_user
from . import aluno_bp
from services.ranking_service import RankingService, TOP_N
from utils.decorators import acesso_premium_required
import logging

logger = logging.getLogger(__name__)


@aluno_bp.route('/ranking')
@login_required
@acesso_premium_required('ranking')
def ranking():
    """Tela "Melhores Alunos" -- ranking geral dos últimos 30 dias."""
    top5 = RankingService.top_n(TOP_N)

    minha_posicao = RankingService.posicao_do_usuario(current_user.id)
    # Só mostra o card "sua posição" separado quando o usuário está fora
    # do top exibido -- dentro do top5 ele já aparece na lista principal,
    # repetir seria redundante.
    mostrar_minha_posicao_separada = (
        minha_posicao is not None and minha_posicao['posicao'] > len(top5)
    )

    return render_template(
        'aluno/ranking.html',
        ranking=top5,
        minha_posicao=minha_posicao,
        mostrar_minha_posicao_separada=mostrar_minha_posicao_separada,
        participa_do_ranking=current_user.aparecer_no_ranking,
    )
