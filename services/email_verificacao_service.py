
"""Verificação de e-mail no cadastro.

Token assinado (itsdangerous) com o id do usuário e o e-mail no momento
do envio, sem tabela nova: se o e-mail da conta mudar, links antigos
deixam de valer; reabrir o mesmo link depois de verificado é inofensivo
(idempotente). Expira em 48 horas -- o usuário pede outro na tela de
pendência.
"""
import math
from datetime import datetime, timedelta, timezone

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db
from models import User

SALT = 'fitlog-email-verify-v1'
VALIDADE_SEGUNDOS = 48 * 3600

# Conta nova usa o app na hora, sem confirmar o e-mail, por estes dias
# (com um aviso no topo). Durante a carência só ficam travadas as áreas
# que custam dinheiro ou dependem do e-mail ser da pessoa: FitBot (IA) e
# assinatura/pagamento. Passou a carência sem confirmar -> app inteiro
# travado, como antes. Troca de e-mail numa conta antiga trava na hora
# (a conta já passou da carência).
CARENCIA_DIAS = 7
PREFIXOS_TRAVADOS_NA_CARENCIA = ('fitbot.', 'billing.')


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

    @staticmethod
    def dias_restantes_carencia(user) -> int:
        """Dias (arredondados para cima) que faltam da carência; 0 = acabou."""
        criado = getattr(user, 'created_at', None)
        if criado is None:
            return 0
        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)
        restante = criado + timedelta(days=CARENCIA_DIAS) - datetime.now(timezone.utc)
        if restante.total_seconds() <= 0:
            return 0
        return math.ceil(restante.total_seconds() / 86400)

    @staticmethod
    def em_carencia(user) -> bool:
        return EmailVerificacaoService.dias_restantes_carencia(user) > 0

    @staticmethod
    def bloqueia_endpoint(user, endpoint: str) -> bool:
        """True se este endpoint deve ser barrado agora por falta de
        confirmação do e-mail."""
        if not EmailVerificacaoService.precisa_verificar(user):
            return False
        if not EmailVerificacaoService.em_carencia(user):
            return True
        return (endpoint or '').startswith(PREFIXOS_TRAVADOS_NA_CARENCIA)
