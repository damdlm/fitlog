"""Rotas de cobrança/assinatura (Asaas)."""

import logging

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import limiter
from models import Plano
from services.billing_service import BillingService

billing_bp = Blueprint('billing', __name__)
logger = logging.getLogger(__name__)


@billing_bp.route('/webhook/asaas', methods=['POST'])
@limiter.limit("120 per minute")
def webhook_asaas():
    """Recebe eventos do Asaas. NUNCA exige login nem CSRF (ver
    csrf.exempt aplicado a esta view em routes/__init__.py) -- quem
    chama essa rota é o servidor do Asaas, não o navegador de um
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
    """Tela de status da assinatura do usuário logado -- aluno vê
    trial/ativa/bloqueada com botão de assinar; professor vê o tier
    atual calculado pela contagem de alunos, com botão de assinar
    quando deve e ainda não está pago."""
    if current_user.is_aluno():
        assinatura = current_user.assinatura
        plano = Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()
        return render_template(
            'billing/minha_assinatura.html',
            perfil='aluno',
            assinatura=assinatura,
            acesso_premium=assinatura.acesso_premium_ativo() if assinatura else False,
            plano=plano,
        )

    if current_user.is_professor():
        tier = BillingService.calcular_tier_professor(current_user)
        total_alunos = BillingService.contar_alunos_ativos(current_user)
        situacao = BillingService.situacao_conta(current_user)
        return render_template(
            'billing/minha_assinatura.html',
            perfil='professor',
            tier=tier,
            situacao=situacao,
            total_alunos=total_alunos,
        )

    return redirect(url_for('main.index'))


@billing_bp.route('/api/minha-assinatura')
@login_required
def api_minha_assinatura():
    """Mesma informação da tela acima, em JSON -- pra outras telas do
    front-end que precisam checar o status sem navegar pra cá (ex: um
    badge no menu)."""
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


@billing_bp.route('/assinar', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def assinar():
    """Inicia (ou reaproveita) o checkout hospedado do Asaas e
    redireciona o navegador pra lá -- protegido por CSRF normal (essa
    view não está na lista de exceção em routes/__init__.py, só o
    webhook está)."""
    if current_user.is_aluno():
        plano = Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()
        if plano is None:
            logger.error('Plano aluno_fit não encontrado/ativo -- checar seed de planos')
            flash('Não foi possível iniciar a assinatura agora. Tente novamente em instantes.', 'danger')
            return redirect(url_for('billing.minha_assinatura'))
    elif current_user.is_professor():
        plano = BillingService.calcular_tier_professor(current_user)
        if plano is None:
            flash('Você ainda está na faixa gratuita (até 2 alunos) -- não há cobrança a fazer.', 'info')
            return redirect(url_for('billing.minha_assinatura'))
    else:
        return redirect(url_for('main.index'))

    try:
        checkout_url = BillingService.criar_assinatura_checkout(current_user, plano)
    except RuntimeError:
        # ASAAS_API_KEY não configurada -- erro de operação, não do
        # usuário. Já logado dentro de BillingService.
        flash('Cobrança ainda não está disponível. Tente novamente mais tarde.', 'danger')
        return redirect(url_for('billing.minha_assinatura'))
    except requests.RequestException:
        logger.exception('Falha ao criar checkout Asaas para usuário %s', current_user.id)
        flash('Não foi possível conectar ao sistema de pagamento agora. Tente novamente.', 'danger')
        return redirect(url_for('billing.minha_assinatura'))

    if not checkout_url:
        logger.error('Asaas não retornou URL de checkout para usuário %s', current_user.id)
        flash('Não foi possível gerar o link de pagamento. Tente novamente.', 'danger')
        return redirect(url_for('billing.minha_assinatura'))

    return redirect(checkout_url)
