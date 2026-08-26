"""Coleta de métricas operacionais para o painel de monitoramento do
admin (routes/admin_routes.py:monitoramento). Tudo aqui é *leitura*:
nenhuma função neste módulo escreve no banco ou no cache.

Fontes de dado:
  - Processo (CPU/memória do próprio worker Gunicorn) -- via psutil,
    que lê /proc no Linux (funciona normalmente dentro do container
    do Railway, sem precisar de acesso à API da plataforma).
  - Banco (Postgres) -- via queries em pg_stat_database/pg_stat_activity
    quando o dialeto é postgresql; em SQLite (dev/testes) essas
    consultas não existem, então voltamos só o que dá pra saber pelo
    próprio SQLAlchemy (pool, arquivo do banco).
  - Cache/Redis -- via redis-py direto (mesma REDIS_URL do
    Flask-Limiter/Flask-Caching), comando INFO.

Qualquer falha ao coletar uma métrica é isolada: uma fonte indisponível
(ex: Redis fora do ar) não deve derrubar o painel inteiro, só marcar
aquele bloco como indisponível.
"""

import os
import time
import logging
from datetime import datetime, timezone

from models import db, User, Treino, RegistroTreino, Assinatura

logger = logging.getLogger(__name__)

# Guardado no processo (não no banco/cache) -- reinicia a cada deploy,
# o que é exatamente o "tempo online desde o último deploy" que
# interessa no painel.
_PROCESS_START = time.time()


class MonitoringService:

    # =========================================================
    # PROCESSO (CPU / MEMÓRIA -- AGREGADO DE TODOS OS WORKERS)
    # =========================================================
    @staticmethod
    def _workers_do_gunicorn(psutil_mod, processo_atual):
        """Retorna a lista de processos-worker do Gunicorn no mesmo
        container -- não só o processo que atendeu esta requisição.

        A app roda com `workers = 2` (gthread) no gunicorn.conf.py: são
        2 processos do SO, filhos do processo arbiter/master do
        Gunicorn. Sem esse passo, o painel só enxergaria o worker que
        por acaso atendeu cada requisição, fazendo CPU/memória
        "pularem" entre os dois processos a cada refresh sem isso
        representar uma variação real de carga.

        A relação usada é puramente pai->filhos via psutil (PID/PPID),
        não por nome de processo -- o Gunicorn só renomeia processos
        (para "gunicorn: worker [...]") quando o pacote `setproctitle`
        está instalado, o que não é o caso aqui (ver requirements.txt).
        Pai->filhos funciona independente disso.
        """
        try:
            pai = processo_atual.parent()
        except Exception:
            pai = None

        if pai is None:
            return [processo_atual]

        try:
            nome_pai = (pai.name() or "").lower()
            cmdline_pai = " ".join(pai.cmdline()).lower()
        except Exception:
            nome_pai = ""
            cmdline_pai = ""

        eh_gunicorn = "gunicorn" in nome_pai or "gunicorn" in cmdline_pai
        if not eh_gunicorn:
            # Não está rodando sob um master do Gunicorn (ex: `flask run`
            # local) -- só o processo atual mesmo.
            return [processo_atual]

        try:
            irmaos = pai.children()
        except Exception:
            irmaos = [processo_atual]

        return irmaos or [processo_atual]

    @classmethod
    def get_process_metrics(cls):
        """CPU/memória agregadas de TODOS os workers do Gunicorn (não
        só do processo que atendeu esta requisição) e do sistema onde
        eles rodam. Requer psutil -- se não estiver instalado, retorna
        disponivel=False em vez de quebrar a página."""
        try:
            import psutil
        except ImportError:
            return {"disponivel": False, "erro": "psutil não instalado"}

        try:
            processo_atual = psutil.Process(os.getpid())
            workers_proc = cls._workers_do_gunicorn(psutil, processo_atual)

            workers_info = []
            cpu_total = 0.0
            memoria_total_mb = 0.0
            threads_total = 0

            for p in workers_proc:
                try:
                    with p.oneshot():
                        # interval curto por processo -- com 2 workers,
                        # ~0.1-0.2s de latência extra no endpoint, aceitável
                        # para um painel que atualiza a cada 10s.
                        cpu_pct = p.cpu_percent(interval=0.1)
                        mem_mb = p.memory_info().rss / (1024 * 1024)
                        threads = p.num_threads()
                    workers_info.append({
                        "pid": p.pid,
                        "cpu_pct": round(cpu_pct, 1),
                        "memoria_mb": round(mem_mb, 1),
                        "threads": threads,
                    })
                    cpu_total += cpu_pct
                    memoria_total_mb += mem_mb
                    threads_total += threads
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Worker morreu/reiniciou entre a listagem e a leitura --
                    # ignora esse processo, não derruba a métrica inteira.
                    continue

            mem_sistema = psutil.virtual_memory()
            cpu_sistema = psutil.cpu_percent(interval=0.1)

            uptime_segundos = time.time() - _PROCESS_START

            return {
                "disponivel": True,
                "num_workers": len(workers_info),
                "workers": workers_info,
                # Agregado -- soma de todos os workers do Gunicorn, não
                # só do que atendeu esta requisição.
                "cpu_processo_pct": round(cpu_total, 1),
                "memoria_processo_mb": round(memoria_total_mb, 1),
                "num_threads": threads_total,
                "cpu_sistema_pct": round(cpu_sistema, 1),
                "memoria_sistema_usada_pct": round(mem_sistema.percent, 1),
                "memoria_sistema_total_mb": round(mem_sistema.total / (1024 * 1024), 1),
                "memoria_sistema_usada_mb": round(mem_sistema.used / (1024 * 1024), 1),
                "pid": os.getpid(),
                "uptime_segundos": int(uptime_segundos),
            }
        except Exception:
            logger.exception("Erro ao coletar métricas de processo")
            return {"disponivel": False, "erro": "falha ao ler métricas do processo"}

    # =========================================================
    # BANCO DE DADOS
    # =========================================================
    @staticmethod
    def get_database_metrics():
        try:
            from sqlalchemy import text

            engine = db.engine
            dialeto = engine.dialect.name  # 'postgresql' ou 'sqlite'

            pool = engine.pool
            pool_info = {
                "tamanho": pool.size() if hasattr(pool, "size") else None,
                "em_uso": pool.checkedout() if hasattr(pool, "checkedout") else None,
                "overflow": pool.overflow() if hasattr(pool, "overflow") else None,
            }

            resultado = {
                "disponivel": True,
                "dialeto": dialeto,
                "pool": pool_info,
            }

            if dialeto == "postgresql":
                with engine.connect() as conn:
                    # Tamanho do banco em disco
                    tamanho_bytes = conn.execute(text(
                        "SELECT pg_database_size(current_database())"
                    )).scalar()

                    # Conexões ativas neste banco (não no cluster inteiro)
                    conexoes = conn.execute(text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database()"
                    )).scalar()

                    conexoes_ativas = conn.execute(text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND state = 'active'"
                    )).scalar()

                    max_conexoes = conn.execute(text(
                        "SHOW max_connections"
                    )).scalar()

                    # Cache hit ratio -- proporção de leituras servidas pelo
                    # buffer cache do Postgres em vez de disco; abaixo de
                    # ~90% costuma indicar shared_buffers pequeno ou
                    # queries varrendo tabela demais.
                    hit_ratio_row = conn.execute(text(
                        "SELECT sum(blks_hit), sum(blks_hit) + sum(blks_read) "
                        "FROM pg_stat_database WHERE datname = current_database()"
                    )).fetchone()
                    blks_hit, blks_total = hit_ratio_row
                    cache_hit_ratio = (
                        round(100 * blks_hit / blks_total, 1)
                        if blks_total else None
                    )

                    resultado.update({
                        "tamanho_mb": round(tamanho_bytes / (1024 * 1024), 1),
                        "conexoes_total": conexoes,
                        "conexoes_ativas": conexoes_ativas,
                        "max_conexoes": int(max_conexoes),
                        "cache_hit_ratio_pct": cache_hit_ratio,
                    })
            else:
                # SQLite (dev/testes): sem catálogo equivalente a
                # pg_stat_*. Só o que é possível saber pelo arquivo.
                db_path = engine.url.database
                if db_path and db_path != ":memory:" and os.path.exists(db_path):
                    resultado["tamanho_mb"] = round(
                        os.path.getsize(db_path) / (1024 * 1024), 1
                    )

            return resultado
        except Exception:
            logger.exception("Erro ao coletar métricas do banco")
            return {"disponivel": False, "erro": "falha ao consultar o banco"}

    # =========================================================
    # CACHE / REDIS
    # =========================================================
    @staticmethod
    def get_cache_metrics():
        """Lê o Redis usado por Flask-Caching/Flask-Limiter direto via
        redis-py (já é uma dependência da aplicação -- ver
        requirements.txt), em vez de depender de atributos internos e
        não-documentados do Flask-Caching."""
        redis_url = os.getenv("REDIS_URL") or os.getenv("CACHE_REDIS_URL")
        if not redis_url:
            return {"disponivel": False, "erro": "REDIS_URL não configurada (cache em memória local)"}

        try:
            import redis

            cliente = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            info = cliente.info()

            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            hit_rate = round(100 * hits / total, 1) if total else None

            # info['db0'] vem como string "keys=N,expires=M,avg_ttl=..."
            # em algumas versões do redis-py já vem parseado como dict.
            db0 = info.get("db0")
            if isinstance(db0, dict):
                total_chaves = db0.get("keys")
            else:
                total_chaves = None

            return {
                "disponivel": True,
                "versao_redis": info.get("redis_version"),
                "memoria_usada_mb": round(info.get("used_memory", 0) / (1024 * 1024), 1),
                "memoria_pico_mb": round(info.get("used_memory_peak", 0) / (1024 * 1024), 1),
                "memoria_max_mb": (
                    round(info.get("maxmemory", 0) / (1024 * 1024), 1)
                    if info.get("maxmemory") else None
                ),
                "clientes_conectados": info.get("connected_clients"),
                "total_chaves": total_chaves,
                "hit_rate_pct": hit_rate,
                "uptime_segundos": info.get("uptime_in_seconds"),
                "comandos_processados": info.get("total_commands_processed"),
            }
        except Exception:
            logger.exception("Erro ao coletar métricas do Redis")
            return {"disponivel": False, "erro": "Redis inacessível"}

    # =========================================================
    # NEGÓCIO (visão rápida de uso da aplicação)
    # =========================================================
    @staticmethod
    def get_business_metrics():
        try:
            total_usuarios = User.query.filter_by(ativo=True).count()
            total_alunos = User.query.filter_by(ativo=True, tipo_usuario="aluno").count()
            total_professores = User.query.filter_by(ativo=True, tipo_usuario="professor").count()

            total_treinos = Treino.query.count()

            hoje = datetime.now(timezone.utc).date()
            registros_hoje = RegistroTreino.query.filter(
                db.func.date(RegistroTreino.data_registro) == hoje
            ).count()

            assinaturas_ativas = Assinatura.query.filter_by(status="active").count()
            assinaturas_inadimplentes = Assinatura.query.filter(
                Assinatura.status.in_(["past_due", "blocked"])
            ).count()
            assinaturas_trial = Assinatura.query.filter_by(status="trialing").count()

            return {
                "disponivel": True,
                "total_usuarios": total_usuarios,
                "total_alunos": total_alunos,
                "total_professores": total_professores,
                "total_treinos": total_treinos,
                "registros_hoje": registros_hoje,
                "assinaturas_ativas": assinaturas_ativas,
                "assinaturas_trial": assinaturas_trial,
                "assinaturas_inadimplentes": assinaturas_inadimplentes,
            }
        except Exception:
            logger.exception("Erro ao coletar métricas de negócio")
            return {"disponivel": False, "erro": "falha ao consultar métricas de negócio"}

    # =========================================================
    # AGREGADO -- usado tanto pela página quanto pelo endpoint JSON
    # de auto-atualização.
    # =========================================================
    @classmethod
    def get_all_metrics(cls):
        processo = cls.get_process_metrics()
        banco = cls.get_database_metrics()
        cache = cls.get_cache_metrics()
        negocio = cls.get_business_metrics()

        # Diagnóstico leve -- só booleanos e mensagens de erro (nunca
        # valores em si), pra dar pra investigar pelo log do Railway
        # sem expor dado nenhum da aplicação. Temporário enquanto
        # validamos o painel em produção; pode ser removido depois.
        logger.info(
            "Monitoramento coletado: processo=%s banco=%s(%s) cache=%s(%s) negocio=%s(%s)",
            processo.get("disponivel"),
            banco.get("disponivel"), banco.get("erro", ""),
            cache.get("disponivel"), cache.get("erro", ""),
            negocio.get("disponivel"), negocio.get("erro", ""),
        )

        return {
            "coletado_em": datetime.now(timezone.utc).isoformat(),
            "processo": processo,
            "banco": banco,
            "cache": cache,
            "negocio": negocio,
        }