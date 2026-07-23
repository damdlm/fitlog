"""
Utilitário de envio de e-mail via API HTTPS do SendGrid (https://sendgrid.com).

Motivo de usar API em vez de SMTP: a Railway (e outros PaaS) bloqueiam
conexões SMTP de saída (portas 25/465/587) por padrão para evitar abuso.
A API do SendGrid funciona via HTTPS (porta 443), que nunca é bloqueada.

O remetente (MAIL_DEFAULT_SENDER) precisa estar verificado no SendGrid
via "Single Sender Verification" (Settings > Sender Authentication) --
isso permite usar um endereço avulso (ex: Gmail) como remetente, sem
precisar ser dono de um domínio próprio.

Configuração via variáveis de ambiente (ver config.py):
    SENDGRID_API_KEY, MAIL_DEFAULT_SENDER

Se SENDGRID_API_KEY não estiver configurada (ex: ambiente de
desenvolvimento local sem chave), o e-mail não é enviado de verdade --
o conteúdo é apenas registrado no logger em nível INFO, para permitir
testar o fluxo de recuperação de senha sem precisar de uma conta
SendGrid real.
"""

import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

SENDGRID_API_URL = 'https://api.sendgrid.com/v3/mail/send'


def enviar_email(destinatario, assunto, corpo_texto, corpo_html=None):
    """
    Envia um e-mail simples (texto + opcionalmente HTML) via API do SendGrid.

    Retorna True se o e-mail foi aceito pela API do SendGrid, ou False se
    apenas foi registrado em log (API key não configurada) ou se houve
    falha no envio.
    """
    api_key = current_app.config.get('SENDGRID_API_KEY')

    if not api_key:
        # Sem API key configurada (ex: dev local): loga o conteúdo em vez
        # de falhar silenciosamente, para o fluxo continuar testável.
        logger.info(
            "SENDGRID_API_KEY nao configurada -- e-mail NAO enviado de verdade.\n"
            "Para: %s | Assunto: %s\n%s",
            destinatario, assunto, corpo_texto,
        )
        return False

    remetente = current_app.config.get('MAIL_DEFAULT_SENDER')

    conteudo = [{'type': 'text/plain', 'value': corpo_texto}]
    if corpo_html:
        conteudo.append({'type': 'text/html', 'value': corpo_html})

    payload = {
        'personalizations': [{'to': [{'email': destinatario}]}],
        'from': {'email': remetente},
        'subject': assunto,
        'content': conteudo,
    }

    try:
        resposta = requests.post(
            SENDGRID_API_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=10,
        )
        resposta.raise_for_status()
        logger.info("E-mail enviado -- destinatario=%s assunto=%s", destinatario, assunto)
        return True
    except Exception as e:
        # Falha de envio nao deve derrubar a request (ex: usuario pediria
        # reset de senha e receberia um erro 500 por causa da API de e-mail).
        # O chamador trata isso mostrando uma mensagem generica ao usuario.
        logger.error("Falha ao enviar e-mail para %s: %s", destinatario, e)
        return False