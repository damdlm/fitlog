"""Execução de jobs agendados (Railway Cron) com isolamento de falhas.

Os comandos `flask ...` rodados pelo cron encadeavam etapas com `sh -c "a; b; c"`:
o código de saída era só o do ÚLTIMO comando, então uma falha em `a` ou `b`
aparecia no Railway como "Last run succeeded". `executar_etapas` roda cada
etapa isolada (uma falha não impede as seguintes), registra a exceção no log
e no Sentry, e devolve quais falharam para o comando terminar com código != 0.
"""
import logging

import sentry_sdk

from models import db

logger = logging.getLogger(__name__)


def executar_etapas(etapas):
    """Roda `etapas` -- iterável de (nome, callable sem argumentos) -- em ordem.

    Devolve (resultados, falhas): `resultados` mapeia nome -> retorno da etapa
    (só das que deram certo) e `falhas` lista os nomes das que levantaram
    exceção. A sessão do banco recebe rollback após uma falha, para a etapa
    seguinte não herdar uma transação quebrada."""
    resultados = {}
    falhas = []
    for nome, funcao in etapas:
        try:
            resultados[nome] = funcao()
        except Exception as exc:
            db.session.rollback()
            falhas.append(nome)
            logger.exception('Etapa de cron falhou: %s', nome)
            sentry_sdk.capture_exception(exc)
    return resultados, falhas
