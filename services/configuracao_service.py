"""Serviço das flags globais de configuração (ver
models.py:ConfiguracaoApp) -- liga/desliga o modo "app grátis" de
lançamento e a visibilidade da tela de assinatura, sem precisar de
deploy nem migration."""

from .base_service import CacheService
from models import db, ConfiguracaoApp
import logging

logger = logging.getLogger(__name__)

_CACHE_KEY_COBRANCA = 'configuracao_app:cobranca_ativa'
_CACHE_KEY_TELA_ASSINATURA = 'configuracao_app:tela_assinatura_ativa'
_CACHE_TTL_SEGUNDOS = 300


class ConfiguracaoService:

    @staticmethod
    def _obter_ou_criar() -> ConfiguracaoApp:
        """Sempre a linha id=1 (singleton) -- cria com os valores
        padrão (cobrança e tela de assinatura ativas) se por algum
        motivo ainda não existir (ambiente novo sem rodar a migration
        de seed, testes, etc.), nunca derruba a aplicação por causa
        disso."""
        config = ConfiguracaoApp.query.get(1)
        if config is None:
            config = ConfiguracaoApp(id=1, cobranca_ativa=True, tela_assinatura_ativa=True)
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
        valor = CacheService.get(_CACHE_KEY_COBRANCA)
        if valor is None:
            valor = ConfiguracaoService._obter_ou_criar().cobranca_ativa
            CacheService.set(_CACHE_KEY_COBRANCA, valor, ttl_seconds=_CACHE_TTL_SEGUNDOS)
        return valor

    @staticmethod
    def set_cobranca_ativa(ativa: bool) -> None:
        """Chamado pela tela /admin/telas-controladas. Invalida o
        cache em seguida -- a próxima leitura (próxima request de
        qualquer usuário) já pega o valor novo."""
        config = ConfiguracaoService._obter_ou_criar()
        config.cobranca_ativa = ativa
        db.session.commit()
        CacheService.invalidate(_CACHE_KEY_COBRANCA)
        logger.info('Cobrança %s pelo admin (modo %s)', 'ativada' if ativa else 'desativada', 'normal' if ativa else 'grátis')

    @staticmethod
    def tela_assinatura_ativa() -> bool:
        """Independente de cobranca_ativa -- controla só se a tela
        "Minha Assinatura" (e o link dela no menu) aparece pra quem
        não é admin. Ver routes/billing_routes.py. Cacheado pelo
        mesmo motivo de cobranca_ativa (lido a cada request via
        context processor pro menu)."""
        valor = CacheService.get(_CACHE_KEY_TELA_ASSINATURA)
        if valor is None:
            valor = ConfiguracaoService._obter_ou_criar().tela_assinatura_ativa
            CacheService.set(_CACHE_KEY_TELA_ASSINATURA, valor, ttl_seconds=_CACHE_TTL_SEGUNDOS)
        return valor

    @staticmethod
    def set_tela_assinatura_ativa(ativa: bool) -> None:
        """Chamado pela tela /admin/telas-controladas."""
        config = ConfiguracaoService._obter_ou_criar()
        config.tela_assinatura_ativa = ativa
        db.session.commit()
        CacheService.invalidate(_CACHE_KEY_TELA_ASSINATURA)
        logger.info('Tela de assinatura %s pelo admin', 'ativada' if ativa else 'desativada')
