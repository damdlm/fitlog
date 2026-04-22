"""
Divisões de treino pré-definidas para serem usadas nas versões
"""

# =============================================
# DIVISÃO 3x POR SEMANA (A, B, C)
# =============================================

SPLIT_3X = {
    "nome": "Divisão 3x (ABC)",
    "descricao": "Peito/Ombro/Tríceps, Costas/Bíceps, Pernas",
    "frequencia": "3x",
    "treinos": {
        "A": {
            "nome": "Peito, Ombro e Tríceps",
            "descricao": "Treino A - Peito, Ombro e Tríceps",
            "exercicios": [
                # Peito
                {"nome": "Supino Reto com Barra", "musculo": "Peitoral"},
                {"nome": "Supino Inclinado com Halteres", "musculo": "Peitoral"},
                {"nome": "Crucifixo com Halteres", "musculo": "Peitoral"},
                {"nome": "Crossover na Polia", "musculo": "Peitoral"},
                
                # Ombro
                {"nome": "Desenvolvimento com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Lateral com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Frontal com Halteres", "musculo": "Ombros"},
                {"nome": "Crucifixo Inverso", "musculo": "Ombros"},
                
                # Tríceps
                {"nome": "Tríceps Pulley", "musculo": "Tríceps"},
                {"nome": "Tríceps Testa com Barra W", "musculo": "Tríceps"},
                {"nome": "Mergulho no Banco", "musculo": "Tríceps"},
            ]
        },
        "B": {
            "nome": "Costas e Bíceps",
            "descricao": "Treino B - Costas e Bíceps",
            "exercicios": [
                # Costas
                {"nome": "Barra Fixa", "musculo": "Costas"},
                {"nome": "Remada Curvada com Barra", "musculo": "Costas"},
                {"nome": "Remada Unilateral com Halter", "musculo": "Costas"},
                {"nome": "Pulldown na Polia", "musculo": "Costas"},
                {"nome": "Pullover com Halter", "musculo": "Costas"},
                
                # Bíceps
                {"nome": "Rosca Direta com Barra", "musculo": "Bíceps"},
                {"nome": "Rosca Alternada com Halteres", "musculo": "Bíceps"},
                {"nome": "Rosca Martelo", "musculo": "Bíceps"},
                {"nome": "Rosca Scott com Halter", "musculo": "Bíceps"},
            ]
        },
        "C": {
            "nome": "Pernas Completa",
            "descricao": "Treino C - Pernas Completa",
            "exercicios": [
                # Quadríceps
                {"nome": "Agachamento com Barra", "musculo": "Quadríceps"},
                {"nome": "Leg Press", "musculo": "Quadríceps"},
                {"nome": "Cadeira Extensora", "musculo": "Quadríceps"},
                {"nome": "Afundo com Halteres", "musculo": "Quadríceps"},
                
                # Posterior
                {"nome": "Cadeira Flexora", "musculo": "Posterior de Coxa"},
                {"nome": "Levantamento Terra Romeno", "musculo": "Posterior de Coxa"},
                {"nome": "Stiff", "musculo": "Posterior de Coxa"},
                
                # Glúteos
                {"nome": "Elevação Pélvica", "musculo": "Glúteos"},
                {"nome": "Coice no Cabo", "musculo": "Glúteos"},
                
                # Panturrilhas
                {"nome": "Elevação de Panturrilha em Pé", "musculo": "Panturrilhas"},
                {"nome": "Elevação de Panturrilha Sentado", "musculo": "Panturrilhas"},
            ]
        }
    }
}

# =============================================
# DIVISÃO 4x POR SEMANA (A, B, C, D)
# =============================================

SPLIT_4X = {
    "nome": "Divisão 4x (ABCD)",
    "descricao": "Peito, Costas, Pernas, Ombros/Braços",
    "frequencia": "4x",
    "treinos": {
        "A": {
            "nome": "Peito",
            "descricao": "Treino A - Peito",
            "exercicios": [
                {"nome": "Supino Reto com Barra", "musculo": "Peitoral"},
                {"nome": "Supino Inclinado com Halteres", "musculo": "Peitoral"},
                {"nome": "Crucifixo com Halteres", "musculo": "Peitoral"},
                {"nome": "Crossover na Polia", "musculo": "Peitoral"},
                {"nome": "Supino Declinado com Barra", "musculo": "Peitoral"},
                {"nome": "Flexões", "musculo": "Peitoral"},
            ]
        },
        "B": {
            "nome": "Costas",
            "descricao": "Treino B - Costas",
            "exercicios": [
                {"nome": "Barra Fixa", "musculo": "Costas"},
                {"nome": "Remada Curvada com Barra", "musculo": "Costas"},
                {"nome": "Remada Unilateral com Halter", "musculo": "Costas"},
                {"nome": "Pulldown na Polia", "musculo": "Costas"},
                {"nome": "Pullover com Halter", "musculo": "Costas"},
                {"nome": "Remada Alta", "musculo": "Costas"},
            ]
        },
        "C": {
            "nome": "Pernas Completa",
            "descricao": "Treino C - Pernas Completa",
            "exercicios": [
                {"nome": "Agachamento com Barra", "musculo": "Quadríceps"},
                {"nome": "Leg Press", "musculo": "Quadríceps"},
                {"nome": "Cadeira Extensora", "musculo": "Quadríceps"},
                {"nome": "Cadeira Flexora", "musculo": "Posterior de Coxa"},
                {"nome": "Levantamento Terra Romeno", "musculo": "Posterior de Coxa"},
                {"nome": "Elevação Pélvica", "musculo": "Glúteos"},
                {"nome": "Elevação de Panturrilha em Pé", "musculo": "Panturrilhas"},
            ]
        },
        "D": {
            "nome": "Ombros e Braços",
            "descricao": "Treino D - Ombros e Braços",
            "exercicios": [
                # Ombros
                {"nome": "Desenvolvimento com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Lateral com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Frontal com Halteres", "musculo": "Ombros"},
                {"nome": "Crucifixo Inverso", "musculo": "Ombros"},
                
                # Tríceps
                {"nome": "Tríceps Pulley", "musculo": "Tríceps"},
                {"nome": "Tríceps Testa com Barra W", "musculo": "Tríceps"},
                {"nome": "Mergulho no Banco", "musculo": "Tríceps"},
                
                # Bíceps
                {"nome": "Rosca Direta com Barra", "musculo": "Bíceps"},
                {"nome": "Rosca Alternada com Halteres", "musculo": "Bíceps"},
                {"nome": "Rosca Martelo", "musculo": "Bíceps"},
                {"nome": "Rosca Scott com Halter", "musculo": "Bíceps"},
            ]
        }
    }
}

# =============================================
# DIVISÃO 5x POR SEMANA (A, B, C, D, E)
# =============================================

SPLIT_5X = {
    "nome": "Divisão 5x (ABCDE)",
    "descricao": "Peito, Costas, Pernas, Ombros, Braços",
    "frequencia": "5x",
    "treinos": {
        "A": {
            "nome": "Peito",
            "descricao": "Treino A - Peito",
            "exercicios": [
                {"nome": "Supino Reto com Barra", "musculo": "Peitoral"},
                {"nome": "Supino Inclinado com Halteres", "musculo": "Peitoral"},
                {"nome": "Crucifixo com Halteres", "musculo": "Peitoral"},
                {"nome": "Crossover na Polia", "musculo": "Peitoral"},
                {"nome": "Flexões", "musculo": "Peitoral"},
            ]
        },
        "B": {
            "nome": "Costas",
            "descricao": "Treino B - Costas",
            "exercicios": [
                {"nome": "Barra Fixa", "musculo": "Costas"},
                {"nome": "Remada Curvada com Barra", "musculo": "Costas"},
                {"nome": "Remada Unilateral com Halter", "musculo": "Costas"},
                {"nome": "Pulldown na Polia", "musculo": "Costas"},
                {"nome": "Pullover com Halter", "musculo": "Costas"},
            ]
        },
        "C": {
            "nome": "Pernas",
            "descricao": "Treino C - Pernas",
            "exercicios": [
                {"nome": "Agachamento com Barra", "musculo": "Quadríceps"},
                {"nome": "Leg Press", "musculo": "Quadríceps"},
                {"nome": "Cadeira Extensora", "musculo": "Quadríceps"},
                {"nome": "Cadeira Flexora", "musculo": "Posterior de Coxa"},
                {"nome": "Levantamento Terra Romeno", "musculo": "Posterior de Coxa"},
                {"nome": "Elevação de Panturrilha em Pé", "musculo": "Panturrilhas"},
            ]
        },
        "D": {
            "nome": "Ombros",
            "descricao": "Treino D - Ombros",
            "exercicios": [
                {"nome": "Desenvolvimento com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Lateral com Halteres", "musculo": "Ombros"},
                {"nome": "Elevação Frontal com Halteres", "musculo": "Ombros"},
                {"nome": "Crucifixo Inverso", "musculo": "Ombros"},
                {"nome": "Encolhimento de Ombros", "musculo": "Ombros"},
            ]
        },
        "E": {
            "nome": "Braços",
            "descricao": "Treino E - Braços",
            "exercicios": [
                # Bíceps
                {"nome": "Rosca Direta com Barra", "musculo": "Bíceps"},
                {"nome": "Rosca Alternada com Halteres", "musculo": "Bíceps"},
                {"nome": "Rosca Martelo", "musculo": "Bíceps"},
                {"nome": "Rosca Scott com Halter", "musculo": "Bíceps"},
                
                # Tríceps
                {"nome": "Tríceps Pulley", "musculo": "Tríceps"},
                {"nome": "Tríceps Testa com Barra W", "musculo": "Tríceps"},
                {"nome": "Mergulho no Banco", "musculo": "Tríceps"},
                {"nome": "Tríceps Coice com Halter", "musculo": "Tríceps"},
            ]
        }
    }
}

# Lista de todas as divisões disponíveis
ALL_SPLITS = {
    "3x": SPLIT_3X,
    "4x": SPLIT_4X,
    "5x": SPLIT_5X,
}

# Mapeamento de músculos
MUSCLE_MAPPING = {
    "Peitoral": "Peitoral",
    "Ombros": "Ombros",
    "Tríceps": "Tríceps",
    "Costas": "Costas",
    "Bíceps": "Bíceps",
    "Quadríceps": "Quadríceps",
    "Posterior de Coxa": "Posterior de Coxa",
    "Glúteos": "Glúteos",
    "Panturrilhas": "Panturrilhas",
    "Abdômen": "Abdômen",
}