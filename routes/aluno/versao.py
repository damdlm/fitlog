"""
Rotas de "Minhas Versões" -- histórico de versões do aluno (ativa e
finalizadas), reconstruída após a remoção da tabela `treinos`
compartilhada (ver migration e1f2a3b4c5d6).

Diferente da tela "Cadastrar Treinos" (routes/aluno/cadastro_treinos.py),
que só enxerga a versão ATIVA, aqui o aluno pode ver e editar QUALQUER
versão sua, inclusive as já finalizadas -- por isso todas as chamadas ao
VersaoService abaixo passam permitir_finalizada=True. As travas de posse
(IDOR) e de integridade de histórico (RegistroTreino) continuam
aplicadas pelo service independente disso.
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
    return f"minhas-versoes-{current_user.id}"


def _acesso_negado():
    flash('Acesso negado.', 'danger')
    return redirect(url_for('main.index'))


@aluno_bp.route('/versoes')
@login_required
def versoes():
    """Lista todas as versões do aluno (ativa + finalizadas), mais recente primeiro."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    todas_versoes = VersaoService.get_all(user_id=current_user.id)
    return render_template(
        'aluno/versoes.html',
        versoes=todas_versoes,
        titulo='Minhas Versões',
        voltar_url=url_for('aluno.cadastrar_treinos'),
        voltar_label='Cadastrar Treinos',
        ver_versao_url=lambda vid: url_for('aluno.ver_versao', versao_id=vid),
    )


@aluno_bp.route('/versao/<int:versao_id>')
@login_required
def ver_versao(versao_id):
    """Detalhe de uma versão (ativa ou finalizada): treinos + exercícios."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))

    treinos_versao = sorted(versao.treinos, key=lambda tv: tv.ordem or 0)
    exercicios_catalogo = ExercicioService.get_exercicios_completos(user_id=current_user.id)
    musculos_catalogo = MusculoService.get_all_nomes()

    treino_exercicios_map = {}
    treino_observacoes_map = {}
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
        'aluno/ver_versao.html',
        versao=versao,
        treinos_versao=treinos_versao,
        exercicios_catalogo=exercicios_catalogo,
        musculos_catalogo=musculos_catalogo,
        treino_exercicios_map=treino_exercicios_map,
        treino_observacoes_map=treino_observacoes_map,
        max_treinos=VersaoService.MAX_TREINOS_POR_VERSAO,
        voltar_url=url_for('aluno.versoes'),
        voltar_label='Minhas Versões',
        finalizar_url=url_for('aluno.versao_finalizar', versao_id=versao.id),
        clonar_url=url_for('aluno.versao_clonar', versao_id=versao.id),
        excluir_url=url_for('aluno.versao_excluir', versao_id=versao.id),
        editar_descricao_url=url_for('aluno.versao_editar_descricao', versao_id=versao.id),
        adicionar_treino_url=url_for('aluno.versao_adicionar_treino', versao_id=versao.id),
        salvar_treino_url=lambda tv_id: url_for('aluno.versao_salvar_treino', versao_id=versao.id, treino_versao_id=tv_id),
        remover_treino_url=lambda tv_id: url_for('aluno.versao_remover_treino', versao_id=versao.id, treino_versao_id=tv_id),
        novo_exercicio_url=url_for('aluno.novo_exercicio'),
    )


@aluno_bp.route('/versao/<int:versao_id>/editar', methods=['POST'])
@login_required
@limiter.limit("30 per hour", key_func=_chave_por_usuario)
def versao_editar_descricao(versao_id):
    """Edita a descrição de uma versão -- ativa ou finalizada."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    descricao = request.form.get('descricao', '')
    try:
        VersaoService.editar_descricao_livre(
            versao_id, descricao, user_id=current_user.id, permitir_finalizada=True
        )
        flash('Versão atualizada!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao editar versão (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/treino', methods=['POST'])
@login_required
@limiter.limit("60 per hour", key_func=_chave_por_usuario)
def versao_adicionar_treino(versao_id):
    """Adiciona um treino a uma versão -- ativa ou finalizada."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    try:
        VersaoService.adicionar_treino_livre(
            versao_id, nome_treino, descricao_treino,
            user_id=current_user.id, permitir_finalizada=True
        )
        flash('Treino adicionado! Agora selecione os exercícios.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao adicionar treino (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/treino/<int:treino_versao_id>', methods=['POST'])
@login_required
@limiter.limit("120 per hour", key_func=_chave_por_usuario)
def versao_salvar_treino(versao_id, treino_versao_id):
    """Salva nome/descrição/exercícios de um treino -- versão ativa ou finalizada."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    exercicios_raw = request.form.getlist('exercicios[]')
    observacoes = {
        chave: request.form.get(f'observacao_{chave}', '').strip()[:60]
        for chave in exercicios_raw if chave and chave.strip()
    }
    try:
        VersaoService.salvar_treino_livre(
            versao_id, treino_versao_id, nome_treino, descricao_treino,
            exercicios_raw, user_id=current_user.id, observacoes=observacoes,
            permitir_finalizada=True
        )
        flash('Treino salvo com sucesso!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao salvar treino (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/treino/<int:treino_versao_id>/remover', methods=['POST'])
@login_required
@limiter.limit("60 per hour", key_func=_chave_por_usuario)
def versao_remover_treino(versao_id, treino_versao_id):
    """Remove um treino de uma versão -- ativa ou finalizada (bloqueado
    pelo service se já houver histórico de registro para esse treino)."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    try:
        VersaoService.remover_treino_livre(
            versao_id, treino_versao_id, user_id=current_user.id, permitir_finalizada=True
        )
        flash('Treino removido da versão.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao remover treino (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/finalizar', methods=['POST'])
@login_required
@limiter.limit("10 per hour", key_func=_chave_por_usuario)
def versao_finalizar(versao_id):
    """Finaliza a versão ativa (mesma regra de negócio de cadastrar_treinos_finalizar)."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    try:
        versao = VersaoService.finalizar_livre(versao_id, user_id=current_user.id)
        flash(f'Versão {versao.numero_versao} finalizada!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao finalizar versão (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/clonar', methods=['POST'])
@login_required
@limiter.limit("10 per hour", key_func=_chave_por_usuario)
def versao_clonar(versao_id):
    """Cria uma nova versão ativa copiando a estrutura de treinos desta versão."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    try:
        nova_versao = VersaoService.clonar_versao(versao_id, user_id=current_user.id)
        flash(f'Versão clonada como v{nova_versao.numero_versao}!', 'success')
        return redirect(url_for('aluno.ver_versao', versao_id=nova_versao.id))
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao clonar versão")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))


@aluno_bp.route('/versao/<int:versao_id>/excluir', methods=['POST'])
@login_required
@limiter.limit("10 per hour", key_func=_chave_por_usuario)
def versao_excluir(versao_id):
    """Exclui uma versão finalizada sem histórico de registro."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    try:
        VersaoService.excluir_versao(versao_id, user_id=current_user.id)
        flash('Versão excluída com sucesso!', 'success')
        return redirect(url_for('aluno.versoes'))
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao excluir versão")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
