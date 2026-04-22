"""Middleware para logging de requisições"""

import time
from flask import request, g
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware:
    """Middleware que loga todas as requisições"""
    
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        start_time = time.time()
        
        def custom_start_response(status, headers, exc_info=None):
            # Calcular tempo de resposta
            duration = time.time() - start_time
            
            # Logar requisição
            logger.info(
                f"Request: {environ.get('REQUEST_METHOD')} {environ.get('PATH_INFO')} - "
                f"Status: {status} - Duration: {duration:.3f}s"
            )
            
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)

def setup_middleware(app):
    """Configura middlewares da aplicação"""
    app.wsgi_app = LoggingMiddleware(app.wsgi_app)