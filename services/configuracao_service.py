"""Serviço da flag global de cobrança (ver models.py:ConfiguracaoApp)
-- liga/desliga o modo "app grátis" de lançamento, sem precisar de
deploy nem migration."""

from .base_service import CacheService
from models import db, ConfiguracaoApp
import logging

logger = logging.getLogger(__name__)

_CACHE_KEY = 'configuracao_app:cobranca_ativa'
_CACHE_TTL_SEGUNDOS = 300


class ConfiguracaoService:

    @staticmethod
    def _obter_ou_criar() -> ConfiguracaoApp:
        """Sempre a linha id=1 (singleton) -- cria com cobranca_ativa=
        True se por algum motivo ainda não existir (ambiente novo sem
        rodar a migration de seed, testes, etc.), nunca derruba a
        aplicação por causa disso."""
        config = ConfiguracaoApp.query.get(1)
        if config is None:
            config = ConfiguracaoApp(id=1, cobranca_ativa=True)
            db.session.add(config)
            db.session.commit()
        return config

    @staticmethod
    def cobranca_ativa() -> bool:
        """Único ponto de verdade consultado por
        BillingService.usuario_tem_acesso_premium,
        pode_cadastrar_aluno e professor_acesso_alunos_liberado --
        chamado a cada request que checa acesso, por isso cacheado
        (muda raramente, só quando o admin mexe no toggle).
        False = modo grátis: essas três checagens liberam tudo, sem
        exigir plano nem cobrar nada."""
        valor = CacheService.get(_CACHE_KEY)
        if valor is None:
            valor = ConfiguracaoService._obter_ou_criar().cobranca_ativa
            CacheService.set(_CACHE_KEY, valor, ttl_seconds=_CACHE_TTL_SEGUNDOS)
        return valor

    @staticmethod
    def set_cobranca_ativa(ativa: bool) -> None:
        """Chamado pela tela /admin/telas-controladas. Invalida o
        cache em seguida -- a próxima leitura (próxima request de
        qualquer usuário) já pega o valor novo."""
        config = ConfiguracaoService._obter_ou_criar()
        config.cobranca_ativa = ativa
        db.session.commit()
        CacheService.invalidate(_CACHE_KEY)
        logger.info('Cobrança %s pelo admin (modo %s)', 'ativada' if ativa else 'desativada', 'normal' if ativa else 'grátis')
