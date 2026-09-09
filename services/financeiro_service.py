"""Serviço da tela financeira do admin (/admin/financeiro).

Duas fontes de dado bem separadas:

1. Local (tabela pagamentos_recebidos) -- histórico de cada cobrança
   confirmada, gravado por BillingService._registrar_pagamento_recebido
   a partir dos webhooks do Asaas. É daqui que vem o relatório por
   período/plano/forma de pagamento/tipo de usuário: são dados NOSSOS
   (plano, tipo de usuário) que o Asaas não conhece, então não dá pra
   pedir esse cruzamento diretamente pra API dele.

2. Asaas (API ao vivo) -- saldo disponível na conta (GET
   /finance/balance) e as taxas atualmente configuradas pra conta (GET
   /myAccount/fees). Consultado só quando a tela financeira é aberta
   (nunca em request de usuário comum), sempre com timeout curto.

Reaproveita BillingService._base_url()/_headers() (mesma API key,
mesmo ambiente sandbox/produção) em vez de duplicar a configuração.
"""

import logging
from datetime import datetime, timezone

import requests

from models import PagamentoRecebido, Plano
from services.billing_service import BillingService, REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class FinanceiroService:

    @staticmethod
    def resumo_periodo(data_inicio: datetime, data_fim: datetime) -> dict:
        """Agrega os pagamentos confirmados (tabela pagamentos_recebidos)
        entre data_inicio e data_fim (inclusive, comparado contra
        confirmado_em). Retorna totais gerais e três recortes -- por
        forma de pagamento, por plano e por tipo de usuário -- prontos
        pra tela renderizar sem lógica adicional.

        qtd_sem_taxa_conhecida conta pagamentos cujo webhook não trouxe
        netValue (taxa_asaas_centavos None) -- eles entram no total
        bruto mas não no total de taxas, então o admin sabe que o
        "total pago ao Asaas" pode estar subestimado nesse período."""
        pagamentos = (
            PagamentoRecebido.query
            .filter(PagamentoRecebido.confirmado_em >= data_inicio)
            .filter(PagamentoRecebido.confirmado_em <= data_fim)
            .all()
        )

        total_bruto = sum(p.valor_bruto_centavos for p in pagamentos)
        total_taxa = sum(p.taxa_asaas_centavos for p in pagamentos if p.taxa_asaas_centavos is not None)
        total_liquido = sum(p.valor_liquido_centavos for p in pagamentos if p.valor_liquido_centavos is not None)
        qtd_sem_taxa = sum(1 for p in pagamentos if p.taxa_asaas_centavos is None)

        por_forma = FinanceiroService._agrupar(pagamentos, lambda p: p.forma_pagamento or 'desconhecida')
        por_tipo_usuario = FinanceiroService._agrupar(pagamentos, lambda p: p.tipo_usuario or 'desconhecido')

        planos_por_codigo = {pl.codigo: pl.nome for pl in Plano.query.all()}
        agrupado_plano = FinanceiroService._agrupar(pagamentos, lambda p: p.plano_codigo or 'desconhecido')
        por_plano = [
            {**linha, 'nome': planos_por_codigo.get(linha['chave'], linha['chave'])}
            for linha in agrupado_plano
        ]

        return {
            'total_bruto_centavos': total_bruto,
            'total_taxa_centavos': total_taxa,
            'total_liquido_centavos': total_liquido,
            'qtd_pagamentos': len(pagamentos),
            'qtd_sem_taxa_conhecida': qtd_sem_taxa,
            'por_forma_pagamento': por_forma,
            'por_plano': por_plano,
            'por_tipo_usuario': por_tipo_usuario,
        }

    @staticmethod
    def _agrupar(pagamentos, chave_fn):
        grupos = {}
        for p in pagamentos:
            chave = chave_fn(p)
            grupo = grupos.setdefault(chave, {'chave': chave, 'total_centavos': 0, 'qtd': 0})
            grupo['total_centavos'] += p.valor_bruto_centavos
            grupo['qtd'] += 1
        return sorted(grupos.values(), key=lambda g: g['total_centavos'], reverse=True)

    @staticmethod
    def obter_saldo_asaas() -> dict:
        """GET /finance/balance -- saldo disponível na conta Asaas
        agora. Erros de rede/API não derrubam a tela financeira: o
        chamador recebe {'erro': ...} e mostra "indisponível" no lugar
        do valor, o resto da tela (dados locais) continua funcionando."""
        try:
            resp = requests.get(
                f'{BillingService._base_url()}/finance/balance',
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            dados = resp.json()
            saldo = dados.get('balance')
            return {'saldo_centavos': round(saldo * 100) if saldo is not None else None}
        except Exception:
            logger.exception('Falha ao consultar saldo da conta no Asaas')
            return {'erro': 'Não foi possível consultar o saldo no Asaas agora.'}

    @staticmethod
    def obter_taxas_conta_asaas() -> dict:
        """GET /myAccount/fees -- taxas atualmente aplicadas à conta
        (podem diferir da tabela padrão pública se o Asaas negociou
        condição especial). Mesma política de erro que obter_saldo_asaas."""
        try:
            resp = requests.get(
                f'{BillingService._base_url()}/myAccount/fees',
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return {'dados': resp.json()}
        except Exception:
            logger.exception('Falha ao consultar taxas da conta no Asaas')
            return {'erro': 'Não foi possível consultar as taxas da conta no Asaas agora.'}
