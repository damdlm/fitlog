"""Rotas de privacidade / LGPD.

- GET  /privacidade                 -> política de privacidade (pública)
- GET  /privacidade/termos          -> termos de uso (pública)
- GET  /privacidade/central         -> autoatendimento (dados, exportar, excluir)
- GET  /privacidade/exportar-dados  -> download JSON dos próprios dados
- POST /privacidade/excluir-conta   -> anonimiza a conta (exige senha)
- POST /privacidade/fitbot-consentimento -> concede/revoga uso de IA pelo FitBot
- GET/POST /privacidade/aceite      -> reaceite de Termos/Política p/ usuários
                                        existentes, quando a versão vigente muda
                                        (ver app.py:_exigir_aceite_lgpd_atual)
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

import json

from extensions import limiter
from models import ConsentimentoLGPD
from services.privacidade_service import (
    PrivacidadeService,
    TIPO_FITBOT,
    TIPO_TERMOS_USO,
    TIPO_POLITICA_PRIVACIDADE,
)
from routes.auth_routes import _safe_next_url

privacidade_bp = Blueprint("privacidade", __name__)
logger = logging.getLogger(__name__)


@privacidade_bp.route("/", methods=["GET"])
def politica():
    """Política de Privacidade -- pública, não exige login (precisa
    poder ser lida por quem ainda está decidindo se cria conta)."""
    return render_template("privacidade/politica.html")


@privacidade_bp.route("/termos", methods=["GET"])
def termos():
    """Termos de Uso -- pública, mesmo motivo da política acima."""
    return render_template("privacidade/termos.html")


@privacidade_bp.route("/central", methods=["GET"])
@login_required
def central():
    """Central de Privacidade: estado atual do consentimento do FitBot
    e atalhos para exportar/excluir os próprios dados."""
    fitbot_consentido = PrivacidadeService.tem_consentimento_fitbot(current_user.id)
    return render_template("privacidade/central.html", fitbot_consentido=fitbot_consentido)


@privacidade_bp.route("/aceite", methods=["GET", "POST"])
@login_required
def aceite():
    """Tela de reaceite para contas já existentes, mostrada só quando a
    versão vigente de Termos e/ou Política mudou desde o último aceite
    (ver PrivacidadeService.documentos_pendentes). Nunca aparece de novo
    depois de aceito -- não é um "aceite a cada login"."""
    pendentes = PrivacidadeService.documentos_pendentes(current_user.id)
    destino = _safe_next_url(request.values.get("next"))

    if not pendentes:
        # Já está em dia (ex: acessou por um link direto/atualizou em
        # outra aba) -- não tem o que mostrar, manda pra frente.
        return redirect(destino)

    if request.method == "POST":
        if not request.form.get("ciencia"):
            flash("É preciso marcar que você está ciente para continuar.", "danger")
            return redirect(url_for("privacidade.aceite", next=destino))

        PrivacidadeService.registrar_aceite_pendentes(current_user.id)
        return redirect(destino)

    return render_template(
        "privacidade/aceite_atualizado.html",
        precisa_termos=TIPO_TERMOS_USO in pendentes,
        precisa_politica=TIPO_POLITICA_PRIVACIDADE in pendentes,
        next=destino,
    )


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
    IA de terceiros (Groq/Gemini/OpenAI). Chamado tanto pelo modal de
    primeiro uso do chat quanto pelo toggle em Meu Perfil."""
    dados = request.get_json(silent=True) or {}
    concedido = bool(dados.get("concedido", True))

    PrivacidadeService.registrar_consentimento(
        current_user.id, TIPO_FITBOT, concedido=concedido,
        contexto="chat" if concedido else "revogado em Meu Perfil",
    )
    return jsonify({"ok": True, "concedido": concedido})

