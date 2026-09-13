"""Contagem agregada de acessos por tela e relatório "Telas mais
acessadas" do admin -- ver models.AcessoTela.

Registrado via app.after_request (ver app.py, hook
_registrar_acesso_tela) a cada navegação de página bem-sucedida.
Propositalmente privacy-first (ver docstring de AcessoTela): sabe
quantas vezes cada tela foi acessada por papel, nunca por usuário
específico.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from models import db, AcessoTela

logger = logging.getLogger(__name__)

# Endpoints técnicos que não são "telas" -- ruído que poluiria o
# relatório (chamadas de polling, health checks, assets etc.).
_ENDPOINTS_IGNORADOS = {
    "static", "service_worker", "health", "health_db",
    "robots_txt", "sitemap_xml", "llms_txt",
    "admin.api_monitoramento", "admin.api_monitoramento_historico",
}
_PREFIXOS_CAMINHO_IGNORADOS = ("/api/", "/static/", "/exercicios-media/")
_PAPEIS_VALIDOS = {"aluno", "professor", "admin", "anonimo"}


class AcessoTelaService:

    @staticmethod
    def deve_contar(endpoint, caminho):
        """True se esse request representa a navegação a uma "tela"
        de verdade -- filtra fora polling de API, estáticos e rotas
        técnicas que não interessam pro relatório."""
        if not endpoint or endpoint in _ENDPOINTS_IGNORADOS:
            return False
        if endpoint.startswith("api."):
            return False
        if caminho and caminho.startswith(_PREFIXOS_CAMINHO_IGNORADOS):
            return False
        return True

    @classmethod
    def registrar_acesso(cls, endpoint, papel, quando=None):
        """Incrementa em 1 o contador de hoje para (endpoint, papel).
        Best-effort: nunca propaga exceção -- uma falha aqui não pode
        derrubar a resposta normal da página."""
        if papel not in _PAPEIS_VALIDOS:
            papel = "anonimo"
        dia = quando or date.today()

        try:
            linha = AcessoTela.query.filter_by(endpoint=endpoint, papel=papel, data=dia).first()
            if linha:
                linha.contagem += 1
            else:
                db.session.add(AcessoTela(endpoint=endpoint, papel=papel, data=dia, contagem=1))
            db.session.commit()
        except IntegrityError:
            # Dois workers tentaram criar a mesma linha ao mesmo tempo
            # (primeiro acesso do dia a essa tela) -- o outro venceu,
            # só precisamos incrementar em cima do que já foi criado.
            db.session.rollback()
            try:
                linha = AcessoTela.query.filter_by(endpoint=endpoint, papel=papel, data=dia).first()
                if linha:
                    linha.contagem += 1
                    db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("AcessoTela: falha ao registrar acesso (retry) endpoint=%s", endpoint)
        except Exception:
            db.session.rollback()
            logger.exception("AcessoTela: falha ao registrar acesso endpoint=%s", endpoint)

    @staticmethod
    def _nome_amigavel(endpoint):
        """'aluno.versoes' -> 'Aluno · Versoes' -- só pra ficar mais
        legível na tabela do relatório, sem manter um dicionário de
        tradução pra cada endpoint (custo alto de manutenção)."""
        partes = endpoint.split(".")
        return " · ".join(p.replace("_", " ").title() for p in partes)

    @classmethod
    def get_relatorio(cls, dias=30):
        """Ranking de telas mais acessadas nos últimos `dias` dias,
        com o total por papel (aluno/professor/admin/anonimo)."""
        try:
            desde = date.today() - timedelta(days=dias)
            linhas = AcessoTela.query.filter(AcessoTela.data >= desde).all()

            por_endpoint = {}
            for l in linhas:
                agregado = por_endpoint.setdefault(l.endpoint, {
                    "endpoint": l.endpoint,
                    "nome_amigavel": cls._nome_amigavel(l.endpoint),
                    "total": 0,
                    "por_papel": {"aluno": 0, "professor": 0, "admin": 0, "anonimo": 0},
                })
                agregado["total"] += l.contagem
                agregado["por_papel"][l.papel] = agregado["por_papel"].get(l.papel, 0) + l.contagem

            telas = sorted(por_endpoint.values(), key=lambda t: t["total"], reverse=True)
            return {
                "disponivel": True,
                "dias": dias,
                "total_geral": sum(t["total"] for t in telas),
                "telas": telas,
            }
        except Exception:
            logger.exception("AcessoTela: falha ao montar relatório")
            return {"disponivel": False, "erro": "falha ao consultar acessos", "telas": []}
