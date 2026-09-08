"""Rotas de notificações in-app entre aluno e professor.

Sem push (ver models.Notificacao) -- a tela e o sininho do navbar leem
daqui via polling (ver static/js/modules/notificacoes.js).
"""

import logging

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from extensions import limiter
from services.notificacao_service import NotificacaoService
from utils.format_utils import FUSO_BRASIL

notificacao_bp = Blueprint('notificacao', __name__)
logger = logging.getLogger(__name__)


def _chave_por_usuario():
    return f"notificacoes-{current_user.id}"


def _data_formatada(dt):
    if not dt:
        return ''
    return dt.astimezone(FUSO_BRASIL).strftime('%d/%m/%Y às %H:%M')


@notificacao_bp.route('/notificacoes')
@login_required
def listar():
    """Página com o histórico completo de notificações do usuário."""
    notificacoes = NotificacaoService.listar(current_user.id, limit=100)
    return render_template(
        'notificacoes/lista.html',
        notificacoes=notificacoes,
        data_formatada=_data_formatada,
    )


@notificacao_bp.route('/api/notificacoes')
@login_required
@limiter.limit("120 per hour", key_func=_chave_por_usuario)
def api_listar():
    """Usado pelo sininho: contagem de não lidas + as mais recentes,
    consultado por polling (ver notificacoes.js)."""
    notificacoes = NotificacaoService.listar(current_user.id, limit=8)
    return jsonify({
        "nao_lidas": NotificacaoService.contar_nao_lidas(current_user.id),
        "notificacoes": [
            {
                "id": n.id,
                "tipo": n.tipo,
                "titulo": n.titulo,
                "mensagem": n.mensagem,
                "url": n.url,
                "lida": n.lida,
                "created_at": _data_formatada(n.created_at),
            }
            for n in notificacoes
        ],
    })


@notificacao_bp.route('/api/notificacoes/<int:notificacao_id>/marcar-lida', methods=['POST'])
@login_required
@limiter.limit("120 per hour", key_func=_chave_por_usuario)
def api_marcar_lida(notificacao_id):
    sucesso = NotificacaoService.marcar_como_lida(notificacao_id, current_user.id)
    if not sucesso:
        return jsonify({"success": False}), 404
    return jsonify({"success": True})


@notificacao_bp.route('/api/notificacoes/marcar-todas-lidas', methods=['POST'])
@login_required
@limiter.limit("30 per hour", key_func=_chave_por_usuario)
def api_marcar_todas_lidas():
    NotificacaoService.marcar_todas_como_lidas(current_user.id)
    return jsonify({"success": True})
