"""Registro e consulta de travamentos da aplicação (frontend e
backend) -- alimenta o painel /admin/crash-logs.

Frontend: static/js/crash-watchdog.js captura erros JS não tratados,
promises rejeitadas sem catch, congelamentos de UI (thread principal
bloqueada por tempo demais) e indícios de que a sessão anterior
encerrou de forma anormal (ex: o processo do PWA sendo morto pelo
sistema por falta de memória -- ver o histórico da "saga do crash" já
resolvida no calendário/modal de exercícios), e reporta via POST
público (sem login) para /admin/crash-logs/api/reportar.

Backend: app.py:erro_500 grava aqui antes de renderizar a página de
erro genérica.

Tudo gravado em best-effort -- uma falha ao registrar o log NUNCA pode
impedir a recuperação em si (nem o reload do frontend, nem a resposta
500 do backend), por isso todo método aqui engole exceção própria."""

import logging
from datetime import datetime, timedelta, timezone

from models import db, CrashLog

logger = logging.getLogger(__name__)

# Suficiente pra investigar um problema recorrente sem deixar a tabela
# crescer indefinidamente -- limpeza roda junto do cron semanal de
# notificações (ver app.py, comando `notificacoes-limpar`).
RETENCAO_DIAS = 30

TIPOS_FRONTEND_VALIDOS = {'js_error', 'promise_rejeitada', 'ui_travada', 'crash_anterior'}


class CrashLogService:

    @staticmethod
    def registrar_frontend(tipo, mensagem, detalhes=None, url=None, user_agent=None, usuario_id=None):
        """Grava um travamento reportado pelo navegador. `tipo` fora da
        lista conhecida cai em 'js_error' em vez de rejeitar -- o
        cliente pode estar rodando uma versão antiga do JS depois de um
        deploy, sem que isso deva perder o relatório."""
        try:
            if tipo not in TIPOS_FRONTEND_VALIDOS:
                tipo = 'js_error'
            log = CrashLog(
                origem='frontend',
                tipo=tipo,
                mensagem=(mensagem or '(sem mensagem)')[:2000],
                detalhes=(detalhes or '')[:8000] or None,
                url=(url or '')[:500] or None,
                user_agent=(user_agent or '')[:300] or None,
                usuario_id=usuario_id,
            )
            db.session.add(log)
            db.session.commit()
            return log
        except Exception:
            db.session.rollback()
            logger.exception("CrashLog: falha ao registrar travamento de frontend")
            return None

    @staticmethod
    def registrar_backend(tipo, mensagem, detalhes=None, url=None, usuario_id=None):
        """Grava uma exceção 500 não tratada. Chamado de dentro do
        próprio errorhandler(500) -- ver docstring do módulo."""
        try:
            log = CrashLog(
                origem='backend',
                tipo=(tipo or 'Exception')[:40],
                mensagem=(mensagem or '(sem mensagem)')[:2000],
                detalhes=(detalhes or '')[:8000] or None,
                url=(url or '')[:500] or None,
                usuario_id=usuario_id,
            )
            db.session.add(log)
            db.session.commit()
            return log
        except Exception:
            db.session.rollback()
            logger.exception("CrashLog: falha ao registrar travamento de backend")
            return None

    @staticmethod
    def listar(origem=None, page=1, per_page=30):
        """Página de travamentos, mais recente primeiro. `origem`
        filtra 'frontend'/'backend'; qualquer outro valor (inclusive
        None) traz os dois."""
        query = CrashLog.query.order_by(CrashLog.criado_em.desc())
        if origem in ('frontend', 'backend'):
            query = query.filter(CrashLog.origem == origem)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def contar_recentes(horas=24):
        """Total de travamentos nas últimas `horas` -- usado no badge
        de destaque do painel."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(hours=horas)
            return CrashLog.query.filter(CrashLog.criado_em >= desde).count()
        except Exception:
            logger.exception("CrashLog: falha ao contar travamentos recentes")
            return None

    @staticmethod
    def limpar_antigas(dias_retencao=RETENCAO_DIAS):
        """Remove travamentos mais antigos que `dias_retencao` dias.
        Chamado pelo comando CLI `notificacoes-limpar` (cron semanal
        já existente -- ver app.py)."""
        try:
            limite = datetime.now(timezone.utc) - timedelta(days=dias_retencao)
            total = CrashLog.query.filter(CrashLog.criado_em < limite).delete()
            db.session.commit()
            return total
        except Exception:
            db.session.rollback()
            logger.exception("CrashLog: falha ao limpar travamentos antigos")
            return None
