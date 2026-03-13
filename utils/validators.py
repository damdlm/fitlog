"""Módulo de validações para a aplicação"""

import re

def validar_treino_id(treino_id):
    """
    Valida se o ID do treino é uma letra maiúscula única
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not treino_id:
        return False, "ID do treino é obrigatório"
    
    treino_id = treino_id.strip().upper()
    
    if len(treino_id) != 1:
        return False, "ID deve ter exatamente 1 caractere"
    
    if not treino_id.isalpha():
        return False, "ID deve ser uma letra"
    
    return True, treino_id

def validar_semana(semana):
    """
    Valida se o número da semana é válido (1-52)
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        semana_int = int(semana)
        if semana_int < 1 or semana_int > 52:
            return False, "Semana deve estar entre 1 e 52"
        return True, semana_int
    except (ValueError, TypeError):
        return False, "Semana deve ser um número válido"

def validar_carga(carga):
    """
    Valida se a carga é um número positivo
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        carga_float = float(carga)
        if carga_float < 0:
            return False, "Carga não pode ser negativa"
        if carga_float > 999:
            return False, "Carga muito alta (máx 999kg)"
        return True, carga_float
    except (ValueError, TypeError):
        return False, "Carga deve ser um número válido"

def validar_repeticoes(repeticoes):
    """
    Valida se o número de repetições é um inteiro positivo
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        reps_int = int(repeticoes)
        if reps_int < 0:
            return False, "Repetições não podem ser negativas"
        if reps_int > 100:
            return False, "Número de repetições muito alto (máx 100)"
        return True, reps_int
    except (ValueError, TypeError):
        return False, "Repetições devem ser um número válido"

def validar_num_series(num_series):
    """
    Valida se o número de séries é um inteiro entre 1 e 10
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        series_int = int(num_series)
        if series_int < 1 or series_int > 10:
            return False, "Número de séries deve estar entre 1 e 10"
        return True, series_int
    except (ValueError, TypeError):
        return False, "Número de séries deve ser um número válido"

def validar_periodo(periodo):
    """
    Valida se o período está no formato correto (ex: Janeiro/2024)
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not periodo:
        return False, "Período é obrigatório"
    
    # Padrão: Mês/Ano ou Mês Ano
    padrao = re.match(r'^([A-Za-zçãõáéíóú]+)[/\s]+(\d{4})$', periodo.strip())
    if not padrao:
        return False, "Formato inválido. Use: Mês/Ano (ex: Janeiro/2024)"
    
    return True, periodo.strip()

def validar_email(email):
    """
    Valida formato de email
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not email:
        return False, "Email é obrigatório"
    
    padrao = re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)
    if not padrao:
        return False, "Email inválido"
    
    return True, email

def validar_senha(senha):
    """
    Valida se a senha atende aos requisitos mínimos
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not senha:
        return False, "Senha é obrigatória"
    
    if len(senha) < 6:
        return False, "Senha deve ter pelo menos 6 caracteres"
    
    return True, senha