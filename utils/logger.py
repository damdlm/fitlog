"""Configuração de logging da aplicação"""

import logging
from flask import request, session, has_request_context

class RequestFormatter(logging.Formatter):
    """Formatter personalizado que inclui dados da requisição"""
    
    def format(self, record):
        if has_request_context():
            record.url = request.url
            record.method = request.method
            record.ip = request.remote_addr
            record.user_id = session.get('user_id', 'anonymous')
            record.user_agent = request.user_agent.string
        else:
            record.url = None
            record.method = None
            record.ip = None
            record.user_id = 'cli'
            record.user_agent = None
        
        return super().format(record)

def setup_logging(app):
    """Configura logging para a aplicação"""
    import os
    from logging.handlers import RotatingFileHandler
    
    # Criar diretório de logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Formato do log
    log_format = '%(asctime)s - %(levelname)s - [%(user_id)s] - %(method)s %(url)s - %(message)s'
    
    # Handler para arquivo
    file_handler = RotatingFileHandler(
        'logs/fitlog.log', 
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(RequestFormatter(log_format))
    file_handler.setLevel(logging.INFO)
    
    # Handler para console (apenas em desenvolvimento)
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(RequestFormatter(log_format))
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    
    app.logger.info("Logging configurado com sucesso")