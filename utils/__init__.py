"""Pacote de utilitários da aplicação"""

from .date_utils import converter_periodo_para_data, MESES
from .exercise_utils import (
    buscar_musculo_no_catalogo, get_series_from_registro,
    calcular_media_series, calcular_volume_total, remover_acentos
)
from .format_utils import (
    formatar_data, formatar_data_para_input, data_atual_formatada, data_atual_iso
)
from .validators import (  # 👈 Nome corrigido (plural)
    validar_treino_id, 
    validar_semana, 
    validar_carga,
    validar_repeticoes,
    validar_num_series,
    validar_periodo,
    validar_email,
    validar_senha
)
from .decorators import with_app_context, log_execution_time  # 👈 Nome corrigido (plural)

__all__ = [
    # Date utils
    'converter_periodo_para_data', 'MESES',
    
    # Exercise utils
    'buscar_musculo_no_catalogo', 'get_series_from_registro',
    'calcular_media_series', 'calcular_volume_total', 'remover_acentos',
    
    # Format utils
    'formatar_data', 'formatar_data_para_input', 'data_atual_formatada', 'data_atual_iso',
    
    # Validators
    'validar_treino_id', 'validar_semana', 'validar_carga',
    'validar_repeticoes', 'validar_num_series', 'validar_periodo',
    'validar_email', 'validar_senha',
    
    # Decorators
    'with_app_context', 'log_execution_time'
]