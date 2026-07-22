"""
Configuração do Gunicorn.

O hook `worker_abort` roda no exato momento em que o gunicorn manda
SIGABRT para um worker que estourou o --timeout. Sem ele, o worker
simplesmente desaparece do log ("Worker exiting") sem indicar qual
linha de código estava executando — foi o que aconteceu nos logs
de produção: nenhum rastro de onde o processo ficou preso.

Com faulthandler.dump_traceback, o stack trace de TODAS as threads
do processo é despejado no stderr um instante antes da morte do
worker, indo parar nos logs do Railway. Na próxima vez que travar,
o log vai mostrar exatamente a linha (provavelmente dentro de uma
chamada ao banco, se for isso).
"""
import os
import sys
import faulthandler

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 2
timeout = 120


def worker_abort(worker):
    worker.log.critical("WORKER TIMEOUT (pid: %s) — despejando stack trace", worker.pid)
    faulthandler.dump_traceback(sys.stderr)