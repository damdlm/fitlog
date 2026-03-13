"""Repositório base com operações comuns"""

from models import db
from flask_login import current_user
import logging

logger = logging.getLogger(__name__)

class BaseRepository:
    """Classe base para todos os repositórios"""
    
    def __init__(self, model_class):
        """
        Inicializa o repositório com a classe do modelo
        
        Args:
            model_class: Classe do modelo SQLAlchemy
        """
        self.model_class = model_class
    
    def get_current_user_id(self):
        """Retorna ID do usuário atual"""
        return current_user.id if current_user and current_user.is_authenticated else None
    
    def filter_by_user(self, query, user_id=None):
        """
        Aplica filtro de usuário à query se o modelo tiver user_id
        
        Args:
            query: Query SQLAlchemy
            user_id: ID do usuário (opcional)
        
        Returns:
            Query filtrada
        """
        if user_id is None:
            user_id = self.get_current_user_id()
        
        if user_id and hasattr(self.model_class, 'user_id'):
            return query.filter_by(user_id=user_id)
        
        return query
    
    def get_all(self, user_id=None, order_by=None):
        """
        Retorna todos os registros
        
        Args:
            user_id: ID do usuário (opcional)
            order_by: Campo para ordenação (opcional)
        
        Returns:
            Lista de registros
        """
        try:
            query = self.model_class.query
            query = self.filter_by_user(query, user_id)
            
            if order_by:
                query = query.order_by(order_by)
            
            return query.all()
        except Exception as e:
            logger.error(f"Erro em get_all ({self.model_class.__name__}): {e}")
            return []
    
    def get_by_id(self, id, user_id=None):
        """
        Retorna registro por ID
        
        Args:
            id: ID do registro
            user_id: ID do usuário (opcional)
        
        Returns:
            Registro ou None
        """
        try:
            query = self.model_class.query.filter_by(id=id)
            query = self.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            logger.error(f"Erro em get_by_id {id} ({self.model_class.__name__}): {e}")
            return None
    
    def create(self, **kwargs):
        """
        Cria um novo registro
        
        Args:
            **kwargs: Atributos do registro
        
        Returns:
            Instância criada ou None
        """
        try:
            # Adicionar user_id se não fornecido e modelo tiver o campo
            if 'user_id' not in kwargs and hasattr(self.model_class, 'user_id'):
                kwargs['user_id'] = self.get_current_user_id()
            
            instance = self.model_class(**kwargs)
            db.session.add(instance)
            db.session.commit()
            
            logger.info(f"Registro criado em {self.model_class.__name__}: ID {instance.id}")
            return instance
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro em create ({self.model_class.__name__}): {e}")
            return None
    
    def update(self, instance, **kwargs):
        """
        Atualiza um registro existente
        
        Args:
            instance: Instância a ser atualizada
            **kwargs: Atributos a serem atualizados
        
        Returns:
            Instância atualizada ou None
        """
        try:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            db.session.commit()
            logger.info(f"Registro atualizado em {self.model_class.__name__}: ID {instance.id}")
            return instance
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro em update ({self.model_class.__name__}): {e}")
            return None
    
    def delete(self, instance):
        """
        Remove um registro
        
        Args:
            instance: Instância a ser removida
        
        Returns:
            bool: True se sucesso, False caso contrário
        """
        try:
            db.session.delete(instance)
            db.session.commit()
            logger.info(f"Registro excluído em {self.model_class.__name__}: ID {instance.id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro em delete ({self.model_class.__name__}): {e}")
            return False
    
    def delete_by_id(self, id, user_id=None):
        """
        Remove um registro por ID
        
        Args:
            id: ID do registro
            user_id: ID do usuário (opcional)
        
        Returns:
            bool: True se sucesso, False caso contrário
        """
        instance = self.get_by_id(id, user_id)
        if instance:
            return self.delete(instance)
        return False
    
    def count(self, user_id=None):
        """
        Retorna quantidade de registros
        
        Args:
            user_id: ID do usuário (opcional)
        
        Returns:
            int: Quantidade de registros
        """
        try:
            query = self.model_class.query
            query = self.filter_by_user(query, user_id)
            return query.count()
        except Exception as e:
            logger.error(f"Erro em count ({self.model_class.__name__}): {e}")
            return 0
    
    def exists(self, id, user_id=None):
        """
        Verifica se um registro existe
        
        Args:
            id: ID do registro
            user_id: ID do usuário (opcional)
        
        Returns:
            bool: True se existe
        """
        return self.get_by_id(id, user_id) is not None
    
    def bulk_create(self, instances_data):
        """
        Cria múltiplos registros em lote
        
        Args:
            instances_data: Lista de dicionários com dados
        
        Returns:
            list: Lista de instâncias criadas
        """
        try:
            instances = []
            for data in instances_data:
                if 'user_id' not in data and hasattr(self.model_class, 'user_id'):
                    data['user_id'] = self.get_current_user_id()
                instances.append(self.model_class(**data))
            
            db.session.bulk_save_objects(instances)
            db.session.commit()
            
            logger.info(f"Bulk create em {self.model_class.__name__}: {len(instances)} registros")
            return instances
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro em bulk_create ({self.model_class.__name__}): {e}")
            return []
    
    def get_or_create(self, defaults=None, **kwargs):
        """
        Busca um registro ou cria se não existir
        
        Args:
            defaults: Valores padrão para criação
            **kwargs: Filtros de busca
        
        Returns:
            tuple: (instância, created)
        """
        instance = self.model_class.query.filter_by(**kwargs).first()
        if instance:
            return instance, False
        
        if defaults:
            kwargs.update(defaults)
        
        return self.create(**kwargs), True