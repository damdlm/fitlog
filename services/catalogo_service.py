"""
Serviço para gerenciar o catálogo de exercícios do arquivo JSON
"""

import json
import hashlib
from pathlib import Path
import logging
from utils.exercise_utils import remover_acentos

logger = logging.getLogger(__name__)

class CatalogoService:
    """Serviço para acessar o catálogo de exercícios do JSON"""
    
    _catalogo = None
    _catalogo_path = Path("storage/exercises-ptbr-full-translation.json")
    
    @classmethod
    def get_catalogo(cls, force_reload=False):
        """Carrega o catálogo do arquivo JSON (com cache)"""
        if cls._catalogo is None or force_reload:
            try:
                if not cls._catalogo_path.exists():
                    logger.error(f"Arquivo de catálogo não encontrado: {cls._catalogo_path}")
                    return []
                
                with open(cls._catalogo_path, 'r', encoding='utf-8') as f:
                    cls._catalogo = json.load(f)
                
                logger.info(f"Catálogo carregado com {len(cls._catalogo)} exercícios")
            except Exception as e:
                logger.error(f"Erro ao carregar catálogo: {e}")
                return []
        
        return cls._catalogo
    
    @classmethod
    def get_todos_exercicios(cls, limite=500):
        """
        Retorna todos os exercícios do catálogo (com paginação opcional)
        
        Args:
            limite: Número máximo de exercícios (padrão 500)
        
        Returns:
            list: Lista com todos os exercícios
        """
        catalogo = cls.get_catalogo()
        if not catalogo:
            return []
        
        # Mapeamento de músculos em inglês para português
        mapa_musculos = {
            'abdominais': 'Abdômen',
            'abductors': 'Abdutores',
            'adductors': 'Adutores',
            'biceps': 'Bíceps',
            'calves': 'Panturrilhas',
            'chest': 'Peitoral',
            'forearms': 'Antebraços',
            'glutes': 'Glúteos',
            'hamstrings': 'Posterior de Coxa',
            'lats': 'Dorsal',
            'lower back': 'Lombar',
            'middle back': 'Costas',
            'neck': 'Pescoço',
            'quadriceps': 'Quadríceps',
            'shoulders': 'Ombros',
            'traps': 'Trapézio',
            'triceps': 'Tríceps'
        }
        
        resultados = []
        for ex in catalogo:
            nome = ex.get('name', '')
            primary_muscles = ex.get('primaryMuscles', [])
            musculo_original = primary_muscles[0] if primary_muscles else "Não especificado"
            
            musculo_exibicao = mapa_musculos.get(musculo_original.lower(), musculo_original.title())
            
            # Gerar ID hash para referência
            id_hash = int(hashlib.md5(nome.encode()).hexdigest()[:7], 16) & 0x7FFFFFFF
            resultados.append({
                "id": id_hash,
                "nome": nome,
                "musculo": musculo_exibicao,
                "musculo_original": musculo_original,
                "equipment": ex.get('equipment', ''),
                "level": ex.get('level', ''),
                "force": ex.get('force', ''),
                "instructions": ex.get('instructions', [])
            })
            
            if len(resultados) >= limite:
                break
        
        # Ordenar por nome
        resultados.sort(key=lambda x: x['nome'])
        return resultados
    
    @classmethod
    def buscar_exercicios(cls, termo=None, musculo=None, limite=500):
        """
        Busca exercícios no catálogo por termo e/ou músculo
        Se não houver termo, retorna todos (limitado)
        
        Args:
            termo: Termo para buscar no nome do exercício (opcional)
            musculo: Filtrar por músculo (opcional)
            limite: Número máximo de resultados
        
        Returns:
            list: Lista de exercícios encontrados
        """
        # Se não tiver termo nem músculo, retorna todos
        if not termo and not musculo:
            return cls.get_todos_exercicios(limite)
        
        catalogo = cls.get_catalogo()
        if not catalogo:
            return []
        
        # Mapeamento de músculos em inglês para português
        mapa_musculos = {
            'abdominais': 'Abdômen',
            'abductors': 'Abdutores',
            'adductors': 'Adutores',
            'biceps': 'Bíceps',
            'calves': 'Panturrilhas',
            'chest': 'Peitoral',
            'forearms': 'Antebraços',
            'glutes': 'Glúteos',
            'hamstrings': 'Posterior de Coxa',
            'lats': 'Dorsal',
            'lower back': 'Lombar',
            'middle back': 'Costas',
            'neck': 'Pescoço',
            'quadriceps': 'Quadríceps',
            'shoulders': 'Ombros',
            'traps': 'Trapézio',
            'triceps': 'Tríceps'
        }
        
        resultados = []
        termo_normalizado = remover_acentos(termo.lower()) if termo else None
        
        for ex in catalogo:
            nome = ex.get('name', '')
            primary_muscles = ex.get('primaryMuscles', [])
            musculo_original = primary_muscles[0] if primary_muscles else "Não especificado"
            
            nome_normalizado = remover_acentos(nome.lower())
            musculo_exibicao = mapa_musculos.get(musculo_original.lower(), musculo_original.title())
            
            # Aplicar filtros
            if termo and termo_normalizado not in nome_normalizado:
                continue
            
            if musculo and musculo_exibicao != musculo:
                continue
            
            # Gerar ID hash para referência
            id_hash = int(hashlib.md5(nome.encode()).hexdigest()[:8], 16)
            
            resultados.append({
                "id": id_hash,
                "nome": nome,
                "musculo": musculo_exibicao,
                "musculo_original": musculo_original,
                "equipment": ex.get('equipment', ''),
                "level": ex.get('level', ''),
                "force": ex.get('force', ''),
                "instructions": ex.get('instructions', [])
            })
            
            if len(resultados) >= limite:
                break
        
        return resultados
    
    @classmethod
    def get_musculos_disponiveis(cls):
        """Retorna lista de músculos disponíveis no catálogo"""
        catalogo = cls.get_catalogo()
        if not catalogo:
            return []
        
        mapa_musculos = {
            'abdominais': 'Abdômen',
            'abductors': 'Abdutores',
            'adductors': 'Adutores',
            'biceps': 'Bíceps',
            'calves': 'Panturrilhas',
            'chest': 'Peitoral',
            'forearms': 'Antebraços',
            'glutes': 'Glúteos',
            'hamstrings': 'Posterior de Coxa',
            'lats': 'Dorsal',
            'lower back': 'Lombar',
            'middle back': 'Costas',
            'neck': 'Pescoço',
            'quadriceps': 'Quadríceps',
            'shoulders': 'Ombros',
            'traps': 'Trapézio',
            'triceps': 'Tríceps'
        }
        
        musculos_set = set()
        for ex in catalogo:
            primary_muscles = ex.get('primaryMuscles', [])
            if primary_muscles:
                musculo = mapa_musculos.get(primary_muscles[0].lower(), primary_muscles[0].title())
                musculos_set.add(musculo)
        
        return sorted(list(musculos_set))
    
    @classmethod
    def get_exercicio_por_nome(cls, nome):
        """Busca um exercício específico pelo nome no catálogo"""
        catalogo = cls.get_catalogo()
        if not catalogo:
            return None
        
        nome_normalizado = remover_acentos(nome.lower())
        
        for ex in catalogo:
            if remover_acentos(ex.get('name', '').lower()) == nome_normalizado:
                primary_muscles = ex.get('primaryMuscles', [])
                musculo_original = primary_muscles[0] if primary_muscles else "Não especificado"
                
                mapa_musculos = {
                    'abdominais': 'Abdômen',
                    'abductors': 'Abdutores',
                    'adductors': 'Adutores',
                    'biceps': 'Bíceps',
                    'calves': 'Panturrilhas',
                    'chest': 'Peitoral',
                    'forearms': 'Antebraços',
                    'glutes': 'Glúteos',
                    'hamstrings': 'Posterior de Coxa',
                    'lats': 'Dorsal',
                    'lower back': 'Lombar',
                    'middle back': 'Costas',
                    'neck': 'Pescoço',
                    'quadriceps': 'Quadríceps',
                    'shoulders': 'Ombros',
                    'traps': 'Trapézio',
                    'triceps': 'Tríceps'
                }
                
                return {
                    "nome": ex.get('name', ''),
                    "musculo": mapa_musculos.get(musculo_original.lower(), musculo_original.title()),
                    "equipment": ex.get('equipment', ''),
                    "instructions": ex.get('instructions', [])
                }
        
        return None