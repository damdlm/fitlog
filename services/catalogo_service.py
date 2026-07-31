"""
Serviço para gerenciar o catálogo de exercícios - AGORA USA O BANCO DE DADOS
(catálogo global = exercicios_sistema, importado de data/exercises.json)
"""
from .base_service import BaseService
from models import db, ExercicioSistema
import logging
from utils.exercise_utils import remover_acentos

logger = logging.getLogger(__name__)

class CatalogoService:
    """Serviço para acessar o catálogo de exercícios do BANCO DE DADOS"""
    
    @classmethod
    def get_catalogo(cls, force_reload=False):
        """Mantido para compatibilidade - agora retorna do banco"""
        return cls.get_todos_exercicios()
    
    @classmethod
    def get_todos_exercicios(cls, limite=500):
        """
        Retorna todos os exercícios do catálogo (do banco)
        """
        try:
            exercicios = ExercicioSistema.query.order_by(
                ExercicioSistema.nome
            ).limit(limite).all()
            
            if not exercicios:
                return []
            
            resultados = []
            for ex in exercicios:
                resultados.append({
                    "id": ex.id,
                    "nome": ex.nome,
                    "musculo": ex.grupo_muscular or "Não especificado",
                    "musculo_original": ex.grupo_muscular or "",
                    "equipment": ex.equipamento or "",
                    "level": "",
                    "force": "",
                    "instructions": ex.instrucoes or []
                })
            
            return resultados
            
        except Exception as e:
            logger.error(f"Erro ao buscar exercícios: {e}")
            return []
    
    @classmethod
    def buscar_exercicios(cls, termo=None, musculo=None, limite=500):
        """
        Busca exercícios no BANCO por termo e/ou músculo
        """
        try:
            query = ExercicioSistema.query
            
            if termo:
                query = query.filter(ExercicioSistema.nome.ilike(f'%{termo}%'))
            
            if musculo:
                query = query.filter(ExercicioSistema.grupo_muscular == musculo)
            
            exercicios = query.order_by(ExercicioSistema.nome).limit(limite).all()
            
            if not exercicios:
                return []
            
            resultados = []
            for ex in exercicios:
                resultados.append({
                    "id": ex.id,
                    "nome": ex.nome,
                    "musculo": ex.grupo_muscular or "Não especificado",
                    "musculo_original": ex.grupo_muscular or "",
                    "equipment": ex.equipamento or "",
                    "level": "",
                    "force": "",
                    "instructions": ex.instrucoes or []
                })
            
            return resultados
            
        except Exception as e:
            logger.error(f"Erro ao buscar exercícios: {e}")
            return []
    
    @classmethod
    def get_musculos_disponiveis(cls):
        """Retorna lista de grupos musculares disponíveis no catálogo"""
        try:
            resultados = db.session.query(ExercicioSistema.grupo_muscular)\
                .filter(ExercicioSistema.grupo_muscular.isnot(None))\
                .distinct()\
                .order_by(ExercicioSistema.grupo_muscular)\
                .all()
            
            return [r[0] for r in resultados]
            
        except Exception as e:
            logger.error(f"Erro ao buscar músculos: {e}")
            return []
    
    @classmethod
    def get_exercicio_por_nome(cls, nome):
        """Busca um exercício específico pelo nome no banco"""
        try:
            exercicio = ExercicioSistema.query.filter(
                ExercicioSistema.nome.ilike(nome)
            ).first()
            
            if not exercicio:
                return None
            
            return {
                "id": exercicio.id,
                "nome": exercicio.nome,
                "musculo": exercicio.grupo_muscular or "Não especificado",
                "equipment": exercicio.equipamento or "",
                "instructions": exercicio.instrucoes or []
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar exercício por nome: {e}")
            return None