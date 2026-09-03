import logging

logger = logging.getLogger(__name__)

# ===== FUNÇÕES PARA VERIFICAR ONDE UM EXERCÍCIO É USADO =====

def verificar_exercicio_em_versoes(exercicio_id, tipo_exercicio=None):
    """
    Verifica em quais versões e treinos um exercício está presente

    Args:
        exercicio_id: ID do exercício
        tipo_exercicio: 'usuario' ou 'base' (se None, busca em ambos)
    """
    from models import VersaoExercicio

    resultados = []

    if tipo_exercicio is None or tipo_exercicio == 'usuario':
        ocorrencias_usuario = VersaoExercicio.query.filter_by(
            exercicio_usuario_id=exercicio_id
        ).all()

        for ve in ocorrencias_usuario:
            treino_versao = ve.treino_versao
            if treino_versao:
                versao = treino_versao.versao_ref
                resultados.append({
                    "versao_id": versao.id,
                    "versao": versao.numero_versao,
                    "versao_descricao": versao.descricao,
                    "treino_id": treino_versao.codigo,
                    "data_inicio": versao.data_inicio.isoformat() if versao.data_inicio else None,
                    "data_fim": versao.data_fim.isoformat() if versao.data_fim else None,
                    "tipo": "usuario"
                })

    if tipo_exercicio is None or tipo_exercicio == 'base':
        ocorrencias_base = VersaoExercicio.query.filter_by(
            exercicio_base_id=exercicio_id
        ).all()

        for ve in ocorrencias_base:
            treino_versao = ve.treino_versao
            if treino_versao:
                versao = treino_versao.versao_ref
                resultados.append({
                    "versao_id": versao.id,
                    "versao": versao.numero_versao,
                    "versao_descricao": versao.descricao,
                    "treino_id": treino_versao.codigo,
                    "data_inicio": versao.data_inicio.isoformat() if versao.data_inicio else None,
                    "data_fim": versao.data_fim.isoformat() if versao.data_fim else None,
                    "tipo": "base"
                })

    return resultados

# ===== FUNÇÕES DE COMPATIBILIDADE =====
# Mantidas porque ainda são importadas em tests/unit/test_utils/test_version_utils.py
# -- sempre retornaram valores fixos, nunca dependeram de utils.db_utils.

def get_versoes_treino_antigo(treino_id=None):
    """Compatibilidade: retorna lista vazia"""
    return []

def get_versao_ativa_antiga(treino_id, periodo):
    """Compatibilidade: retorna None"""
    return None

def get_exercicios_por_versao_antiga(versao_id):
    """Compatibilidade: retorna lista vazia"""
    return []