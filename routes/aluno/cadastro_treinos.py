"""
Rotas da tela "Cadastrar Treinos" -- fluxo unificado que substitui as
antigas telas separadas de "Nova Versão" (aluno.nova_versao) e
"Adicionar Treino à Versão" (aluno.novo_treino_versao):

- Cria a versão sem pedir data de início (usa a data do servidor) nem
  divisão fixa ABC/ABCD/ABCDE (o usuário escolhe quantos treinos quiser,
  até o limite de VersaoService.MAX_TREINOS_POR_VERSAO).
- Não pede data de fim: ela só é gravada quando o usuário finaliza a
  versão explicitamente, com a data real da finalização.
- Na mesma tela: cria treinos dentro da versão e adiciona/edita os
  exercícios de cada treino.

Toda a lógica de validação/posse (IDOR) fica nos métodos novos de
VersaoService (create_livre, adicionar_treino_livre, salvar_treino_livre,
remover_treino_livre, finalizar_livre) -- as rotas aqui só traduzem
request -> service e cuidam de flash/redirect, seguindo o mesmo padrão
já usado no restante do blueprint aluno.
"""

import logging

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from . import aluno_bp
from extensions import limiter
from services.versao_service import VersaoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService

logger = logging.getLogger(__name__)


def _chave_por_usuario():
    return f"cadastrar-treinos-{current_user.id}"


@aluno_bp.route('/cadastrar-treinos')
@login_required
def cadastrar_treinos():
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    versao_ativa = VersaoService.get_ativa(user_id=current_user.id)

    treinos_versao = []
    exercicios_catalogo = []
    musculos_catalogo = []
    treino_exercicios_map = {}
    treino_observacoes_map = {}

    if versao_ativa:
        # load_relations=True traz treinos + exercícios em poucas queries
        # (joinedload), evitando N+1 ao montar o mapa abaixo.
        versao_ativa = VersaoService.get_by_id(
            versao_ativa.id, user_id=current_user.id, load_relations=True
        )
        treinos_versao = sorted(versao_ativa.treinos, key=lambda tv: tv.ordem or 0)

        exercicios_catalogo = ExercicioService.get_exercicios_completos(user_id=current_user.id)
        musculos_catalogo = MusculoService.get_all_nomes()

        for tv in treinos_versao:
            ids_prefixados = []
            observacoes_tv = {}
            for ve in tv.exercicios:
                if ve.exercicio_usuario_id is not None:
                    chave = f"u_{ve.exercicio_usuario_id}"
                elif ve.exercicio_base_id is not None:
                    chave = f"b_{ve.exercicio_base_id}"
                else:
                    continue
                ids_prefixados.append(chave)
                if ve.observacao:
                    observacoes_tv[chave] = ve.observacao
            treino_exercicios_map[tv.id] = ids_prefixados
            treino_observacoes_map[tv.id] = observacoes_tv

    return render_template(
        'aluno/cadastrar_treinos.html',
        versao=versao_ativa,
        treinos_versao=treinos_versao,
        exercicios_catalogo=exercicios_catalogo,
        musculos_catalogo=musculos_catalogo,
        treino_exercicios_map=treino_exercicios_map,
        treino_observacoes_map=treino_observacoes_map,
        max_treinos=VersaoService.MAX_TREINOS_POR_VERSAO,
    )


@aluno_bp.route('/cadastrar-treinos/versao', methods=['POST'])
@login_required
@limiter.limit("20 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_criar_versao():
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    descricao = request.form.get('descricao', '')
    try:
        VersaoService.create_livre(descricao, user_id=current_user.id)
        flash('Versão criada! Agora adicione os treinos.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao criar versão (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))


@aluno_bp.route('/cadastrar-treinos/<int:versao_id>/editar', methods=['POST'])
@login_required
@limiter.limit("30 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_editar_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    descricao = request.form.get('descricao', '')
    try:
        VersaoService.editar_descricao_livre(versao_id, descricao, user_id=current_user.id)
        flash('Versão atualizada!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao editar versão (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))


@aluno_bp.route('/cadastrar-treinos/<int:versao_id>/treino', methods=['POST'])
@login_required
@limiter.limit("60 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_adicionar_treino(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    try:
        VersaoService.adicionar_treino_livre(
            versao_id, nome_treino, descricao_treino, user_id=current_user.id
        )
        flash('Treino adicionado! Agora selecione os exercícios.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao adicionar treino (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))


@aluno_bp.route('/cadastrar-treinos/<int:versao_id>/treino/<int:treino_versao_id>', methods=['POST'])
@login_required
@limiter.limit("120 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_salvar_treino(versao_id, treino_versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    exercicios_raw = request.form.getlist('exercicios[]')
    # Observação por exercício (campo observacao_<chave>, até 60 chars) --
    # mesmo padrão usado em aluno.editar_treino_versao.
    observacoes = {
        chave: request.form.get(f'observacao_{chave}', '').strip()[:60]
        for chave in exercicios_raw if chave and chave.strip()
    }
    try:
        VersaoService.salvar_treino_livre(
            versao_id, treino_versao_id, nome_treino, descricao_treino,
            exercicios_raw, user_id=current_user.id, observacoes=observacoes
        )
        flash('Treino salvo com sucesso!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao salvar treino (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))


@aluno_bp.route('/cadastrar-treinos/<int:versao_id>/treino/<int:treino_versao_id>/remover', methods=['POST'])
@login_required
@limiter.limit("60 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_remover_treino(versao_id, treino_versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    try:
        VersaoService.remover_treino_livre(versao_id, treino_versao_id, user_id=current_user.id)
        flash('Treino removido da versão.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao remover treino (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))


@aluno_bp.route('/cadastrar-treinos/<int:versao_id>/finalizar', methods=['POST'])
@login_required
@limiter.limit("10 per hour", key_func=_chave_por_usuario)
def cadastrar_treinos_finalizar(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    try:
        versao = VersaoService.finalizar_livre(versao_id, user_id=current_user.id)
        flash(f'Versão {versao.numero_versao} finalizada! Crie uma nova versão quando quiser.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao finalizar versão (cadastro livre)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.cadastrar_treinos'))