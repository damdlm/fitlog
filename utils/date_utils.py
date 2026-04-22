"""
Utilitários para manipulação de datas no FitLog
"""

import re
from datetime import datetime
import calendar

# Mapeamento de meses (nome para número)
MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12
}

# Mapeamento reverso (número do mês para nome)
MESES_REVERSO = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

# ============================================================================
# FUNÇÕES DE CONVERSÃO (EXISTENTES)
# ============================================================================

def converter_periodo_para_data(periodo_str):
    """
    Converte strings de período como "Janeiro/2024", "Março-26" ou "Fevereiro 2024"
    em uma data no formato YYYY-MM-DD (primeiro dia do mês)
    
    Args:
        periodo_str: String do período (ex: "Janeiro/2024")
    
    Returns:
        str: Data no formato YYYY-MM-DD
    """
    if not periodo_str:
        return datetime.now().strftime("%Y-%m-%d")
    
    periodo_limpo = periodo_str.strip().lower()
    
    # Padrão 1: "Mês/Ano" ou "Mês-Ano" ou "Mês Ano"
    padrao1 = re.match(r'([a-zA-Zçãõáéíóú]+)[/\-\s]+(\d{2,4})', periodo_limpo)
    if padrao1:
        mes_nome = padrao1.group(1).lower()
        ano = padrao1.group(2)
        
        # Converter ano para 4 dígitos
        if len(ano) == 2:
            ano = f"20{ano}" if int(ano) <= 50 else f"19{ano}"
        
        # Obter número do mês
        mes_num = MESES.get(mes_nome)
        if mes_num:
            return f"{ano}-{mes_num:02d}-01"
    
    # Padrão 2: Apenas o mês (assume ano atual)
    padrao2 = re.match(r'([a-zA-Zçãõáéíóú]+)', periodo_limpo)
    if padrao2:
        mes_nome = padrao2.group(1).lower()
        mes_num = MESES.get(mes_nome)
        if mes_num:
            ano_atual = datetime.now().year
            return f"{ano_atual}-{mes_num:02d}-01"
    
    # Fallback
    print(f"Aviso: Não foi possível converter período '{periodo_str}'. Usando data atual.")
    return datetime.now().strftime("%Y-%m-%d")


def ordenar_periodos(periodos):
    """Ordena lista de períodos (ex: ['Janeiro/2024', 'Fevereiro/2024'])"""
    def chave_ordenacao(periodo):
        partes = periodo.split('/')
        if len(partes) != 2:
            return (9999, 0)
        
        mes_nome = partes[0].lower()
        ano = int(partes[1])
        mes_num = MESES.get(mes_nome, 0)
        return (ano, mes_num)
    
    return sorted(periodos, key=chave_ordenacao, reverse=True)


# ============================================================================
# FUNÇÕES PARA REGISTRO POR DATA
# ============================================================================

def formatar_data_br(data_str):
    """
    Converte data ISO (YYYY-MM-DD) para formato brasileiro (DD/MM/YYYY)
    Função auxiliar que pode ser usada como fallback
    
    Args:
        data_str: string no formato YYYY-MM-DD ou objeto date
    
    Returns:
        str: data formatada no padrão brasileiro
    """
    if not data_str:
        return ""
    
    try:
        from datetime import datetime
        # Se for objeto date
        if hasattr(data_str, 'strftime'):
            return data_str.strftime('%d/%m/%Y')
        
        data = datetime.strptime(data_str, '%Y-%m-%d')
        return data.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return str(data_str)


def data_para_periodo(data):
    """
    Converte objeto date para formato "Mês/Ano"
    
    Args:
        data: objeto date
    
    Returns:
        str: "Janeiro/2024"
    
    Exemplo:
        >>> from datetime import date
        >>> data_para_periodo(date(2024, 3, 15))
        'Março/2024'
    """
    if not data:
        return ""
    
    return f"{MESES_REVERSO[data.month]}/{data.year}"


def data_para_semana(data):
    """
    Retorna o número da semana do ano (padrão ISO)
    
    Args:
        data: objeto date
    
    Returns:
        int: número da semana (1-53)
    
    Exemplo:
        >>> from datetime import date
        >>> data_para_semana(date(2024, 3, 15))
        11
    """
    if not data:
        return 1
    
    return data.isocalendar()[1]


def validar_data(data_str):
    """
    Valida se a string é uma data válida no formato YYYY-MM-DD
    
    Args:
        data_str: string a ser validada
    
    Returns:
        tuple: (bool, objeto date ou mensagem de erro)
    
    Exemplo:
        >>> sucesso, resultado = validar_data('2024-03-15')
        >>> if sucesso:
        ...     print(resultado)  # objeto date
        ... else:
        ...     print(resultado)  # mensagem de erro
    """
    if not data_str:
        return False, "Data não fornecida"
    
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Validar se não é data futura
        if data > datetime.now().date():
            return False, "Data não pode ser futura"
        
        return True, data
        
    except ValueError:
        return False, "Formato de data inválido. Use YYYY-MM-DD"


def obter_semanas_do_mes(ano, mes):
    """
    Retorna lista de semanas contidas em um mês
    
    Args:
        ano: ano (ex: 2024)
        mes: mês (1-12)
    
    Returns:
        list: números das semanas
    
    Exemplo:
        >>> obter_semanas_do_mes(2024, 3)
        [9, 10, 11, 12, 13]  # semanas que tocam março/2024
    """
    semanas = set()
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    
    for dia in range(1, ultimo_dia + 1):
        data = datetime(ano, mes, dia).date()
        semanas.add(data.isocalendar()[1])
    
    return sorted(list(semanas))


def obter_dias_do_mes(ano, mes):
    """
    Retorna lista de todos os dias de um mês
    
    Args:
        ano: ano (ex: 2024)
        mes: mês (1-12)
    
    Returns:
        list: objetos date
    """
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    
    dias = []
    for dia in range(1, ultimo_dia + 1):
        dias.append(datetime(ano, mes, dia).date())
    
    return dias


def calcular_diferenca_dias(data_inicio, data_fim):
    """
    Calcula a diferença em dias entre duas datas
    
    Args:
        data_inicio: data inicial
        data_fim: data final
    
    Returns:
        int: número de dias
    
    Exemplo:
        >>> from datetime import date
        >>> calcular_diferenca_dias(date(2024, 3, 1), date(2024, 3, 15))
        14
    """
    if not data_inicio or not data_fim:
        return 0
    
    return (data_fim - data_inicio).days


def primeiro_dia_do_mes(ano, mes):
    """
    Retorna o primeiro dia do mês
    
    Args:
        ano: ano
        mes: mês
    
    Returns:
        date: primeiro dia do mês
    """
    return datetime(ano, mes, 1).date()


def ultimo_dia_do_mes(ano, mes):
    """
    Retorna o último dia do mês
    
    Args:
        ano: ano
        mes: mês
    
    Returns:
        date: último dia do mês
    """
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return datetime(ano, mes, ultimo_dia).date()


def nome_do_mes(numero_mes):
    """
    Retorna o nome do mês em português
    
    Args:
        numero_mes: número do mês (1-12)
    
    Returns:
        str: nome do mês
    """
    return MESES_REVERSO.get(numero_mes, "")


def numero_do_mes(nome_mes):
    """
    Retorna o número do mês a partir do nome
    
    Args:
        nome_mes: nome do mês em português
    
    Returns:
        int: número do mês ou 0 se não encontrado
    """
    return MESES.get(nome_mes.lower(), 0)


def extrair_mes_ano(periodo):
    """
    Extrai mês e ano de uma string de período
    
    Args:
        periodo: string no formato "Mês/Ano" (ex: "Janeiro/2024")
    
    Returns:
        tuple: (mes_numero, ano) ou (None, None) se inválido
    """
    if not periodo or '/' not in periodo:
        return None, None
    
    partes = periodo.split('/')
    if len(partes) != 2:
        return None, None
    
    mes_nome = partes[0].strip()
    ano_str = partes[1].strip()
    
    mes_num = MESES.get(mes_nome.lower())
    if not mes_num:
        return None, None
    
    try:
        ano = int(ano_str)
        return mes_num, ano
    except ValueError:
        return None, None