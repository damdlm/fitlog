from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


def _agora_brasil():
    """Retorna o datetime atual no fuso horário de Brasília (America/Sao_Paulo).

    O servidor roda em UTC, então usar datetime.now() puro fazia o app
    considerar "hoje" com até 3h de adiantamento em relação ao horário
    real do usuário no Brasil (ex: 21h-23h59 em BR já é o dia seguinte em UTC).
    """
    return datetime.now(FUSO_BRASIL)


def data_atual():
    """Data de hoje em Brasília (date). Use no lugar de
    datetime.now(timezone.utc).date(), que das 21h à meia-noite já é o
    dia seguinte."""
    return _agora_brasil().date()


def formatar_datahora_br(valor, formato='%d/%m/%Y %H:%M'):
    """Formata um datetime guardado em UTC no horário de Brasília.

    O banco e o servidor trabalham em UTC (ver `_agora_brasil`), então
    imprimir `valor.strftime(...)` direto mostrava 3h a mais na tela.
    Datetime sem fuso (naive) é tratado como UTC. Retorna '—' se vazio.
    """
    if not valor:
        return '\u2014'
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(FUSO_BRASIL).strftime(formato)


def formatar_numero_br(valor, casas=1):
    """Número no formato brasileiro: milhar com ponto, decimal com vírgula,
    até `casas` casas decimais e sem zeros sobrando à direita.
    104025 -> "104.025" · 32.5 -> "32,5" · 40.0 -> "40". Vazio -> "—"."""
    if valor is None or valor == '':
        return '\u2014'
    try:
        numero = round(float(valor), casas)
    except (TypeError, ValueError):
        return str(valor)
    texto = f"{numero:,.{casas}f}" if casas > 0 else f"{numero:,.0f}"
    if casas > 0:
        texto = texto.rstrip('0').rstrip('.')
    # 1,234.5 (formato en) -> 1.234,5 (formato pt-BR)
    return texto.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def formatar_kg(valor, casas=1):
    """Peso para exibição: "104.025 kg", "32,5 kg"."""
    texto = formatar_numero_br(valor, casas)
    return texto if texto == '\u2014' else f"{texto} kg"


def formatar_data(data_str):
    """
    Converte data do formato YYYY-MM-DD para DD/MM/AAAA
    Se a data for inválida ou None, retorna string vazia
    
    Args:
        data_str: string no formato YYYY-MM-DD ou objeto date
    
    Returns:
        str: data formatada no padrão brasileiro
    
    Exemplo:
        >>> formatar_data('2024-03-15')
        '15/03/2024'
    """
    if not data_str:
        return ""
    
    try:
        # Se for objeto date, converte para string ISO primeiro
        if hasattr(data_str, 'strftime'):
            return data_str.strftime("%d/%m/%Y")
        
        # Tenta converter do formato ISO (YYYY-MM-DD)
        data = datetime.strptime(str(data_str), "%Y-%m-%d")
        return data.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        # Se não conseguir converter, retorna o original
        return str(data_str)


def formatar_data_para_input(data_str):
    """
    Converte data do formato DD/MM/AAAA para YYYY-MM-DD para uso em inputs date
    
    Args:
        data_str: string no formato DD/MM/AAAA
    
    Returns:
        str: data no formato YYYY-MM-DD
    
    Exemplo:
        >>> formatar_data_para_input('15/03/2024')
        '2024-03-15'
    """
    if not data_str:
        return ""
    
    try:
        # Se for objeto date, já está no formato correto
        if hasattr(data_str, 'strftime'):
            return data_str.strftime("%Y-%m-%d")
        
        # Tenta converter do formato brasileiro
        data = datetime.strptime(data_str, "%d/%m/%Y")
        return data.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return data_str


def data_atual_formatada():
    """Retorna a data atual (horário de Brasília) no formato DD/MM/AAAA"""
    return _agora_brasil().strftime("%d/%m/%Y")


def data_atual_iso():
    """Retorna a data atual (horário de Brasília) no formato YYYY-MM-DD para inputs"""
    return _agora_brasil().strftime("%Y-%m-%d")


def formatar_data_completa(data_str):
    """
    Formata data por extenso (ex: 15 de março de 2024)
    
    Args:
        data_str: string no formato YYYY-MM-DD ou objeto date
    
    Returns:
        str: data por extenso
    """
    if not data_str:
        return ""
    
    meses = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }
    
    try:
        if hasattr(data_str, 'strftime'):
            data = data_str
        else:
            data = datetime.strptime(str(data_str), "%Y-%m-%d")
        
        return f"{data.day} de {meses[data.month]} de {data.year}"
    except (ValueError, TypeError):
        return str(data_str)


def formatar_horario(data_str):
    """
    Formata data e hora (ex: 15/03/2024 14:30)
    
    Args:
        data_str: string no formato YYYY-MM-DD HH:MM:SS ou objeto datetime
    
    Returns:
        str: data e hora formatada
    """
    if not data_str:
        return ""
    
    try:
        if hasattr(data_str, 'strftime'):
            return data_str.strftime("%d/%m/%Y %H:%M")
        else:
            data = datetime.strptime(str(data_str), "%Y-%m-%d %H:%M:%S")
            return data.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(data_str)