"""Decoradores utilitários para a aplicação"""

from functools import wraps
from flask import current_app, request, flash, jsonify, redirect, url_for
from flask_login import current_user
import time
import logging

logger = logging.getLogger(__name__)

def with_app_context(f):
    """Decorator para garantir que a função execute com contexto de app"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app:
            from app import create_app
            app = create_app()
            with app.app_context():
                return f(*args, **kwargs)
        return f(*args, **kwargs)
    return decorated_function

def log_execution_time(f):
    """Decorator para logar o tempo de execução de uma função"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        logger.debug(f"{f.__name__} executado em {end_time - start_time:.3f}s")
        return result
    return decorated_function

def admin_required(f):
    """Decorator para verificar se usuário é admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash('Acesso negado. Área restrita para administradores.', 'danger')
            return redirect(url_for('main.index'))
        
        return f(*args, **kwargs)
    return decorated_function

def professor_required(f):
    """Decorator para verificar se usuário é professor ou admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not (current_user.is_admin or current_user.is_professor()):
            flash('Acesso negado. Área restrita para professores.', 'danger')
            return redirect(url_for('main.index'))
        
        return f(*args, **kwargs)
    return decorated_function

def aluno_required(f):
    """Decorator para verificar se usuário é aluno ou admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not (current_user.is_admin or current_user.is_aluno()):
            flash('Acesso negado. Área restrita para alunos.', 'danger')
            return redirect(url_for('main.index'))
        
        return f(*args, **kwargs)
    return decorated_function

def aluno_premium_required(f):
    """Decorator para telas premium do aluno (Estatísticas, FitBot) --
    bloqueia aluno sem trial válido nem assinatura ativa (ver
    services/billing_service.py:aluno_tem_acesso_premium). Lê só o
    banco local (uma query O(1) por FK única em usuario_id), nunca
    chama o gateway de pagamento a cada requisição.

    Professor e admin nunca são bloqueados aqui -- a regra de cobrança
    do Plano Fit é só para aluno; o professor tem sua própria regra
    (tier por quantidade de alunos), tratada à parte."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))

        if current_user.is_admin or current_user.is_professor():
            return f(*args, **kwargs)

        from services.billing_service import BillingService
        if not BillingService.aluno_tem_acesso_premium(current_user):
            # Endpoints de API (ex: /api/progresso, que alimenta o
            # gráfico da tela de Estatísticas via fetch) não podem
            # devolver um redirect para uma página HTML de login -- o
            # JS do front-end tentaria fazer JSON.parse() nisso e
            # quebraria silenciosamente. Telas normais continuam com
            # flash + redirect, como o resto da aplicação.
            if request.blueprint == 'api':
                return jsonify({'erro': 'assinatura_necessaria'}), 403
            flash('Assine o Plano Fit para continuar acessando esta área.', 'warning')
            return redirect(url_for('billing.minha_assinatura'))

        return f(*args, **kwargs)
    return decorated_function


def owner_or_admin(model_getter):
    """
    Decorator para verificar se o usuário atual é o dono do recurso ou admin.
    model_getter: função que recebe os args/kwargs e retorna o objeto com atributo 'user_id'.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Faça login para acessar esta página.', 'warning')
                return redirect(url_for('auth.login'))
            
            if current_user.is_admin:
                return f(*args, **kwargs)
            
            obj = model_getter(*args, **kwargs)
            if not obj:
                flash('Recurso não encontrado.', 'danger')
                return redirect(url_for('main.index'))
            
            if hasattr(obj, 'user_id') and obj.user_id == current_user.id:
                return f(*args, **kwargs)
            
            if hasattr(obj, 'usuario_id') and obj.usuario_id == current_user.id:
                return f(*args, **kwargs)
            
            flash('Você não tem permissão para acessar este recurso.', 'danger')
            return redirect(url_for('main.index'))
        return decorated_function
    return decorator

def versao_ativa_required(f):
    """Decorator para verificar se existe versão ativa"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from services.versao_service import VersaoService
        
        versao_ativa = VersaoService.get_ativa()
        if not versao_ativa:
            flash('Não há versão ativa. Crie uma versão primeiro.', 'warning')
            return redirect(url_for('version.gerenciar_versoes_global'))
        
        return f(*args, **kwargs)
    return decorated_function