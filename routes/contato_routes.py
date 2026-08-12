"""Rotas da tela "Contato" -- reportar erro, crítica ou elogio para o
administrador do sistema, com opção de gravar áudio (transcrito
automaticamente) além de digitar.
"""

import logging

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import limiter
from services.contato_service import ContatoService

contato_bp = Blueprint("contato", __name__)
logger = logging.getLogger(__name__)

# Tamanho máximo aceito para o upload do áudio (ver também
# ContatoService.MAX_AUDIO_BYTES -- essa trava aqui é só para rejeitar
# cedo, antes de gastar tempo processando o arquivo).
MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _chave_por_usuario():
    return f"contato-{current_user.id}"


@contato_bp.route("/", methods=["GET"])
@login_required
def index():
    """Exibe a tela de Contato."""
    return render_template("contato.html")


@contato_bp.route("/transcrever", methods=["POST"])
@login_required
@limiter.limit("10 per minute", key_func=_chave_por_usuario)
def transcrever():
    """
    Recebe um arquivo de áudio (multipart/form-data, campo "audio") e
    devolve a transcrição via Groq Whisper.
    """
    arquivo = request.files.get("audio")
    if not arquivo:
        return jsonify({"ok": False, "texto": "Nenhum áudio recebido."}), 400

    resultado = ContatoService.transcrever_audio(arquivo)
    status = 200 if resultado.get("ok") else 503
    return jsonify(resultado), status


@contato_bp.route("/enviar", methods=["POST"])
@login_required
@limiter.limit("5 per hour", key_func=_chave_por_usuario)
def enviar():
    """Envia a mensagem de contato (texto digitado ou transcrito) por e-mail."""
    dados = request.get_json(silent=True) or {}
    mensagem = (dados.get("mensagem") or "").strip()

    resultado = ContatoService.enviar_mensagem(current_user, mensagem)
    status = 200 if resultado.get("ok") else 400
    return jsonify(resultado), status
