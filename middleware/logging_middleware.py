"""Middleware para logging de requisições"""

import time
import logging
from flask import request

logger = logging.getLogger(__name__)

class LoggingMiddleware:
    """Middleware que loga todas as requisições"""
    
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        start_time = time.time()
        
        # Guarda o método e path antes de qualquer coisa
        method = environ.get('REQUEST_METHOD', 'UNKNOWN')
        path = environ.get('PATH_INFO', '/')
        
        def custom_start_response(status, headers, exc_info=None):
            # Calcular tempo de resposta
            duration = time.time() - start_time
            
            # Logar requisição APÓS a resposta estar pronta
            logger.info(f"Request: {method} {path} - Status: {status} - Duration: {duration:.3f}s")
            
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)

def setup_middleware(app):
    """Configura middlewares da aplicação"""
    # Desabilitar temporariamente o middleware para teste
    # app.wsgi_app = LoggingMiddleware(app.wsgi_app)
    
    # Opção: middleware mais simples sem logging complexo
    @app.after_request
    def log_request(response):
        duration = time.time() - request.start_time if hasattr(request, 'start_time') else 0
        logger.info(f"Request: {request.method} {request.path} - Status: {response.status_code} - Duration: {duration:.3f}s")
        return response
    
    @app.before_request
    def start_timer():
        request.start_time = time.time()
