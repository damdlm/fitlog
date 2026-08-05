import json
import logging
from pathlib import Path
import unicodedata

logger = logging.getLogger(__name__)

def remover_acentos(texto):
    """Remove acentos de uma string"""
    if not texto:
        return texto
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join([c for c in texto if not unicodedata.combining(c)])

# utils/exercise_utils.py - VERSÃO CORRIGIDA (busca no BANCO)

def buscar_musculo_no_catalogo(nome_exercicio):
    """
    Busca o músculo primário de um exercício no catálogo do BANCO DE DADOS.
    Retorna o nome do músculo em português ou None se não encontrar.
    """
    from models import ExercicioSistema
    from utils.exercise_utils import remover_acentos
    
    print(f"🔍 Buscando músculo para: '{nome_exercicio}'")
    
    # Normalizar o nome de busca
    nome_busca = remover_acentos(nome_exercicio.lower().strip())
    print(f"🔤 Termo de busca normalizado: '{nome_busca}'")
    
    try:
        # 1. Correspondência exata
        exercicio = ExercicioSistema.query.filter(
            ExercicioSistema.nome.ilike(nome_exercicio)
        ).first()
        
        if exercicio and exercicio.grupo_muscular:
            musculo = exercicio.grupo_muscular
            print(f"✅ Correspondência exata encontrada: {musculo}")
            return musculo
        
        # 2. Nome do catálogo CONTÉM o nome buscado
        exercicios = ExercicioSistema.query.filter(
            ExercicioSistema.nome.ilike(f'%{nome_exercicio}%')
        ).limit(10).all()
        
        for ex in exercicios:
            nome_catalogo = remover_acentos(ex.nome.lower())
            if nome_busca in nome_catalogo and ex.grupo_muscular:
                musculo = ex.grupo_muscular
                print(f"✅ Correspondência parcial: {musculo}")
                return musculo
        
        # 3. Nome buscado CONTÉM o nome do catálogo
        for ex in exercicios:
            nome_catalogo = remover_acentos(ex.nome.lower())
            if nome_catalogo in nome_busca and ex.grupo_muscular:
                musculo = ex.grupo_muscular
                print(f"✅ Correspondência inversa: {musculo}")
                return musculo
        
        print(f"❌ Nenhum músculo encontrado para '{nome_exercicio}'")
        
    except Exception:
        logger.exception("Erro ao buscar no catálogo")
    
    return None

def get_series_from_registro(registro):
    """Retorna as séries de um registro, convertendo formato antigo se necessário"""
    if hasattr(registro, 'series') and registro.series:
        return [{'carga': float(s.carga), 'repeticoes': s.repeticoes} for s in registro.series]
    return []

def calcular_media_series(series):
    """Calcula média de carga e repetições das séries"""
    if not series:
        return 0, 0
    media_carga = sum(s["carga"] for s in series) / len(series)
    media_reps = sum(s["repeticoes"] for s in series) / len(series)
    return round(media_carga, 1), round(media_reps, 1)

def calcular_volume_total(series):
    """Calcula volume total somando todas as séries"""
    return sum(s["carga"] * s["repeticoes"] for s in series)