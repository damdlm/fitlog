"""
Rotas de "Minhas Versões" -- histórico de versões do aluno (ativa e
finalizadas), reconstruída após a remoção da tabela `treinos`
compartilhada (ver migration e1f2a3b4c5d6).

Diferente da tela "Cadastrar Treinos" (routes/aluno/cadastro_treinos.py),
que só enxerga a versão ATIVA, aqui o aluno pode ver QUALQUER versão sua,
inclusive as já finalizadas -- mas só pode EDITAR (descrição, treinos,
exercícios) enquanto a versão estiver ativa. Uma vez finalizada, a versão
vira histórico somente-leitura (só restam as ações Clonar/Excluir). As
travas de posse (IDOR) e de integridade de histórico (RegistroTreino)
continuam aplicadas pelo service independente disso.
"""

import logging
from collections import Counter

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from . import aluno_bp
from extensions import limiter
from services.versao_service import VersaoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from services.notificacao_service import NotificacaoService
from models import VersaoGlobal, TreinoVersao

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
    # Contagem por músculo pros chips de filtro, calculada uma vez só em
    # O(n) -- antes o template fazia isso com um loop de músculos DENTRO
    # de um loop de exercícios (~36 mil iterações Jinja a cada
    # carregamento, com 27 músculos x 1351 exercícios no catálogo).
    contagem_musculos = Counter(
        ex.musculo_nome or getattr(ex, 'musculo', None) or 'N/A'
        for ex in exercicios_catalogo
    )

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
        contagem_musculos=contagem_musculos,
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
        reordenar_url=url_for('api.api_reordenar_exercicios'),
    )


@aluno_bp.route('/versao/<int:versao_id>/editar', methods=['POST'])
@login_required
@limiter.limit("30 per hour", key_func=_chave_por_usuario)
def versao_editar_descricao(versao_id):
    """Edita a descrição de uma versão -- só permitido se ainda estiver ativa."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    descricao = request.form.get('descricao', '')
    try:
        VersaoService.editar_descricao_livre(
            versao_id, descricao, user_id=current_user.id, permitir_finalizada=False
        )
        flash('Versão atualizada!', 'success')
        NotificacaoService.notificar_professor(
            current_user,
            tipo='versao_editada',
            titulo='Aluno editou uma versão de treino',
            mensagem=f'{current_user.nome_completo or current_user.username} atualizou a descrição de uma versão de treino.',
            url=url_for('professor.ver_versao_aluno', aluno_id=current_user.id, versao_id=versao_id),
            chave_agrupamento=f'versao_editar:{versao_id}',
        )
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
    """Adiciona um treino a uma versão -- só permitido se ainda estiver ativa."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    # exercicios[]/observacao_<chave>: opcionais -- mesmo esquema de
    # versao_salvar_treino, já que ver_versao.html agora reaproveita o
    # mesmo modal (modalExercicios) tanto pra adicionar quanto editar.
    exercicios_raw = request.form.getlist('exercicios[]')
    observacoes = {
        chave: request.form.get(f'observacao_{chave}', '').strip()[:60]
        for chave in exercicios_raw if chave and chave.strip()
    }
    try:
        VersaoService.adicionar_treino_livre(
            versao_id, nome_treino, descricao_treino,
            user_id=current_user.id, permitir_finalizada=False,
            exercicios_raw=exercicios_raw, observacoes=observacoes
        )
        if exercicios_raw:
            flash('Treino adicionado com sucesso!', 'success')
        else:
            flash('Treino adicionado! Agora selecione os exercícios.', 'success')
        NotificacaoService.notificar_professor(
            current_user,
            tipo='treino_adicionado',
            titulo='Aluno adicionou um treino',
            mensagem=f'{current_user.nome_completo or current_user.username} adicionou o treino "{nome_treino.strip()}".',
            url=url_for('professor.ver_versao_aluno', aluno_id=current_user.id, versao_id=versao_id),
            chave_agrupamento=f'versao_add_treino:{versao_id}',
        )
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
    """Salva nome/descrição/exercícios de um treino -- só permitido se a versão ainda estiver ativa."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    exercicios_raw = request.form.getlist('exercicios[]')
    observacoes = {
        chave: request.form.get(f'observacao_{chave}', '').strip()[:60]
        for chave in exercicios_raw if chave and chave.strip()
    }

    # Nomes ANTES de salvar -- usados só pra montar um diff legível na
    # notificação pro professor (ver NotificacaoService.montar_diff_exercicios).
    # Best effort: se falhar por qualquer motivo, segue sem o diff.
    nomes_antes = []
    try:
        treino_atual = TreinoVersao.query.get(treino_versao_id)
        if treino_atual:
            nomes_antes = [
                (ve.exercicio.nome if ve.exercicio else '?') for ve in treino_atual.exercicios
            ]
    except Exception:
        logger.exception("Falha ao capturar exercícios antes de salvar (diff de notificação)")

    try:
        VersaoService.salvar_treino_livre(
            versao_id, treino_versao_id, nome_treino, descricao_treino,
            exercicios_raw, user_id=current_user.id, observacoes=observacoes,
            permitir_finalizada=False
        )
        flash('Treino salvo com sucesso!', 'success')

        diff = None
        try:
            catalogo = ExercicioService.get_exercicios_completos(user_id=current_user.id)
            nomes_catalogo = {f'{ex.prefixo}{ex.id}': ex.nome for ex in catalogo}
            nomes_depois = [nomes_catalogo.get(ch, ch) for ch in exercicios_raw]
            diff = NotificacaoService.montar_diff_exercicios(nomes_antes, nomes_depois)
        except Exception:
            logger.exception("Falha ao montar diff de exercícios para notificação")

        mensagem = f'{current_user.nome_completo or current_user.username} atualizou o treino "{nome_treino.strip()}"'
        mensagem += f' -- {diff}.' if diff else '.'

        NotificacaoService.notificar_professor(
            current_user,
            tipo='treino_editado',
            titulo='Aluno editou um treino',
            mensagem=mensagem,
            url=url_for('professor.ver_versao_aluno', aluno_id=current_user.id, versao_id=versao_id) + f'#treino-{treino_versao_id}',
            chave_agrupamento=f'treino_editar:{treino_versao_id}',
        )
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
    """Remove um treino de uma versão -- só permitido se ainda estiver ativa
    (e bloqueado pelo service se já houver histórico de registro para esse treino)."""
    if not current_user.pode_gerenciar_treino_proprio():
        return _acesso_negado()

    try:
        VersaoService.remover_treino_livre(
            versao_id, treino_versao_id, user_id=current_user.id, permitir_finalizada=False
        )
        flash('Treino removido da versão.', 'success')
        NotificacaoService.notificar_professor(
            current_user,
            tipo='treino_excluido',
            titulo='Aluno excluiu um treino',
            mensagem=f'{current_user.nome_completo or current_user.username} removeu um treino de uma versão.',
            url=url_for('professor.ver_versao_aluno', aluno_id=current_user.id, versao_id=versao_id),
            chave_agrupamento=f'treino_remover:{treino_versao_id}',
        )
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
        NotificacaoService.notificar_professor(
            current_user,
            tipo='versao_finalizada',
            titulo='Aluno finalizou uma versão',
            mensagem=f'{current_user.nome_completo or current_user.username} finalizou a versão {versao.numero_versao}.',
            url=url_for('professor.ver_versao_aluno', aluno_id=current_user.id, versao_id=versao_id),
            chave_agrupamento=f'versao_finalizar:{versao_id}',
        )
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
        versao_obj = VersaoGlobal.query.filter_by(id=versao_id, user_id=current_user.id).first()
        numero_versao = versao_obj.numero_versao if versao_obj else None
        VersaoService.excluir_versao(versao_id, user_id=current_user.id)
        flash('Versão excluída com sucesso!', 'success')
        NotificacaoService.notificar_professor(
            current_user,
            tipo='versao_excluida',
            titulo='Aluno excluiu uma versão',
            mensagem=(
                f'{current_user.nome_completo or current_user.username} excluiu a versão '
                f'{numero_versao}.' if numero_versao else
                f'{current_user.nome_completo or current_user.username} excluiu uma versão de treino.'
            ),
            url=url_for('professor.versoes_aluno', aluno_id=current_user.id),
        )
        return redirect(url_for('aluno.versoes'))
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao excluir versão")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))