"""Dados da tela da ficha (templates/aluno/ver_versao.html), a mesma tela
para a ficha ativa ("Cadastrar treinos"), para qualquer ficha do aluno
("Minhas fichas" > ficha) e para a ficha de um aluno vista pelo professor
(lote 6d, T2).

O catálogo de exercícios NÃO é montado aqui: os cartões do editor chegam
por uma requisição à parte (catalogo_url, editar-treino-versao.js). Antes
as três rotas carregavam os ~1.360 exercícios a cada abertura só para
contar quantos eram (~70 ms por página, ~400 ms na primeira).
"""
from utils.meta_treino import meta_para_json


def chave_exercicio(ve):
    """'u_<id>' (exercício do usuário) ou 'b_<id>' (catálogo); None se nenhum."""
    if ve.exercicio_usuario_id is not None:
        return f"u_{ve.exercicio_usuario_id}"
    if ve.exercicio_base_id is not None:
        return f"b_{ve.exercicio_base_id}"
    return None


def mapas_da_ficha(treinos_versao):
    """Exercícios, observações e metas de cada treino, no formato que o
    editor (cadastrar-treinos.js) usa para abrir o modal já preenchido:
    ({tv.id: [chave]}, {tv.id: {chave: obs}}, {tv.id: {chave: meta}})."""
    exercicios, observacoes, metas = {}, {}, {}
    for tv in treinos_versao:
        chaves, obs_tv, metas_tv = [], {}, {}
        for ve in tv.exercicios:
            chave = chave_exercicio(ve)
            if chave is None:
                continue
            chaves.append(chave)
            if ve.observacao:
                obs_tv[chave] = ve.observacao
            if ve.meta_series or ve.meta_reps_min:
                metas_tv[chave] = meta_para_json(ve.meta_series, ve.meta_reps_min, ve.meta_reps_max)
        exercicios[tv.id] = chaves
        observacoes[tv.id] = obs_tv
        metas[tv.id] = metas_tv
    return exercicios, observacoes, metas
