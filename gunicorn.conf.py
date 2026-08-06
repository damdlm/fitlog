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
# gthread (não sync): com só 2 processos, uma chamada síncrona e lenta
# (ex: FitBot chamando Groq/Gemini, até 20s de timeout — ver
# services/fitbot_service.py) prendia o worker inteiro. Como só há 2
# workers no total, bastavam 2 usuários mandando mensagem ao FitBot ao
# mesmo tempo pra deixar o app INTEIRO (login, calendário, tudo) sem
# nenhum worker livre por até 20s — não é hipotético, é uma conta direta
# com os números atuais (workers=2 x timeout=20s do FitBot).
#
# gthread com poucas threads por worker resolve a causa raiz (I/O
# bloqueante prendendo o processo) sem precisar de fila/worker
# assíncrono separado (Celery/RQ): enquanto uma thread espera a resposta
# do LLM, as outras do mesmo worker continuam atendendo request normais.
# É uma mudança de 1 linha de config, sem nova infraestrutura, e
# reversível (é só tirar as duas linhas abaixo para voltar ao worker
# sync padrão).
#
# Threads convivem no mesmo processo (memória compartilhada), diferente
# de sync workers (processos separados) -- isso é seguro aqui porque:
# request/g/current_app do Flask já são thread-safe (context-local), e
# o SQLAlchemy scoped_session do Flask-SQLAlchemy já escopa por thread
# por padrão. Não há estado mutável global não-trivial no projeto (o
# único cache em memória de processo, o catálogo de exercícios em
# routes/api_routes.py, é só leitura após o primeiro load; uma corrida
# no primeiro load faz no máximo um parse duplicado, não corrompe nada).
worker_class = "gthread"
threads = 4
timeout = 120


def worker_abort(worker):
    worker.log.critical("WORKER TIMEOUT (pid: %s) — despejando stack trace", worker.pid)
    faulthandler.dump_traceback(sys.stderr)