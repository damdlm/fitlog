"""Registro de todos os blueprints da aplicação"""

import logging
from .main_routes import main_bp
from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .register_routes import register_bp
from .stats_routes import stats_bp
from .api_routes import api_bp
from .calendar_routes import calendar_bp
from .professor_routes import professor_bp
from .aluno import aluno_bp          # ← módulo modular, não o arquivo antigo
from .fitbot_routes import fitbot_bp
from .contato_routes import contato_bp
from .billing_routes import billing_bp

logger = logging.getLogger(__name__)

def register_all_routes(app):
    """Registra todos os blueprints no app Flask"""
    blueprints = [
        (main_bp, ''),
        (auth_bp, '/auth'),
        (admin_bp, '/admin'),
        (professor_bp, '/professor'),
        (aluno_bp, '/aluno'),
        (calendar_bp, '/calendar'),
        (register_bp, '/registrar'),
        (stats_bp, '/estatisticas'),
        (api_bp, '/api'),
        (fitbot_bp, '/fitbot'),
        (contato_bp, '/contato'),
        (billing_bp, '/billing'),
    ]
    
    for blueprint, url_prefix in blueprints:
        try:
            app.register_blueprint(blueprint, url_prefix=url_prefix)
            app.logger.info(f"Blueprint {blueprint.name} registrado em {url_prefix or '/'}")
        except Exception:
            app.logger.exception(f"Erro ao registrar {blueprint.name}")

    # A rota de webhook é chamada pelo servidor do Asaas, não pelo
    # navegador de um usuário logado -- não existe token CSRF de sessão
    # possível nesse cenário. A autenticidade é garantida à parte, pelo
    # token 'asaas-access-token' validado dentro da própria rota (ver
    # routes/billing_routes.py). csrf.exempt é aplicado aqui, depois do
    # blueprint já registrado, em vez de no módulo da rota, para não
    # precisar importar o objeto csrf (definido em app.py) de dentro de
    # routes/billing_routes.py.
    from app import csrf
    csrf.exempt(app.view_functions['billing.webhook_asaas'])