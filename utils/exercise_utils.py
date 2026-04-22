import json
from pathlib import Path
import unicodedata

def remover_acentos(texto):
    """Remove acentos de uma string"""
    if not texto:
        return texto
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join([c for c in texto if not unicodedata.combining(c)])

def buscar_musculo_no_catalogo(nome_exercicio):
    """
    Busca o músculo primário de um exercício no catálogo completo.
    Retorna o nome do músculo em português ou None se não encontrar.
    """
    catalogo_path = Path("storage/exercises-ptbr-full-translation.json")
    
    print(f"🔍 Buscando músculo para: '{nome_exercicio}'")
    
    if not catalogo_path.exists():
        print(f"❌ Arquivo de catálogo não encontrado!")
        return None
    
    try:
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            catalogo = json.load(f)
        
        # Normalizar o nome de busca
        nome_busca = remover_acentos(nome_exercicio.lower().strip())
        print(f"🔤 Termo de busca normalizado: '{nome_busca}'")
        
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
        
        # 1. Correspondência exata
        for ex in catalogo:
            nome_catalogo = remover_acentos(ex.get('name', '').lower().strip())
            if nome_catalogo == nome_busca:
                primary_muscles = ex.get('primaryMuscles', [])
                if primary_muscles and len(primary_muscles) > 0:
                    musculo_original = primary_muscles[0].lower()
                    musculo = mapa_musculos.get(musculo_original, musculo_original.title())
                    print(f"✅ Correspondência exata encontrada: {musculo}")
                    return musculo
        
        # 2. Nome do catálogo CONTÉM o nome buscado
        for ex in catalogo:
            nome_catalogo = remover_acentos(ex.get('name', '').lower())
            if nome_busca in nome_catalogo:
                primary_muscles = ex.get('primaryMuscles', [])
                if primary_muscles and len(primary_muscles) > 0:
                    musculo_original = primary_muscles[0].lower()
                    musculo = mapa_musculos.get(musculo_original, musculo_original.title())
                    print(f"✅ Correspondência parcial: {musculo}")
                    return musculo
        
        # 3. Nome buscado CONTÉM o nome do catálogo
        for ex in catalogo:
            nome_catalogo = remover_acentos(ex.get('name', '').lower())
            if nome_catalogo in nome_busca:
                primary_muscles = ex.get('primaryMuscles', [])
                if primary_muscles and len(primary_muscles) > 0:
                    musculo_original = primary_muscles[0].lower()
                    musculo = mapa_musculos.get(musculo_original, musculo_original.title())
                    print(f"✅ Correspondência inversa: {musculo}")
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