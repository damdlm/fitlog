"""
Utilitário de envio de e-mail via SMTP do Gmail (smtp.gmail.com:587).

ATENÇÃO: a Railway (e outros PaaS) podem bloquear conexões SMTP de
saída (portas 25/465/587) por padrão, dependendo do plano/região, para
evitar abuso. Se o envio começar a falhar por timeout de conexão (em
vez de erro de autenticação), é sinal desse bloqueio -- nesse caso, a
alternativa é enviar via uma API HTTPS (ex: SendGrid), que usa a porta
443, normalmente liberada.

Autenticação: GMAIL_USER é o endereço Gmail completo (ex:
usuario@gmail.com). GMAIL_APP_PASSWORD é uma "senha de app" de 16
dígitos gerada em myaccount.google.com -> Segurança -> Verificação em
duas etapas -> Senhas de app. Isso exige que a verificação em duas
etapas esteja ativada na conta Google -- a senha normal da conta NÃO
funciona aqui (o Google bloqueia login de app com a senha normal).

Configuração via variáveis de ambiente (ver config.py):
    GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_DEFAULT_SENDER (opcional,
    usa GMAIL_USER como padrão se não definido)

Se GMAIL_USER ou GMAIL_APP_PASSWORD não estiverem configuradas (ex:
ambiente de desenvolvimento local sem credenciais), o e-mail não é
enviado de verdade -- o conteúdo é apenas registrado no logger em
nível INFO, para permitir testar o fluxo de recuperação de senha sem
precisar de credenciais reais.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)

SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_TIMEOUT = 10


def enviar_email(destinatario, assunto, corpo_texto, corpo_html=None):
    """
    Envia um e-mail simples (texto + opcionalmente HTML) via SMTP do Gmail.

    Retorna True se o e-mail foi aceito pelo servidor SMTP do Gmail, ou
    False se apenas foi registrado em log (credenciais não configuradas)
    ou se houve falha no envio.
    """
    usuario = current_app.config.get('GMAIL_USER')
    senha_app = current_app.config.get('GMAIL_APP_PASSWORD')

    if not usuario or not senha_app:
        # Sem credenciais configuradas (ex: dev local): loga o conteúdo
        # em vez de falhar silenciosamente, para o fluxo continuar
        # testável.
        logger.info(
            "GMAIL_USER/GMAIL_APP_PASSWORD nao configurados -- e-mail NAO enviado de verdade.\n"
            "Para: %s | Assunto: %s\n%s",
            destinatario, assunto, corpo_texto,
        )
        return False

    remetente = current_app.config.get('MAIL_DEFAULT_SENDER') or usuario

    mensagem = MIMEMultipart('alternative')
    mensagem['Subject'] = assunto
    mensagem['From'] = remetente
    mensagem['To'] = destinatario
    mensagem.attach(MIMEText(corpo_texto, 'plain'))
    if corpo_html:
        mensagem.attach(MIMEText(corpo_html, 'html'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as servidor:
            servidor.starttls()
            servidor.login(usuario, senha_app)
            servidor.sendmail(remetente, [destinatario], mensagem.as_string())
        logger.info("E-mail enviado -- destinatario=%s assunto=%s", destinatario, assunto)
        return True
    except Exception as e:
        # Falha de envio nao deve derrubar a request (ex: usuario pediria
        # reset de senha e receberia um erro 500 por causa do envio de
        # e-mail). O chamador trata isso mostrando uma mensagem generica
        # ao usuario.
        logger.error("Falha ao enviar e-mail para %s: %s", destinatario, e)
        return False