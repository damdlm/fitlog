"""Rotas de cobrança/assinatura (Asaas)."""

import logging

from flask import Blueprint, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from extensions import limiter
from services.billing_service import BillingService

billing_bp = Blueprint('billing', __name__)
logger = logging.getLogger(__name__)


@billing_bp.route('/webhook/asaas', methods=['POST'])
@limiter.limit("120 per minute")
def webhook_asaas():
    """Recebe eventos do Asaas. NUNCA exige login nem CSRF (ver
    csrf.exempt aplicado a este blueprint em routes/__init__.py) --
    quem chama essa rota é o servidor do Asaas, não o navegador de um
    usuário logado. A autenticidade é garantida só pelo token no header
    'asaas-access-token', comparado em tempo constante -- ver
    BillingService._validar_token_webhook.
    """
    token_recebido = request.headers.get('asaas-access-token', '')
    if not BillingService._validar_token_webhook(token_recebido):
        logger.warning('Webhook Asaas com token inválido/ausente, rejeitado (IP %s)', request.remote_addr)
        return jsonify({'erro': 'token inválido'}), 401

    payload = request.get_json(silent=True) or {}
    ok = BillingService.processar_webhook(payload)
    # Sempre 200 quando processado (mesmo se o evento não exigia ação
    # nenhuma) -- devolver erro faria o Asaas ficar reenviando o mesmo
    # evento à toa. Só payload malformado retorna 400.
    return jsonify({'ok': ok}), 200 if ok else 400


@billing_bp.route('/minha-assinatura')
@login_required
def minha_assinatura():
    """Status da assinatura do usuário logado. Por ora devolve JSON
    (a tela/template fica para uma etapa seguinte, depois de validar o
    modelo de dados e o fluxo de webhook)."""
    if current_user.is_aluno():
        assinatura = current_user.assinatura
        if assinatura is None:
            return jsonify({'status': 'sem_assinatura'})
        return jsonify({
            'status': assinatura.status,
            'acesso_premium': assinatura.acesso_premium_ativo(),
            'trial_termina_em': assinatura.trial_termina_em.isoformat() if assinatura.trial_termina_em else None,
        })

    if current_user.is_professor():
        tier = BillingService.calcular_tier_professor(current_user)
        return jsonify({
            'tier_atual': tier.codigo if tier else 'gratuito',
            'preco_centavos': tier.preco_centavos if tier else 0,
        })

    return redirect(url_for('main.index'))
