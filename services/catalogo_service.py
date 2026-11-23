"""
Serviço para gerenciar o catálogo de exercícios - AGORA USA O BANCO DE DADOS
(catálogo global = exercicios_sistema, importado de data/exercises.json)
"""
from .base_service import BaseService, CacheService
from models import db, ExercicioSistema, musculo_principal_de
from sqlalchemy import or_
import logging
from utils.exercise_utils import remover_acentos

logger = logging.getLogger(__name__)

# TTL longo -- ExercicioSistema só é alterado por script de importação
# (nenhuma rota HTTP cria/edita/deleta esse catálogo, ver
# grep de "ExercicioSistema(" em routes/), nunca durante o uso normal
# do app. 10 min de possível atraso após uma reimportação manual é
# aceitável -- e quem reimporta pode reiniciar os workers pra forçar
# cache-miss imediato, se precisar ver a mudança na hora.
CATALOGO_CACHE_TTL_SEGUNDOS = 600

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
        cache_key = f"catalogo:todos:{limite}"
        cache_hit = CacheService.get(cache_key)
        if cache_hit is not None:
            return cache_hit

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
                    "musculo": ex.musculo_principal or "Não especificado",
                    "musculo_original": ex.musculo_principal or "",
                    "equipment": ex.equipamento or "",
                    "level": "",
                    "force": "",
                    "instructions": ex.instrucoes or []
                })
            
            CacheService.set(cache_key, resultados, ttl_seconds=CATALOGO_CACHE_TTL_SEGUNDOS)
            return resultados
            
        except Exception:
            logger.exception("Erro ao buscar exercícios")
            return []
    
    @classmethod
    def buscar_exercicios(cls, termo=None, musculo=None, limite=500):
        """
        Busca exercícios no BANCO por termo (nome ou apelido/nickname) e/ou músculo
        """
        try:
            query = ExercicioSistema.query
            
            if termo:
                termo_like = f'%{termo}%'
                query = query.filter(
                    or_(
                        ExercicioSistema.nome.ilike(termo_like),
                        db.cast(ExercicioSistema.nicknames, db.Text).ilike(termo_like),
                    )
                )
            
            if musculo:
                query = query.filter(ExercicioSistema.filtro_musculo_principal(musculo))
            
            exercicios = query.order_by(ExercicioSistema.nome).limit(limite).all()
            
            if not exercicios:
                return []
            
            resultados = []
            for ex in exercicios:
                resultados.append({
                    "id": ex.id,
                    "nome": ex.nome,
                    "musculo": ex.musculo_principal or "Não especificado",
                    "musculo_original": ex.musculo_principal or "",
                    "equipment": ex.equipamento or "",
                    "level": "",
                    "force": "",
                    "instructions": ex.instrucoes or []
                })
            
            return resultados
            
        except Exception:
            logger.exception("Erro ao buscar exercícios")
            return []
    
    @classmethod
    def get_musculos_disponiveis(cls):
        """Retorna lista de grupos musculares disponíveis no catálogo"""
        try:
            # Músculo principal = alvo traduzido (ver
            # ExercicioSistema.musculo_principal); grupo_muscular só sem alvo.
            pares = db.session.query(ExercicioSistema.alvo, ExercicioSistema.grupo_muscular).distinct().all()
            nomes = {musculo_principal_de(a, g) for a, g in pares}
            return sorted((n for n in nomes if n), key=lambda n: remover_acentos(n.lower()))
            
        except Exception:
            logger.exception("Erro ao buscar músculos")
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
                "musculo": exercicio.musculo_principal or "Não especificado",
                "equipment": exercicio.equipamento or "",
                "instructions": exercicio.instrucoes or []
            }
            
        except Exception:
            logger.exception("Erro ao buscar exercício por nome")
            return None