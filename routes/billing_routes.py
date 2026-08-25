"""Rotas de cobrança/assinatura (Asaas)."""

import logging
import re

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import limiter
from models import db, Plano
from services.billing_service import BillingService, DadosCobrancaIncompletosError

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
    """Tela de status da assinatura do usuário logado -- uma cobrança
    só (aluno OU professor). Aluno vê trial/ativa/bloqueada do Plano
    Fit. Professor vê o mesmo tipo de status, mas o plano em jogo pode
    ser Fit (até 2 alunos), Pró ou Premium (conforme a quantidade de
    alunos), com o botão de assinar sempre oferecendo o plano certo
    pra situação atual dele."""
    if not (current_user.is_aluno() or current_user.is_professor()):
        return redirect(url_for('main.index'))

    assinatura = current_user.assinatura
    contexto = dict(
        perfil='professor' if current_user.is_professor() else 'aluno',
        assinatura=assinatura,
        acesso_premium=assinatura.acesso_premium_ativo() if assinatura else False,
        cpf_cnpj=current_user.cpf_cnpj,
        telefone=current_user.telefone,
        endereco_cep=current_user.endereco_cep,
        endereco_numero=current_user.endereco_numero,
    )

    if current_user.is_professor():
        contexto['total_alunos'] = BillingService.contar_alunos_ativos(current_user)
        contexto['plano_gestao_necessario'] = BillingService.plano_gestao_necessario(current_user)
        contexto['plano_oferecido'] = BillingService.plano_recomendado_professor(current_user)
        contexto['acesso_alunos_liberado'] = BillingService.professor_acesso_alunos_liberado(current_user)
    else:
        contexto['plano_oferecido'] = Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()

    return render_template('billing/minha_assinatura.html', **contexto)


@billing_bp.route('/api/minha-assinatura')
@login_required
def api_minha_assinatura():
    """Mesma informação da tela acima, em JSON -- pra outras telas do
    front-end que precisam checar o status sem navegar pra cá (ex: um
    badge no menu)."""
    if not (current_user.is_aluno() or current_user.is_professor()):
        return redirect(url_for('main.index'))

    assinatura = current_user.assinatura
    resultado = {
        'status': assinatura.status if assinatura else 'sem_assinatura',
        'acesso_premium': assinatura.acesso_premium_ativo() if assinatura else False,
        'trial_termina_em': (
            assinatura.trial_termina_em.isoformat()
            if assinatura and assinatura.trial_termina_em else None
        ),
    }
    if current_user.is_professor():
        plano_necessario = BillingService.plano_gestao_necessario(current_user)
        resultado['plano_gestao_necessario'] = plano_necessario.codigo if plano_necessario else None
        resultado['acesso_alunos_liberado'] = BillingService.professor_acesso_alunos_liberado(current_user)

    return jsonify(resultado)


def _cpf_cnpj_valido(valor: str) -> str | None:
    """Valida o formato mínimo (só quantidade de dígitos -- 11 pra CPF,
    14 pra CNPJ) e devolve só os dígitos, sem pontuação. None se
    inválido. Não faz validação de dígito verificador -- se o número
    não existir de verdade, o próprio Asaas rejeita na hora de criar o
    cliente, e a mensagem de erro específica dele é melhor do que a
    gente tentar adivinhar a regra de validação por conta própria."""
    if not valor:
        return None
    digitos = re.sub(r'\D', '', valor)
    if len(digitos) in (11, 14):
        return digitos
    return None


def _cep_valido(valor: str) -> str | None:
    """8 dígitos, sem hífen. None se inválido."""
    if not valor:
        return None
    digitos = re.sub(r'\D', '', valor)
    return digitos if len(digitos) == 8 else None


def _telefone_valido(valor: str) -> str | None:
    """10 ou 11 dígitos (fixo ou celular, com DDD), sem pontuação.
    None se inválido."""
    if not valor:
        return None
    digitos = re.sub(r'\D', '', valor)
    return digitos if len(digitos) in (10, 11) else None


@billing_bp.route('/assinar', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def assinar():
    """Inicia (ou reaproveita) o checkout hospedado do Asaas e
    redireciona o navegador pra lá -- protegido por CSRF normal (essa
    view não está na lista de exceção em routes/__init__.py, só o
    webhook está). Uma assinatura só por usuário: o plano oferecido é
    sempre o certo pra situação atual (Fit pro aluno; Fit, Pró ou
    Premium pro professor, conforme a quantidade de alunos -- ver
    BillingService.plano_recomendado_professor).

    Pede CPF/CNPJ, telefone, CEP e número do endereço antes de tentar o
    checkout -- todos exigidos pelo Asaas pra gerar cobrança de cartão
    recorrente de verdade (confirmado pela própria API, não é chute):
    Receita Federal exige documento; endereço/telefone são exigidos
    especificamente pro checkout RECURRENT+CREDIT_CARD. Nunca pedimos
    isso no cadastro pra não criar fricção -- só na primeira vez que
    tenta assinar; depois fica salvo no usuário."""
    campos_faltando = BillingService.campos_cobranca_faltando(current_user)
    if campos_faltando:
        cpf_cnpj = _cpf_cnpj_valido(request.form.get('cpf_cnpj', '')) if 'cpf_cnpj' in campos_faltando else current_user.cpf_cnpj
        telefone = _telefone_valido(request.form.get('telefone', '')) if 'telefone' in campos_faltando else current_user.telefone
        cep = _cep_valido(request.form.get('endereco_cep', '')) if 'endereco_cep' in campos_faltando else current_user.endereco_cep
        numero = request.form.get('endereco_numero', '').strip() if 'endereco_numero' in campos_faltando else current_user.endereco_numero

        if not (cpf_cnpj and telefone and cep and numero):
            flash('Preencha CPF/CNPJ, telefone, CEP e número do endereço para continuar -- são exigidos para gerar a cobrança.', 'warning')
            return redirect(url_for('billing.minha_assinatura'))

        current_user.cpf_cnpj = cpf_cnpj
        current_user.telefone = telefone
        current_user.endereco_cep = cep
        current_user.endereco_numero = numero
        db.session.commit()

    if current_user.is_aluno():
        plano = Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()
    elif current_user.is_professor():
        plano = BillingService.plano_recomendado_professor(current_user)
    else:
        return redirect(url_for('main.index'))

    if plano is None:
        logger.error('Nenhum plano encontrado/ativo pra oferecer ao usuário %s -- checar seed de planos', current_user.id)
        flash('Não foi possível iniciar a assinatura agora. Tente novamente em instantes.', 'danger')
        return redirect(url_for('billing.minha_assinatura'))

    try:
        checkout_url = BillingService.criar_assinatura_checkout(current_user, plano)
    except DadosCobrancaIncompletosError:
        # Não deveria acontecer (já validamos acima), mas cobre
        # qualquer chamada futura a este método vinda de outro lugar.
        flash('Preencha CPF/CNPJ, telefone, CEP e número do endereço para continuar.', 'warning')
        return redirect(url_for('billing.minha_assinatura'))
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
