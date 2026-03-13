"""Serviço para operações com registros de treino"""

from models import db, RegistroTreino, HistoricoTreino
from sqlalchemy.orm import joinedload
from datetime import datetime
from . import BaseService
import logging

logger = logging.getLogger(__name__)

class RegistroService(BaseService):
    """Gerencia operações relacionadas a registros de treino"""
    
    @staticmethod
    def get_all(filtros=None, user_id=None, load_series=False):
        """Retorna registros com filtros opcionais"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            query = RegistroTreino.query.filter_by(user_id=user_id)
            
            if load_series:
                query = query.options(joinedload(RegistroTreino.series))
            
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
            BaseService.handle_error(e, "Erro ao buscar registros")
            return []
    
    # ===== NOVO MÉTODO ADICIONADO =====
    @staticmethod
    def get_by_data(treino_id, versao_id, data, user_id=None):
        """
        Retorna registros de um treino em uma data específica
        
        Args:
            treino_id: ID do treino
            versao_id: ID da versão
            data: Data do registro (date object ou string YYYY-MM-DD)
            user_id: ID do usuário (opcional)
        
        Returns:
            list: Lista de registros encontrados
        """
        try:
            from datetime import datetime
            
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de buscar registros sem usuário logado")
                return []
            
            # Garantir que data é date object
            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()
            
            # Buscar registros do dia com as séries carregadas
            registros = RegistroTreino.query.options(
                joinedload(RegistroTreino.series)
            ).filter(
                RegistroTreino.user_id == user_id,
                RegistroTreino.treino_id == treino_id,
                RegistroTreino.versao_id == versao_id,
                RegistroTreino.data_registro == data
            ).all()
            
            logger.debug(f"Encontrados {len(registros)} registros para treino {treino_id} em {data}")
            return registros
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros por data")
            return []
    
    @staticmethod
    def salvar_registros(treino_id, versao_id, periodo, semana, dados_exercicios, user_id=None):
        """Salva múltiplos registros de uma sessão de treino"""
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de salvar registros sem usuário logado")
                return False
            
            # Remover registros antigos da mesma sessão
            RegistroTreino.query.filter_by(
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
                    
                    # Criar séries
                    for i in range(dados['num_series']):
                        serie = HistoricoTreino(
                            registro_id=registro.id,
                            carga=dados['carga'],
                            repeticoes=dados['repeticoes'],
                            ordem=i+1
                        )
                        db.session.add(serie)
            
            db.session.commit()
            logger.info(f"Registros salvos para treino {treino_id}, semana {semana}")
            return True
        except Exception as e:
            BaseService.handle_error(e, "Erro ao salvar registros")
            return False
    
    @staticmethod
    def salvar_registro_unico(treino_id, versao_id, periodo, semana, exercicio_id, 
                              carga, repeticoes, num_series=3, data_registro=None, user_id=None):
        """Salva um único registro de exercício"""
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de salvar registro sem usuário logado")
                return None
            
            if data_registro is None:
                data_registro = datetime.now()
            
            # Remover registros antigos do mesmo exercício na mesma sessão
            RegistroTreino.query.filter_by(
                treino_id=treino_id,
                periodo=periodo,
                semana=semana,
                versao_id=versao_id,
                exercicio_id=exercicio_id,
                user_id=user_id
            ).delete()
            
            # Criar novo registro
            registro = RegistroTreino(
                treino_id=treino_id,
                versao_id=versao_id,
                periodo=periodo,
                semana=semana,
                exercicio_id=exercicio_id,
                data_registro=data_registro,
                user_id=user_id
            )
            db.session.add(registro)
            db.session.flush()
            
            # Criar séries
            for i in range(num_series):
                serie = HistoricoTreino(
                    registro_id=registro.id,
                    carga=carga,
                    repeticoes=repeticoes,
                    ordem=i+1
                )
                db.session.add(serie)
            
            db.session.commit()
            logger.info(f"Registro salvo para exercício {exercicio_id}")
            return registro
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao salvar registro único")
            return None
    
    @staticmethod
    def get_periodos_existentes(user_id=None):
        """Retorna lista de períodos com registros"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            registros = RegistroTreino.query\
                .filter_by(user_id=user_id)\
                .with_entities(RegistroTreino.periodo)\
                .distinct().all()
            
            return sorted([r[0] for r in registros], reverse=True)
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar períodos")
            return []
    
    @staticmethod
    def get_semanas_por_periodo(user_id=None):
        """Retorna dicionário com semanas agrupadas por período"""
        try:
            registros = RegistroService.get_all(user_id=user_id)
            
            semanas_set = set()
            for r in registros:
                semanas_set.add((r.periodo, r.semana, f"{r.periodo}_{r.semana}"))
            
            periodos_dict = {}
            for periodo, semana, key in semanas_set:
                if periodo not in periodos_dict:
                    periodos_dict[periodo] = []
                periodos_dict[periodo].append({
                    "semana": semana,
                    "key": key
                })
            
            return periodos_dict
        except Exception as e:
            BaseService.handle_error(e, "Erro ao agrupar semanas")
            return {}
    
    @staticmethod
    def get_volume_total_por_semana(registros):
        """Calcula volume total por semana"""
        try:
            volume_por_semana = {}
            for r in registros:
                key = f"{r.periodo}_{r.semana}"
                if key not in volume_por_semana:
                    volume_por_semana[key] = 0
                
                for serie in r.series:
                    volume_por_semana[key] += float(serie.carga) * serie.repeticoes
            
            return volume_por_semana
        except Exception as e:
            logger.error(f"Erro ao calcular volume por semana: {e}")
            return {}
    
    @staticmethod
    def get_por_exercicio(exercicio_id, limite=None, user_id=None):
        """Retorna registros de um exercício específico"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            query = RegistroTreino.query.options(
                joinedload(RegistroTreino.series)
            ).filter_by(
                exercicio_id=exercicio_id,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro.desc())
            
            if limite:
                query = query.limit(limite)
            
            return query.all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros do exercício {exercicio_id}")
            return []
    
    @staticmethod
    def get_por_periodo(periodo, user_id=None):
        """Retorna todos os registros de um período"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            return RegistroTreino.query.options(
                joinedload(RegistroTreino.series)
            ).filter_by(
                periodo=periodo,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro).all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros do período {periodo}")
            return []
    
    @staticmethod
    def get_por_semana(periodo, semana, user_id=None):
        """Retorna todos os registros de uma semana específica"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            return RegistroTreino.query.options(
                joinedload(RegistroTreino.series)
            ).filter_by(
                periodo=periodo,
                semana=semana,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro).all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros da semana {semana}")
            return []
    
    @staticmethod
    def get_ultimo_registro_por_exercicio(exercicio_id, user_id=None):
        """Retorna o último registro de um exercício"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            
            return RegistroTreino.query.options(
                joinedload(RegistroTreino.series)
            ).filter_by(
                exercicio_id=exercicio_id,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro.desc()).first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar último registro do exercício {exercicio_id}")
            return None
    
    @staticmethod
    def get_estatisticas_exercicio(exercicio_id, user_id=None):
        """Retorna estatísticas de um exercício"""
        try:
            from sqlalchemy import func
            
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}
            
            registros = RegistroService.get_por_exercicio(exercicio_id, user_id=user_id)
            
            if not registros:
                return {}
            
            # Calcular estatísticas
            total_registros = len(registros)
            total_series = 0
            soma_cargas = 0
            soma_repeticoes = 0
            maior_carga = 0
            maior_volume = 0
            
            for r in registros:
                for s in r.series:
                    total_series += 1
                    soma_cargas += float(s.carga)
                    soma_repeticoes += s.repeticoes
                    
                    if float(s.carga) > maior_carga:
                        maior_carga = float(s.carga)
                    
                    volume = float(s.carga) * s.repeticoes
                    if volume > maior_volume:
                        maior_volume = volume
            
            return {
                'total_registros': total_registros,
                'total_series': total_series,
                'media_carga': soma_cargas / total_series if total_series > 0 else 0,
                'media_repeticoes': soma_repeticoes / total_series if total_series > 0 else 0,
                'maior_carga': maior_carga,
                'maior_volume': maior_volume
            }
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao calcular estatísticas do exercício {exercicio_id}")
            return {}