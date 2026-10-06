
"""Verificação de e-mail no cadastro.

Token assinado (itsdangerous) com o id do usuário e o e-mail no momento
do envio, sem tabela nova: se o e-mail da conta mudar, links antigos
deixam de valer; reabrir o mesmo link depois de verificado é inofensivo
(idempotente). Expira em 48 horas -- o usuário pede outro na tela de
pendência.
"""
from datetime import datetime, timezone

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db
from models import User

SALT = 'fitlog-email-verify-v1'
VALIDADE_SEGUNDOS = 48 * 3600


class EmailVerificacaoService:
    @staticmethod
    def _serializer():
        return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=SALT)

    @staticmethod
    def obrigatoria() -> bool:
        return bool(current_app.config.get('EMAIL_VERIFICACAO_OBRIGATORIA', True))

    @staticmethod
    def gerar_token(user: User) -> str:
        return EmailVerificacaoService._serializer().dumps({'uid': user.id, 'email': user.email})

    @staticmethod
    def usuario_do_token(token: str):
        """Devolve o User do token, ou None se inválido/expirado/e-mail
        trocado/conta inativa."""
        try:
            dados = EmailVerificacaoService._serializer().loads(token, max_age=VALIDADE_SEGUNDOS)
        except (BadSignature, SignatureExpired):
            return None
        if not isinstance(dados, dict):
            return None
        user = db.session.get(User, dados.get('uid'))
        if user is None or not user.ativo or user.email != dados.get('email'):
            return None
        return user

    @staticmethod
    def marcar_verificado(user: User, commit: bool = True) -> None:
        if user.email_verificado_em is None:
            user.email_verificado_em = datetime.now(timezone.utc)
            if commit:
                db.session.commit()

    @staticmethod
    def precisa_verificar(user) -> bool:
        """True se este usuário ainda deve confirmar o e-mail para usar o
        app. Admins não são barrados (nunca ficam trancados para fora)."""
        if not EmailVerificacaoService.obrigatoria():
            return False
        if getattr(user, 'is_admin', False):
            return False
        return getattr(user, 'email_verificado_em', None) is None
