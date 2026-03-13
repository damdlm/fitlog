"""Repositório para operações com registros de treino"""

from models import RegistroTreino, HistoricoTreino
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from .base_repository import BaseRepository
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class RegistroRepository(BaseRepository):
    """Repositório para gerenciar registros de treino"""
    
    def __init__(self):
        super().__init__(RegistroTreino)
    
    def get_all_with_filters(self, filtros=None, user_id=None, load_series=False):
        """Retorna registros com filtros"""
        try:
            query = self.model_class.query
            
            if load_series:
                query = query.options(joinedload(RegistroTreino.series))
            
            query = self.filter_by_user(query, user_id)
            
            if filtros:
                if 'treino_id' in filtros and filtros['treino_id']:
                    query = query.filter_by(treino_id=filtros['treino_id'])
                if 'periodo' in filtros and filtros['periodo']:
                    query = query.filter_by(periodo=filtros['periodo'])
                if 'semana' in filtros and filtros['semana'] is not None:
                    query = query.filter_by(semana=filtros['semana'])
                if 'exercicio_id' in filtros and filtros['exercicio_id']:
                    query = query.filter_by(exercicio_id=filtros['exercicio_id'])
                if 'versao_id' in filtros and filtros['versao_id']:
                    query = query.filter_by(versao_id=filtros['versao_id'])
            
            return query.order_by(RegistroTreino.data_registro.desc()).all()
        except Exception as e:
            logger.error(f"Erro ao buscar registros com filtros: {e}")
            return []
    
    def get_by_sessao(self, treino_id, periodo, semana, versao_id, user_id=None):
        """Retorna registros de uma sessão específica"""
        try:
            query = self.model_class.query.filter_by(
                treino_id=treino_id,
                periodo=periodo,
                semana=semana,
                versao_id=versao_id
            ).options(joinedload(RegistroTreino.series))
            
            query = self.filter_by_user(query, user_id)
            return query.all()
        except Exception as e:
            logger.error(f"Erro ao buscar sessão: {e}")
            return []
    
    def salvar_sessao(self, treino_id, versao_id, periodo, semana, dados_exercicios, user_id=None):
        """Salva uma sessão completa de treino"""
        try:
            user_id = user_id or self.get_current_user_id()
            if not user_id:
                return False
            
            # Remover registros antigos da mesma sessão
            self.model_class.query.filter_by(
                treino_id=treino_id,
                periodo=periodo,
                semana=semana,
                versao_id=versao_id,
                user_id=user_id
            ).delete()
            
            # Criar novos registros
            for ex_id, dados in dados_exercicios.items():
                if dados['carga'] and dados['repeticoes']:
                    registro = RegistroTreino(
                        treino_id=treino_id,
                        versao_id=versao_id,
                        periodo=periodo,
                        semana=semana,
                        exercicio_id=ex_id,
                        data_registro=dados.get('data_registro', datetime.now()),
                        user_id=user_id
                    )
                    db.session.add(registro)
                    db.session.flush()
                    
                    for i in range(dados['num_series']):
                        serie = HistoricoTreino(
                            registro_id=registro.id,
                            carga=dados['carga'],
                            repeticoes=dados['repeticoes'],
                            ordem=i+1
                        )
                        db.session.add(serie)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao salvar sessão: {e}")
            return False
    
    def get_periodos_distintos(self, user_id=None):
        """Retorna lista de períodos distintos"""
        try:
            query = db.session.query(
                self.model_class.periodo
            ).distinct()
            
            query = self.filter_by_user(query, user_id)
            
            resultados = query.all()
            return sorted([r[0] for r in resultados], reverse=True)
        except Exception as e:
            logger.error(f"Erro ao buscar períodos distintos: {e}")
            return []
    
    def get_agregado_por_semana(self, treino_id=None, user_id=None):
        """Retorna dados agregados por semana"""
        try:
            query = db.session.query(
                RegistroTreino.periodo,
                RegistroTreino.semana,
                func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes).label('volume_total'),
                func.avg(HistoricoTreino.carga).label('carga_media')
            ).join(HistoricoTreino)
            
            query = self.filter_by_user(query, user_id)
            
            if treino_id:
                query = query.filter(RegistroTreino.treino_id == treino_id)
            
            return query.group_by(
                RegistroTreino.periodo, RegistroTreino.semana
            ).order_by(
                RegistroTreino.periodo, RegistroTreino.semana
            ).all()
        except Exception as e:
            logger.error(f"Erro ao buscar agregados por semana: {e}")
            return []