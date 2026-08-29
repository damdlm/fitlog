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

def acesso_premium_required(tela_chave):
    """Decorator para telas que o admin pode escolher bloquear (ver
    models.py:TelaControlada) -- bloqueia aluno OU professor sem trial
    válido nem assinatura ativa (Fit, Pró ou Premium: qualquer uma
    libera -- ver services/billing_service.py:usuario_tem_acesso_
    premium), mas SÓ se a tela em questão estiver marcada como
    bloqueada pelo admin (services/tela_controlada_service.py). Uma
    tela livre nunca bloqueia ninguém, mesmo sem plano nenhum.

    tela_chave é o identificador estável da tela (ver seed na migration
    de telas_controladas) -- uso: @acesso_premium_required('estatisticas').

    Só admin nunca é bloqueado aqui."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Faça login para acessar esta página.', 'warning')
                return redirect(url_for('auth.login'))

            if current_user.is_admin:
                return f(*args, **kwargs)

            from services.tela_controlada_service import TelaControladaService
            if not TelaControladaService.esta_bloqueada(tela_chave):
                return f(*args, **kwargs)

            from services.billing_service import BillingService
            if not BillingService.usuario_tem_acesso_premium(current_user):
                # Endpoints chamados via fetch/JS (ex: /api/progresso na
                # tela de Estatísticas, ou /calendar/api/eventos na tela
                # de Calendário) não podem devolver um redirect para uma
                # página HTML de login -- o JS do front-end tentaria
                # fazer JSON.parse() nisso e quebraria silenciosamente.
                # '/api/' aparece no path tanto nas rotas do blueprint
                # 'api' quanto nas sub-rotas /api/... de outros
                # blueprints (calendar, etc) -- cobre os dois casos numa
                # checagem só. Telas normais (HTML) continuam com flash
                # + redirect, como o resto da aplicação.
                if request.blueprint == 'api' or '/api/' in request.path:
                    return jsonify({'erro': 'assinatura_necessaria'}), 403
                flash('Assine o Plano Fit para continuar acessando esta área.', 'warning')
                return redirect(url_for('billing.minha_assinatura'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def professor_acesso_alunos_required(f):
    """Decorator para as telas do professor que operam sobre um aluno
    específico (ver rotas com <int:aluno_id> em professor_routes.py) --
    bloqueia quando o professor já passou da faixa gratuita (mais de 2
    alunos, exigindo Pró/Premium) e está com a assinatura 'blocked'
    (carência de 15 dias de atraso esgotada -- ver
    services/billing_service.py:professor_acesso_alunos_liberado). O
    vínculo com os alunos não é apagado, só o acesso às telas.

    Só bloqueia professor -- aluno e admin nunca são afetados aqui (a
    checagem de posse do aluno em si continua sendo feita dentro de
    cada view, este decorator só cuida da cobrança)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))

        if current_user.is_admin or not current_user.is_professor():
            return f(*args, **kwargs)

        from services.billing_service import BillingService
        if not BillingService.professor_acesso_alunos_liberado(current_user):
            flash('Regularize o pagamento do seu plano para voltar a acessar seus alunos.', 'warning')
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