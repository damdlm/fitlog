"""Serviço para operações com treinos"""

from models import db, Treino
from . import BaseService
import logging

logger = logging.getLogger(__name__)

class TreinoService(BaseService):
    """Gerencia operações relacionadas a treinos"""
    
    @staticmethod
    def get_all(user_id=None):
        """Retorna todos os treinos do usuário"""
        try:
            query = Treino.query
            query = BaseService.filter_by_user(query, user_id)
            return query.order_by(Treino.codigo).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treinos")
            return []
    
    @staticmethod
    def get_by_id(treino_id, user_id=None):
        """Retorna treino por ID"""
        try:
            query = Treino.query.filter_by(id=treino_id)
            query = BaseService.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treino {treino_id}")
            return None
    
    @staticmethod
    def get_by_codigo(codigo, user_id=None):
        """Retorna treino por código"""
        try:
            query = Treino.query.filter_by(codigo=codigo.upper())
            query = BaseService.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treino {codigo}")
            return None
    
    @staticmethod
    def create(codigo, nome, descricao, user_id=None):
        """Cria um novo treino"""
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de criar treino sem usuário logado")
                return None
            
            # Verificar se já existe
            existente = TreinoService.get_by_codigo(codigo, user_id)
            if existente:
                logger.warning(f"Treino {codigo} já existe para usuário {user_id}")
                return None
            
            treino = Treino(
                codigo=codigo.upper(),
                nome=nome,
                descricao=descricao,
                user_id=user_id
            )
            db.session.add(treino)
            db.session.commit()
            logger.info(f"Treino {codigo} criado para usuário {user_id}")
            return treino
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao criar treino {codigo}")
            return None
    
    @staticmethod
    def update(treino_id, codigo=None, nome=None, descricao=None, user_id=None):
        """Atualiza um treino existente"""
        try:
            treino = TreinoService.get_by_id(treino_id, user_id)
            if not treino:
                logger.warning(f"Treino {treino_id} não encontrado para atualização")
                return None
            
            if codigo and codigo != treino.codigo:
                # Verificar se novo código já existe
                existente = TreinoService.get_by_codigo(codigo, user_id)
                if existente and existente.id != treino_id:
                    logger.warning(f"Código {codigo} já está em uso")
                    return None
                treino.codigo = codigo.upper()
            
            if nome:
                treino.nome = nome
            if descricao is not None:
                treino.descricao = descricao
            
            db.session.commit()
            logger.info(f"Treino {treino_id} atualizado")
            return treino
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar treino {treino_id}")
            return None
    
    @staticmethod
    def delete(treino_id, user_id=None):
        """Remove um treino"""
        try:
            treino = TreinoService.get_by_id(treino_id, user_id)
            if not treino:
                logger.warning(f"Treino {treino_id} não encontrado para exclusão")
                return False
            
            db.session.delete(treino)
            db.session.commit()
            logger.info(f"Treino {treino_id} excluído")
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao excluir treino {treino_id}")
            return False