"""Serviço para operações com treinos"""

from models import db, Treino
from .base_service import BaseService   # ← importação direta, não do __init__
import logging

logger = logging.getLogger(__name__)

class TreinoService(BaseService):
    """Gerencia operações relacionadas a treinos"""
    
    @staticmethod
    def get_all(user_id=None):
        try:
            query = Treino.query
            query = BaseService.filter_by_user(query, user_id)
            return query.order_by(Treino.codigo).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treinos")
            return []
    
    @staticmethod
    def get_by_id(treino_id, user_id=None):
        try:
            query = Treino.query.filter_by(id=treino_id)
            query = BaseService.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treino {treino_id}")
            return None
    
    @staticmethod
    def get_by_codigo(codigo, user_id=None):
        try:
            query = Treino.query.filter_by(codigo=codigo.upper())
            query = BaseService.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treino {codigo}")
            return None

    @staticmethod
    def get_da_versao_ativa(user_id=None):
        """Retorna os treinos que pertencem à versão ativa do usuário.

        Diferente de get_all(), que traz TODO treino já criado pelo
        usuário (inclusive de versões antigas/encerradas), este método
        restringe aos treinos vinculados (via TreinoVersao) à versão
        global sem data_fim -- usado nos filtros de "Evolução do Volume"
        das telas de estatísticas, para não misturar treinos que não
        fazem mais parte da grade atual do usuário.
        """
        try:
            from models import TreinoVersao
            from services.versao_service import VersaoService

            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            versao_ativa = VersaoService.get_ativa(user_id=user_id)
            if not versao_ativa:
                return []

            return (
                Treino.query
                .join(TreinoVersao, TreinoVersao.treino_id == Treino.id)
                .filter(
                    TreinoVersao.versao_id == versao_ativa.id,
                    Treino.user_id == user_id,
                )
                .order_by(Treino.codigo)
                .all()
            )
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treinos da versão ativa")
            return []
    
    @staticmethod
    def create(codigo, nome, descricao, user_id=None):
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de criar treino sem usuário logado")
                return None
            
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
    def get_or_create(codigo, nome=None, descricao='', user_id=None):
        """Retorna o Treino (letra) já existente para o usuário ou cria um novo
        automaticamente. Usado para não exigir um cadastro manual prévio de
        'Treino' antes de vincular a letra a uma versão."""
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de get_or_create treino sem usuário logado")
                return None

            codigo = codigo.upper()
            treino = TreinoService.get_by_codigo(codigo, user_id)
            if treino:
                return treino

            treino = Treino(
                codigo=codigo,
                nome=nome or f'Treino {codigo}',
                descricao=descricao or '',
                user_id=user_id
            )
            db.session.add(treino)
            db.session.commit()
            logger.info(f"Treino {codigo} criado automaticamente para usuário {user_id}")
            return treino
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao obter/criar treino {codigo}")
            return None

    @staticmethod
    def update(treino_id, codigo=None, nome=None, descricao=None, user_id=None):
        try:
            treino = TreinoService.get_by_id(treino_id, user_id)
            if not treino:
                logger.warning(f"Treino {treino_id} não encontrado para atualização")
                return None
            
            if codigo and codigo != treino.codigo:
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