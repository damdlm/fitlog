import json
from pathlib import Path
import unicodedata

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
    from models import ExercicioBase, Musculo
    from sqlalchemy.orm import joinedload
    from utils.exercise_utils import remover_acentos
    
    print(f"🔍 Buscando músculo para: '{nome_exercicio}'")
    
    # Normalizar o nome de busca
    nome_busca = remover_acentos(nome_exercicio.lower().strip())
    print(f"🔤 Termo de busca normalizado: '{nome_busca}'")
    
    # Mapeamento de músculos em inglês para português (caso o banco ainda tenha nomes em inglês)
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
    
    try:
        # 1. Correspondência exata
        exercicio = ExercicioBase.query.options(
            joinedload(ExercicioBase.musculo_ref)
        ).filter(ExercicioBase.nome.ilike(nome_exercicio)).first()
        
        if exercicio and exercicio.musculo_ref:
            musculo = exercicio.musculo_ref.nome_exibicao
            print(f"✅ Correspondência exata encontrada: {musculo}")
            return musculo
        
        # 2. Nome do catálogo CONTÉM o nome buscado
        exercicios = ExercicioBase.query.options(
            joinedload(ExercicioBase.musculo_ref)
        ).filter(ExercicioBase.nome.ilike(f'%{nome_exercicio}%')).limit(10).all()
        
        for ex in exercicios:
            nome_catalogo = remover_acentos(ex.nome.lower())
            if nome_busca in nome_catalogo and ex.musculo_ref:
                musculo = ex.musculo_ref.nome_exibicao
                print(f"✅ Correspondência parcial: {musculo}")
                return musculo
        
        # 3. Nome buscado CONTÉM o nome do catálogo
        for ex in exercicios:
            nome_catalogo = remover_acentos(ex.nome.lower())
            if nome_catalogo in nome_busca and ex.musculo_ref:
                musculo = ex.musculo_ref.nome_exibicao
                print(f"✅ Correspondência inversa: {musculo}")
                return musculo
        
        # 4. Fallback: tentar pelo nome do músculo original (se existir no banco)
        exercicio = ExercicioBase.query.options(
            joinedload(ExercicioBase.musculo_ref)
        ).filter(ExercicioBase.musculo_nome.ilike(f'%{nome_busca}%')).first()
        
        if exercicio and exercicio.musculo_ref:
            musculo = exercicio.musculo_ref.nome_exibicao
            print(f"✅ Correspondência pelo nome do músculo: {musculo}")
            return musculo
        
        print(f"❌ Nenhum músculo encontrado para '{nome_exercicio}'")
        
    except Exception as e:
        print(f"❌ Erro ao buscar no catálogo: {e}")
        import traceback
        traceback.print_exc()
    
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