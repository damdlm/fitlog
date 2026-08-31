"""Rotas de privacidade / LGPD.

- GET  /privacidade                 -> política de privacidade (pública)
- GET  /privacidade/central         -> autoatendimento (dados, exportar, excluir)
- GET  /privacidade/exportar-dados  -> download JSON dos próprios dados
- POST /privacidade/excluir-conta   -> anonimiza a conta (exige senha)
- POST /privacidade/fitbot-consentimento -> concede/revoga uso de IA pelo FitBot
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

import json

from extensions import limiter
from models import ConsentimentoLGPD
from services.privacidade_service import PrivacidadeService, TIPO_FITBOT

privacidade_bp = Blueprint("privacidade", __name__)
logger = logging.getLogger(__name__)


@privacidade_bp.route("/", methods=["GET"])
def politica():
    """Política de privacidade -- pública, não exige login (precisa
    poder ser lida por quem ainda está decidindo se cria conta)."""
    return render_template("privacidade/politica.html")


@privacidade_bp.route("/central", methods=["GET"])
@login_required
def central():
    """Central de Privacidade: estado atual do consentimento do FitBot
    e atalhos para exportar/excluir os próprios dados."""
    fitbot_consentido = PrivacidadeService.tem_consentimento_fitbot(current_user.id)
    return render_template("privacidade/central.html", fitbot_consentido=fitbot_consentido)


@privacidade_bp.route("/exportar-dados", methods=["GET"])
@login_required
@limiter.limit("5 per hour")
def exportar_dados():
    """Devolve um JSON com todos os dados pessoais do usuário logado
    (portabilidade -- Art. 18, V da LGPD)."""
    dados = PrivacidadeService.exportar_dados(current_user)
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    nome_arquivo = f"fitlog-meus-dados-{current_user.username}.json"
    return Response(
        corpo,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@privacidade_bp.route("/excluir-conta", methods=["POST"])
@login_required
@limiter.limit("5 per hour")
def excluir_conta():
    """Anonimiza a conta do usuário logado (exclusão/esquecimento --
    Art. 18, VI da LGPD). Exige a senha atual como confirmação, no
    mesmo padrão usado em auth.change_password."""
    senha = request.form.get("senha_confirmacao", "")

    if not senha or not current_user.check_password(senha):
        flash("Senha incorreta. A exclusão da conta não foi realizada.", "danger")
        return redirect(url_for("privacidade.central"))

    usuario_id = current_user.id
    ok = PrivacidadeService.anonimizar_conta(current_user)

    if not ok:
        flash("Não foi possível excluir sua conta agora. Tente novamente.", "danger")
        return redirect(url_for("privacidade.central"))

    logout_user()
    logger.info("Conta excluída/anonimizada pelo próprio titular -- usuario ID %s", usuario_id)
    flash("Sua conta foi excluída. Seus dados pessoais foram removidos.", "info")
    return redirect(url_for("auth.login"))


@privacidade_bp.route("/fitbot-consentimento", methods=["POST"])
@login_required
def fitbot_consentimento():
    """Concede ou revoga o consentimento para o FitBot enviar dados a
    IA de terceiros (Groq/Gemini). Chamado tanto pelo modal de
    primeiro uso do chat quanto pelo toggle em Meu Perfil."""
    dados = request.get_json(silent=True) or {}
    concedido = bool(dados.get("concedido", True))

    PrivacidadeService.registrar_consentimento(
        current_user.id, TIPO_FITBOT, concedido=concedido,
        contexto="chat" if concedido else "revogado em Meu Perfil",
    )
    return jsonify({"ok": True, "concedido": concedido})
