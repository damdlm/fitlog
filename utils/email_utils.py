"""
Utilitário de envio de e-mail via SMTP (usa apenas smtplib da stdlib,
sem adicionar Flask-Mail como dependência nova).

Configuração via variáveis de ambiente (ver config.py):
    MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD,
    MAIL_DEFAULT_SENDER

Se MAIL_SERVER não estiver configurado (ex: ambiente de desenvolvimento
local sem SMTP), o e-mail não é enviado de verdade — o conteúdo é apenas
registrado no logger em nível INFO, para permitir testar o fluxo de
recuperação de senha sem precisar de um servidor SMTP real.
"""

import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


def enviar_email(destinatario, assunto, corpo_texto, corpo_html=None):
    """
    Envia um e-mail simples (texto + opcionalmente HTML).

    Retorna True se o e-mail foi (tentativamente) enviado via SMTP,
    ou False se apenas foi registrado em log (SMTP não configurado)
    ou se houve falha no envio.
    """
    mail_server = current_app.config.get('MAIL_SERVER')

    if not mail_server:
        # Sem SMTP configurado (ex: dev local): loga o conteúdo em vez de
        # falhar silenciosamente, para o fluxo continuar testável.
        logger.info(
            "MAIL_SERVER nao configurado -- e-mail NAO enviado de verdade.\n"
            "Para: %s | Assunto: %s\n%s",
            destinatario, assunto, corpo_texto,
        )
        return False

    remetente = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')

    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = destinatario
    msg.set_content(corpo_texto)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype='html')

    porta = current_app.config.get('MAIL_PORT', 587)
    usar_tls = current_app.config.get('MAIL_USE_TLS', True)
    usuario = current_app.config.get('MAIL_USERNAME')
    senha = current_app.config.get('MAIL_PASSWORD')

    try:
        with smtplib.SMTP(mail_server, porta, timeout=10) as smtp:
            if usar_tls:
                smtp.starttls()
            if usuario and senha:
                smtp.login(usuario, senha)
            smtp.send_message(msg)
        logger.info("E-mail enviado -- destinatario=%s assunto=%s", destinatario, assunto)
        return True
    except Exception as e:
        # Falha de envio nao deve derrubar a request (ex: usuario pediria
        # reset de senha e receberia um erro 500 por causa do SMTP).
        # O chamador trata isso mostrando uma mensagem generica ao usuario.
        logger.error("Falha ao enviar e-mail para %s: %s", destinatario, e)
        return False