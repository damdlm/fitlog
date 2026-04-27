"""
Serviço para gerenciar o catálogo de exercícios - AGORA USA O BANCO DE DADOS
"""
from .base_service import BaseService
from models import db, ExercicioBase, Musculo
from sqlalchemy import or_
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
            exercicios = ExercicioBase.query.options(
                db.joinedload(ExercicioBase.musculo_ref)
            ).order_by(ExercicioBase.nome).limit(limite).all()
            
            if not exercicios:
                return []
            
            resultados = []
            for ex in exercicios:
                resultados.append({
                    "id": ex.id,
                    "nome": ex.nome,
                    "musculo": ex.musculo_ref.nome_exibicao if ex.musculo_ref else "Não especificado",
                    "musculo_original": ex.musculo_nome or "",
                    "equipment": ex.equipamento or "",
                    "level": ex.nivel or "",
                    "force": ex.forca or "",
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
            query = ExercicioBase.query.options(
                db.joinedload(ExercicioBase.musculo_ref)
            )
            
            if termo:
                query = query.filter(ExercicioBase.nome.ilike(f'%{termo}%'))
            
            if musculo:
                query = query.join(ExercicioBase.musculo_ref).filter(
                    Musculo.nome_exibicao == musculo
                )
            
            exercicios = query.order_by(ExercicioBase.nome).limit(limite).all()
            
            if not exercicios:
                return []
            
            resultados = []
            for ex in exercicios:
                resultados.append({
                    "id": ex.id,
                    "nome": ex.nome,
                    "musculo": ex.musculo_ref.nome_exibicao if ex.musculo_ref else "Não especificado",
                    "musculo_original": ex.musculo_nome or "",
                    "equipment": ex.equipamento or "",
                    "level": ex.nivel or "",
                    "force": ex.forca or "",
                    "instructions": ex.instrucoes or []
                })
            
            return resultados
            
        except Exception as e:
            logger.error(f"Erro ao buscar exercícios: {e}")
            return []
    
    @classmethod
    def get_musculos_disponiveis(cls):
        """Retorna lista de músculos disponíveis no catálogo"""
        try:
            resultados = db.session.query(Musculo.nome_exibicao).join(
                ExercicioBase, ExercicioBase.musculo_id == Musculo.id
            ).distinct().order_by(Musculo.nome_exibicao).all()
            
            return [r[0] for r in resultados]
            
        except Exception as e:
            logger.error(f"Erro ao buscar músculos: {e}")
            return []
    
    @classmethod
    def get_exercicio_por_nome(cls, nome):
        """Busca um exercício específico pelo nome no banco"""
        try:
            exercicio = ExercicioBase.query.options(
                db.joinedload(ExercicioBase.musculo_ref)
            ).filter(ExercicioBase.nome.ilike(nome)).first()
            
            if not exercicio:
                return None
            
            return {
                "id": exercicio.id,
                "nome": exercicio.nome,
                "musculo": exercicio.musculo_ref.nome_exibicao if exercicio.musculo_ref else "Não especificado",
                "equipment": exercicio.equipamento or "",
                "instructions": exercicio.instrucoes or []
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar exercício por nome: {e}")
            return None