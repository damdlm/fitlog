"""Decoradores utilitários para a aplicação"""

from functools import wraps
from flask import current_app, request, flash, redirect, url_for
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