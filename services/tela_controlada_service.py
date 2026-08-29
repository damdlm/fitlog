"""Serviço de telas controladas pelo admin (bloqueio dinâmico por
tela, ver models.py:TelaControlada)."""

from .base_service import CacheService
from models import db, TelaControlada
import logging

logger = logging.getLogger(__name__)

_CACHE_KEY = 'telas_controladas:bloqueadas'
_CACHE_TTL_SEGUNDOS = 300


class TelaControladaService:

    @staticmethod
    def esta_bloqueada(chave: str) -> bool:
        """Usado pelo decorator @acesso_premium_required(chave) a cada
        request -- por isso fica em cache (as chaves bloqueadas mudam
        raramente, só quando o admin salva a tela de configuração).
        Uma chave sem linha cadastrada é tratada como NÃO bloqueada
        (livre), nunca derruba a aplicação por uma tela nova que ainda
        não foi seedada."""
        bloqueadas = CacheService.get(_CACHE_KEY)
        if bloqueadas is None:
            bloqueadas = {
                t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=True).all()
            }
            CacheService.set(_CACHE_KEY, bloqueadas, ttl_seconds=_CACHE_TTL_SEGUNDOS)
        return chave in bloqueadas

    @staticmethod
    def listar_todas() -> list[TelaControlada]:
        """Pra tela de configuração do admin -- lê direto do banco
        (sem cache), lista pequena e a página já é só do admin."""
        return TelaControlada.query.order_by(TelaControlada.nome_exibicao).all()

    @staticmethod
    def atualizar(chaves_marcadas: set[str]) -> None:
        """Salva de uma vez o estado de bloqueio de TODAS as telas
        cadastradas, a partir do conjunto de chaves que vieram
        marcadas no formulário (checkbox marcado = bloqueia_sem_plano
        True). Uma tela cuja chave não está em `chaves_marcadas` fica
        livre. Invalida o cache em seguida -- a próxima leitura
        (próxima request de qualquer usuário) já pega o valor novo."""
        telas = TelaControlada.query.all()
        for tela in telas:
            tela.bloqueia_sem_plano = tela.chave in chaves_marcadas
        db.session.commit()
        CacheService.invalidate(_CACHE_KEY)
