"""
Dados de treinos e exercícios pré-definidos para novos usuários
"""

# =============================================
# TREINOS 3x POR SEMANA (A, B, C)
# =============================================

WORKOUTS_3X = {
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

# =============================================
# TREINOS 4x POR SEMANA (A, B, C, D)
# =============================================

WORKOUTS_4X = {
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

# =============================================
# TREINOS 5x POR SEMANA (A, B, C, D, E)
# =============================================

WORKOUTS_5X = {
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

# Mapeamento de músculos para garantir consistência
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