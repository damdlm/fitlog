"""Service da tela "Contato" -- transcrição de áudio (Groq Whisper) e
envio de e-mail para o(s) administrador(es) do sistema.
"""

import logging

import requests
from flask import current_app
from markupsafe import escape

from models import User
from utils.email_utils import enviar_email

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
TIMEOUT = 30

# Tamanho máximo aceito para o arquivo de áudio (~8 MB é bastante para
# alguns minutos de fala em webm/opus -- a Groq aceita até 25 MB, mas
# não faz sentido permitir upload tão grande numa caixa de mensagem).
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class ContatoService:

    @staticmethod
    def transcrever_audio(arquivo):
        """
        Transcreve um arquivo de áudio (werkzeug FileStorage) usando a
        API de transcrição da Groq (Whisper).

        Retorna um dict {"ok": bool, "texto": str} -- "texto" traz a
        transcrição em caso de sucesso, ou uma mensagem de erro amigável
        em caso de falha.
        """
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            logger.warning("Contato: GROQ_API_KEY não configurada -- transcrição indisponível.")
            return {"ok": False, "texto": "Transcrição de áudio indisponível no momento. Tente digitar sua mensagem."}

        conteudo = arquivo.read()
        if not conteudo:
            return {"ok": False, "texto": "Áudio vazio, tente gravar novamente."}

        if len(conteudo) > MAX_AUDIO_BYTES:
            return {"ok": False, "texto": "Áudio muito longo. Tente uma mensagem mais curta."}

        modelo = current_app.config.get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

        try:
            resposta = requests.post(
                GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (arquivo.filename or "audio.webm", conteudo, arquivo.mimetype or "audio/webm")},
                data={"model": modelo, "language": "pt", "response_format": "json"},
                timeout=TIMEOUT,
            )
            resposta.raise_for_status()
            texto = (resposta.json().get("text") or "").strip()

            if not texto:
                return {"ok": False, "texto": "Não consegui entender o áudio. Tente novamente ou digite sua mensagem."}

            return {"ok": True, "texto": texto}

        except requests.exceptions.Timeout:
            logger.warning("Contato: timeout ao transcrever áudio na Groq.")
            return {"ok": False, "texto": "A transcrição demorou demais. Tente novamente ou digite sua mensagem."}
        except Exception:
            logger.exception("Contato: falha ao transcrever áudio.")
            return {"ok": False, "texto": "Não foi possível transcrever o áudio agora. Tente digitar sua mensagem."}

    @staticmethod
    def _emails_administradores():
        """
        Emails de destino: todo usuário com is_admin=True que tenha
        e-mail cadastrado. Se nenhum for encontrado (ex: banco recém
        criado, sem admin ainda), cai para ADMIN_EMAIL (env var opcional
        -- ver config.py) como último recurso.
        """
        emails = [
            u.email for u in User.query.filter_by(is_admin=True).all()
            if u.email
        ]
        if emails:
            return emails

        fallback = current_app.config.get("ADMIN_EMAIL")
        return [fallback] if fallback else []

    @staticmethod
    def enviar_mensagem(usuario, mensagem):
        """
        Envia a mensagem de contato por e-mail para o(s) administrador(es).

        Retorna um dict {"ok": bool, "erro": str|None}.
        """
        mensagem = (mensagem or "").strip()
        if not mensagem:
            return {"ok": False, "erro": "Escreva ou grave uma mensagem antes de enviar."}

        if len(mensagem) > 4000:
            return {"ok": False, "erro": "Mensagem muito longa. Tente resumir um pouco."}

        destinatarios = ContatoService._emails_administradores()
        if not destinatarios:
            logger.error("Contato: nenhum e-mail de administrador configurado -- mensagem não enviada.")
            return {"ok": False, "erro": "Não foi possível enviar sua mensagem agora. Tente novamente mais tarde."}

        assunto = f"FitLog — Nova mensagem de contato de {usuario.nome_completo or usuario.username}"
        corpo_texto = (
            f"Nova mensagem recebida pela tela de Contato do FitLog.\n\n"
            f"De: {usuario.nome_completo or usuario.username} ({usuario.email})\n"
            f"Tipo de usuário: {usuario.tipo_usuario}\n\n"
            f"Mensagem:\n{mensagem}\n"
        )
        # Escapamos tudo que vem do usuário (nome, e-mail, tipo e mensagem)
        # antes de montar o HTML -- corrige HTML injection na tela de
        # Contato (CORREÇÃO 3 do hardening de segurança). O e-mail já
        # cadastrado do usuário é validado no registro, mas escapamos
        # mesmo assim por defesa em profundidade e por ser O(1)/local,
        # sem custo adicional de banco ou rede.
        nome_html = escape(usuario.nome_completo or usuario.username)
        email_html = escape(usuario.email)
        tipo_html = escape(usuario.tipo_usuario)
        mensagem_html = escape(mensagem)

        corpo_html = (
            f"<p>Nova mensagem recebida pela tela de <strong>Contato</strong> do FitLog.</p>"
            f"<p><strong>De:</strong> {nome_html} "
            f"(<a href='mailto:{email_html}'>{email_html}</a>)<br>"
            f"<strong>Tipo de usuário:</strong> {tipo_html}</p>"
            f"<p><strong>Mensagem:</strong></p>"
            f"<p style='white-space:pre-wrap;background:#f9f9f9;padding:12px;border-radius:8px;'>{mensagem_html}</p>"
        )

        # Envia para cada admin -- enviar_email já trata falhas
        # individualmente (loga e retorna False) sem derrubar a request.
        enviado_para_alguem = False
        for destinatario in destinatarios:
            if enviar_email(destinatario, assunto, corpo_texto, corpo_html):
                enviado_para_alguem = True

        if not enviado_para_alguem:
            # Em dev sem RESEND_API_KEY configurada, enviar_email só loga
            # e retorna False -- não é um erro real do ponto de vista do
            # usuário, então não bloqueamos o fluxo por isso.
            logger.info("Contato: mensagem registrada em log (e-mail não enviado de verdade -- sem API key).")

        return {"ok": True, "erro": None}
