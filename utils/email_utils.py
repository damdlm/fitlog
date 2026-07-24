"""
Utilitário de envio de e-mail via API HTTPS do Resend
(api.resend.com).

Motivo de usar uma API HTTPS em vez de SMTP: a Railway bloqueia
conexões SMTP de saída (portas 25/465/587) por padrão -- confirmado em
produção com erro "Network is unreachable" na porta 587. A API do
Resend funciona via HTTPS (porta 443), que não é bloqueada.

Configuração via variáveis de ambiente (ver config.py):
    RESEND_API_KEY -- gerada em resend.com -> API Keys
    MAIL_DEFAULT_SENDER -- endereço de um domínio verificado em
        resend.com -> Domains, ou onboarding@resend.dev para testes
        (só entrega para o e-mail cadastrado na conta Resend)

Se RESEND_API_KEY não estiver configurada (ex: ambiente de
desenvolvimento local sem credenciais), o e-mail não é enviado de
verdade -- o conteúdo é apenas registrado no logger em nível INFO,
para permitir testar o fluxo de recuperação de senha sem precisar de
credenciais reais.
"""

import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

SEND_URL = 'https://api.resend.com/emails'
TIMEOUT = 10


def enviar_email(destinatario, assunto, corpo_texto, corpo_html=None):
    """
    Envia um e-mail simples (texto + opcionalmente HTML) via API do Resend.

    Retorna True se o e-mail foi aceito pela API do Resend, ou False se
    apenas foi registrado em log (API key não configurada) ou se houve
    falha no envio.
    """
    api_key = current_app.config.get('RESEND_API_KEY')

    if not api_key:
        # Sem API key configurada (ex: dev local): loga o conteúdo em
        # vez de falhar silenciosamente, para o fluxo continuar
        # testável.
        logger.info(
            "RESEND_API_KEY nao configurada -- e-mail NAO enviado de verdade.\n"
            "Para: %s | Assunto: %s\n%s",
            destinatario, assunto, corpo_texto,
        )
        return False

    remetente = current_app.config.get('MAIL_DEFAULT_SENDER')

    payload = {
        'from': remetente,
        'to': [destinatario],
        'subject': assunto,
        'text': corpo_texto,
    }
    if corpo_html:
        payload['html'] = corpo_html

    try:
        resposta = requests.post(
            SEND_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=TIMEOUT,
        )
        resposta.raise_for_status()
        logger.info("E-mail enviado -- destinatario=%s assunto=%s", destinatario, assunto)
        return True
    except Exception as e:
        # Falha de envio nao deve derrubar a request (ex: usuario pediria
        # reset de senha e receberia um erro 500 por causa do envio de
        # e-mail). O chamador trata isso mostrando uma mensagem generica
        # ao usuario.
        logger.error("Falha ao enviar e-mail para %s: %s", destinatario, e)
        return False