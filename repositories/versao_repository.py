"""Repositório para operações com versões"""

from models import VersaoGlobal, TreinoVersao, VersaoExercicio
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from .base_repository import BaseRepository
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class VersaoRepository(BaseRepository):
    """Repositório para gerenciar versões"""
    
    def __init__(self):
        super().__init__(VersaoGlobal)
    
    def get_ativa(self, periodo=None, user_id=None):
        """Retorna versão ativa para um período"""
        try:
            if periodo:
                from utils.date_utils import converter_periodo_para_data
                data_periodo = converter_periodo_para_data(periodo)
                
                query = self.model_class.query.filter(
                    self.model_class.data_inicio <= data_periodo,
                    (self.model_class.data_fim.is_(None) | 
                     (self.model_class.data_fim >= data_periodo))
                )
            else:
                query = self.model_class.query.filter_by(data_fim=None)
            
            query = self.filter_by_user(query, user_id)
            return query.order_by(self.model_class.data_inicio.desc()).first()
        except Exception as e:
            logger.error(f"Erro ao buscar versão ativa: {e}")
            return None
    
    def get_with_treinos(self, versao_id, user_id=None):
        """Retorna versão com seus treinos e exercícios"""
        try:
            query = self.model_class.query.options(
                joinedload(VersaoGlobal.treinos)
                .joinedload(TreinoVersao.exercicios)
            ).filter_by(id=versao_id)
            query = self.filter_by_user(query, user_id)
            return query.first()
        except Exception as e:
            logger.error(f"Erro ao buscar versão com treinos {versao_id}: {e}")
            return None
    
    def get_proximo_numero(self, user_id=None):
        """Retorna o próximo número de versão disponível"""
        try:
            user_id = user_id or self.get_current_user_id()
            if not user_id:
                return 1
            
            ultima = db.session.query(func.max(self.model_class.numero_versao))\
                .filter_by(user_id=user_id).scalar() or 0
            return ultima + 1
        except Exception as e:
            logger.error(f"Erro ao buscar próximo número de versão: {e}")
            return 1
    
    def adicionar_treino(self, versao_id, treino_id, nome_treino, descricao_treino, 
                         exercicios_ids, user_id=None):
        """Adiciona um treino a uma versão"""
        try:
            # Verificar se o treino já existe na versão
            existe = TreinoVersao.query.filter_by(
                versao_id=versao_id, treino_id=treino_id
            ).first()
            
            if existe:
                logger.warning(f"Treino {treino_id} já existe na versão {versao_id}")
                return False
            
            # Obter ordem
            ordem = TreinoVersao.query.filter_by(versao_id=versao_id).count()
            
            treino_versao = TreinoVersao(
                versao_id=versao_id,
                treino_id=treino_id,
                nome_treino=nome_treino,
                descricao_treino=descricao_treino,
                ordem=ordem
            )
            db.session.add(treino_versao)
            db.session.flush()
            
            # Adicionar exercícios
            for ordem_ex, ex_id in enumerate(exercicios_ids):
                ve = VersaoExercicio(
                    treino_versao_id=treino_versao.id,
                    exercicio_id=ex_id,
                    ordem=ordem_ex
                )
                db.session.add(ve)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar treino à versão: {e}")
            return False
    
    def remover_treino(self, versao_id, treino_id, user_id=None):
        """Remove um treino de uma versão"""
        try:
            treino_versao = TreinoVersao.query.filter_by(
                versao_id=versao_id, treino_id=treino_id
            ).first()
            
            if treino_versao:
                db.session.delete(treino_versao)
                db.session.commit()
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao remover treino da versão: {e}")
            return False