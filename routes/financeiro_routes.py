"""Painel financeiro do admin (/admin/financeiro).

Além do @admin_required de sempre, esta área exige uma reautenticação
por senha própria (ver `_financeiro_desbloqueado`) antes de mostrar
qualquer número -- é informação confidencial (faturamento, saldo na
conta Asaas). Sem tolerância de tempo: o desbloqueio vale só enquanto
o admin continua DENTRO da área financeira (recarregar a página ou
trocar o filtro de datas não pede senha de novo) e é derrubado assim
que ele navega para qualquer página fora daqui -- ver o hook
`_financeiro_expira_ao_sair` em app.py, que limpa esse mesmo flag de
sessão a cada request GET fora do blueprint `financeiro`. Sair da tela
e voltar sempre pede usuário e senha de novo.
"""

import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import current_user
from datetime import datetime, timezone

from extensions import limiter
from services.financeiro_service import FinanceiroService
from utils.decorators import admin_required

logger = logging.getLogger(__name__)
financeiro_bp = Blueprint('financeiro', __name__)

SESSION_KEY = 'financeiro_desbloqueado'


def _financeiro_desbloqueado() -> bool:
    return session.get(SESSION_KEY) is True


@financeiro_bp.route('/login', methods=['GET', 'POST'])
@admin_required
@limiter.limit('10 per minute')
def login():
    """Reautenticação dedicada -- pede usuário e senha de novo mesmo
    já estando logado como admin, exatamente como uma tela de dados
    confidenciais deve exigir. Confere usuário E senha (não só a
    senha) para reduzir o risco de alguém digitar sem perceber que a
    sessão aberta é de outro admin."""
    if _financeiro_desbloqueado():
        return redirect(url_for('financeiro.painel'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if username != current_user.username or not current_user.check_password(password):
            flash('Usuário ou senha incorretos.', 'danger')
            return render_template('admin/financeiro_login.html'), 401

        session[SESSION_KEY] = True
        return redirect(url_for('financeiro.painel'))

    return render_template('admin/financeiro_login.html')


@financeiro_bp.route('/')
@admin_required
def painel():
    if not _financeiro_desbloqueado():
        return redirect(url_for('financeiro.login'))

    hoje = datetime.now(timezone.utc)
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return render_template(
        'admin/financeiro.html',
        data_inicio_padrao=inicio_mes.strftime('%Y-%m-%d'),
        data_fim_padrao=hoje.strftime('%Y-%m-%d'),
    )


@financeiro_bp.route('/api/resumo')
@admin_required
def api_resumo():
    """Chamada via fetch() pelo JS da tela -- devolve o resumo do
    período em JSON. Continua exigindo o desbloqueio da reautenticação
    (não só admin_required): sem isso, alguém com a URL da API em mãos
    driblaria a tela de senha."""
    if not _financeiro_desbloqueado():
        return jsonify({'erro': 'reautenticacao_necessaria'}), 401

    data_inicio_str = request.args.get('data_inicio', '')
    data_fim_str = request.args.get('data_fim', '')
    try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    except ValueError:
        return jsonify({'erro': 'Datas inválidas.'}), 400

    if data_inicio > data_fim:
        return jsonify({'erro': 'Data inicial não pode ser depois da data final.'}), 400

    resumo = FinanceiroService.resumo_periodo(data_inicio, data_fim)
    saldo = FinanceiroService.obter_saldo_asaas()

    return jsonify({'resumo': resumo, 'saldo': saldo})
