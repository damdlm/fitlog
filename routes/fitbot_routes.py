"""Rotas do FitBot — assistente virtual de treino (chat com IA)"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required

from extensions import limiter
from services.fitbot_service import FitBotService

fitbot_bp = Blueprint("fitbot", __name__)
logger = logging.getLogger(__name__)

# Tamanho máximo aceito para a imagem em base64 (~1.5 MB).
# A imagem já chega comprimida (~800x800) do front-end; isso aqui é
# só uma trava de segurança contra payloads fora do esperado.
MAX_IMAGEM_BASE64_CHARS = 2_000_000

# O Gemini free só libera 15 requisições por minuto NO TOTAL da chave
# de API — ou seja, dividido entre todos os usuários do app ao mesmo
# tempo. Por isso o limite abaixo é aplicado de forma GLOBAL (mesma
# chave para todo mundo), não por usuário/IP, para nunca estourar a
# cota gratuita mesmo com vários alunos usando o FitBot ao mesmo tempo.
def _chave_global_fitbot():
    return "fitbot-chat-global"


@fitbot_bp.route("/chat", methods=["POST"])
@login_required
@limiter.limit("12 per minute", key_func=_chave_global_fitbot)
def chat():
    """
    Recebe uma mensagem (e opcionalmente uma foto em base64) e devolve
    a resposta do FitBot.

    Body JSON esperado:
        {
            "mensagem": "texto digitado pelo usuário",
            "imagem_base64": "opcional, já comprimida pelo front-end",
            "historico": [{"papel": "usuario"|"bot", "texto": "..."}]
        }
    """
    dados = request.get_json(silent=True) or {}

    mensagem = (dados.get("mensagem") or "").strip()
    imagem_base64 = dados.get("imagem_base64")
    historico = dados.get("historico") or []

    if not mensagem and not imagem_base64:
        return jsonify({"ok": False, "resposta": "Digite uma pergunta ou envie uma foto do equipamento."}), 400

    if len(mensagem) > 1000:
        return jsonify({"ok": False, "resposta": "Mensagem muito longa. Tenta resumir sua dúvida."}), 400

    if imagem_base64 and len(imagem_base64) > MAX_IMAGEM_BASE64_CHARS:
        return jsonify({"ok": False, "resposta": "Essa imagem ficou grande demais. Tenta novamente."}), 400

    if not isinstance(historico, list):
        historico = []

    resultado = FitBotService.get_resposta(
        mensagem=mensagem,
        imagem_base64=imagem_base64,
        historico=historico,
    )

    status = 200 if resultado.get("ok") else 503
    return jsonify(resultado), status