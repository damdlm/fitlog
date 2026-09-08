"""Serviço de notificações in-app entre aluno e professor vinculados.

Sem infraestrutura de push (ver static/sw.js, que só existe pra permitir
"Instalar app") -- as notificações aqui vivem só no banco e são lidas
via polling pela tela/menu de notificações (ver static/js/modules/
notificacoes.js).

Toda criação de notificação é "best effort": uma falha aqui nunca deve
quebrar a ação principal do usuário (salvar um treino, editar uma
versão etc) -- por isso _criar() engole e loga qualquer exceção em vez
de propagar.
"""

import logging

from models import db, Notificacao
from services.base_service import BaseService

logger = logging.getLogger(__name__)


class NotificacaoService(BaseService):

    LIMITE_PADRAO = 20

    @staticmethod
    def _nome(usuario):
        if not usuario:
            return 'Alguém'
        return usuario.nome_completo or usuario.username

    @staticmethod
    def _criar(destinatario_id, remetente_id, tipo, titulo, mensagem, url=None):
        """Cria e persiste uma notificação. Nunca levanta exceção --
        retorna None em caso de falha (ver docstring do módulo)."""
        if not destinatario_id:
            return None
        try:
            notificacao = Notificacao(
                destinatario_id=destinatario_id,
                remetente_id=remetente_id,
                tipo=tipo,
                titulo=titulo[:150],
                mensagem=mensagem[:300],
                url=url,
            )
            db.session.add(notificacao)
            db.session.commit()
            return notificacao
        except Exception:
            db.session.rollback()
            logger.exception(
                "Falha ao criar notificação (tipo=%s, destinatario=%s)",
                tipo, destinatario_id
            )
            return None

    @staticmethod
    def notificar_professor(aluno, tipo, titulo, mensagem, url=None):
        """Notifica o professor vinculado ao aluno, se houver vínculo
        ativo. Sem professor vinculado, não faz nada (aluno sem
        professor é um caso normal do app -- ver AlunoProfessor)."""
        professor = BaseService.get_professor_do_aluno(aluno.id)
        if not professor:
            return None
        return NotificacaoService._criar(
            destinatario_id=professor.id,
            remetente_id=aluno.id,
            tipo=tipo,
            titulo=titulo,
            mensagem=mensagem,
            url=url,
        )

    @staticmethod
    def notificar_aluno(aluno_id, professor, tipo, titulo, mensagem, url=None):
        """Notifica o aluno sobre uma ação feita pelo professor no
        treino dele."""
        return NotificacaoService._criar(
            destinatario_id=aluno_id,
            remetente_id=professor.id if professor else None,
            tipo=tipo,
            titulo=titulo,
            mensagem=mensagem,
            url=url,
        )

    @staticmethod
    def listar(user_id, apenas_nao_lidas=False, limit=None):
        query = Notificacao.query.filter_by(destinatario_id=user_id)
        if apenas_nao_lidas:
            query = query.filter_by(lida=False)
        query = query.order_by(Notificacao.created_at.desc())
        return query.limit(limit or NotificacaoService.LIMITE_PADRAO).all()

    @staticmethod
    def contar_nao_lidas(user_id):
        return Notificacao.query.filter_by(destinatario_id=user_id, lida=False).count()

    @staticmethod
    def marcar_como_lida(notificacao_id, user_id):
        """Marca uma notificação como lida -- só se ela pertencer ao
        usuário (evita que um ID adivinhado marque notificação de
        outra pessoa)."""
        notificacao = Notificacao.query.filter_by(
            id=notificacao_id, destinatario_id=user_id
        ).first()
        if not notificacao:
            return False
        try:
            notificacao.lida = True
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Falha ao marcar notificação %s como lida", notificacao_id)
            return False

    @staticmethod
    def marcar_todas_como_lidas(user_id):
        try:
            Notificacao.query.filter_by(destinatario_id=user_id, lida=False) \
                .update({'lida': True})
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Falha ao marcar todas as notificações do usuário %s como lidas", user_id)
            return False
