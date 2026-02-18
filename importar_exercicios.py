import json
from pathlib import Path
import os
import sys

# Adicionar o diretório raiz ao path para importar a aplicação
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def importar_exercicios():
    """Importa exercícios do arquivo JSON completo para o formato da aplicação"""
    
    # Caminhos dos arquivos
    arquivo_origem = Path("storage/exercises-ptbr-full-translation.json")
    arquivo_destino = Path("storage/exercicios.json")
    arquivo_musculos = Path("storage/musculos.json")
    
    if not arquivo_origem.exists():
        print(f"Arquivo {arquivo_origem} não encontrado!")
        return
    
    # Carregar arquivo de origem
    with open(arquivo_origem, 'r', encoding='utf-8') as f:
        exercicios_origem = json.load(f)
    
    # Mapeamento de treinos (você pode ajustar conforme necessidade)
    # Como o arquivo não tem informação de treino, vamos distribuir
    treinos_disponiveis = ['A', 'B', 'C', 'D', 'E']
    exercicios_convertidos = []
    musculos_set = set()
    
    for i, ex in enumerate(exercicios_origem):
        # Pegar o primeiro músculo primário como principal
        musculo_principal = ex['primaryMuscles'][0] if ex['primaryMuscles'] else "Outros"
        musculos_set.add(musculo_principal)
        
        # Distribuir exercícios entre os treinos (rotativo)
        treino = treinos_disponiveis[i % len(treinos_disponiveis)]
        
        exercicio = {
            "id": i + 1,  # ID sequencial
            "nome": ex['name'],
            "musculo": musculo_principal,
            "treino": treino,
            "instrucoes": ex['instructions'],  # Guardar as instruções
            "equipamento": ex['equipment'],
            "nivel": ex['level'],
            "categoria": ex['category'],
            "musculos_secundarios": ex['secondaryMuscles'],
            "imagens": ex.get('images', [])
        }
        exercicios_convertidos.append(exercicio)
    
    # Salvar exercícios
    with open(arquivo_destino, 'w', encoding='utf-8') as f:
        json.dump(exercicios_convertidos, f, indent=2, ensure_ascii=False)
    
    # Salvar lista de músculos
    musculos_lista = sorted(list(musculos_set))
    with open(arquivo_musculos, 'w', encoding='utf-8') as f:
        json.dump(musculos_lista, f, indent=2, ensure_ascii=False)
    
    print(f"✅ {len(exercicios_convertidos)} exercícios importados com sucesso!")
    print(f"✅ {len(musculos_lista)} músculos identificados")
    return exercicios_convertidos

if __name__ == "__main__":
    importar_exercicios()