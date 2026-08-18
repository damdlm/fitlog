from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, TreinoVersao, VersaoExercicio, ExercicioCustomizado, ExercicioSistema, Musculo
from services.versao_service import VersaoService
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/versoes')
@login_required
def versoes():
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versoes = VersaoService.get_all(user_id=current_user.id)
    return render_template('aluno/versoes.html', versoes=versoes)

@aluno_bp.route('/versao/nova', methods=['GET', 'POST'])
@login_required
def nova_versao():
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        divisao = request.form.get('divisao', 'ABC')
        data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        versao_atual = VersaoService.get_ativa(user_id=current_user.id)
        if versao_atual and not data_fim:
            versao_atual.data_fim = data_inicio
            db.session.add(versao_atual)
        nova_versao = VersaoService.create(
            descricao=descricao,
            data_inicio=data_inicio,
            divisao=divisao,
            data_fim=data_fim,
            user_id=current_user.id
        )
        if nova_versao:
            flash('Versão criada com sucesso!', 'success')
            return redirect(url_for('aluno.versoes'))
        else:
            flash('Erro ao criar versão!', 'danger')
    return render_template('aluno/nova_versao.html')

@aluno_bp.route('/versao/<int:versao_id>', methods=['GET', 'POST'])
@login_required
def ver_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    if request.method == 'POST':
        versao.descricao = request.form.get('descricao')
        nova_divisao = request.form.get('divisao')
        if nova_divisao in ['ABC', 'ABCD', 'ABCDE']:
            versao.divisao = nova_divisao
        versao.data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        versao.data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        db.session.commit()
        flash('Versão atualizada!', 'success')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    treinos_dict = VersaoService.get_treinos(versao.id, user_id=current_user.id)
    exercicios = ExercicioService.get_exercicios_completos(user_id=current_user.id)
    treinos_disponiveis = TreinoService.get_all(user_id=current_user.id)
    return render_template('aluno/ver_versao.html',
                         versao=versao,
                         treinos=treinos_dict,
                         exercicios=exercicios,
                         treinos_disponiveis=treinos_disponiveis)

@aluno_bp.route('/versao/<int:versao_id>/finalizar', methods=['POST'])
@login_required
def finalizar_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    if versao.data_fim:
        flash('Versão já finalizada!', 'warning')
        return redirect(url_for('aluno.versoes'))
    data_atual = datetime.now().date()
    if VersaoService.finalizar(versao_id, data_atual, user_id=current_user.id):
        flash('Versão finalizada!', 'success')
    else:
        flash('Erro ao finalizar versão!', 'danger')
    return redirect(url_for('aluno.versoes'))

@aluno_bp.route('/versao/<int:versao_id>/clonar', methods=['POST'])
@login_required
def clonar_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    if VersaoService.clone(versao_id, user_id=current_user.id):
        flash('Versão clonada com sucesso!', 'success')
    else:
        flash('Erro ao clonar versão!', 'danger')
    return redirect(url_for('aluno.versoes'))

@aluno_bp.route('/versao/<int:versao_id>/excluir', methods=['POST'])
@login_required
def excluir_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    versao_ativa = VersaoService.get_ativa(user_id=current_user.id)
    if versao_ativa and versao_ativa.id == versao_id:
        flash('Não é possível excluir a versão ativa. Finalize-a primeiro.', 'warning')
        return redirect(url_for('aluno.versoes'))
    from models import RegistroTreino
    registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=current_user.id).first()
    if registros:
        flash('Não é possível excluir esta versão pois existem registros vinculados.', 'danger')
        return redirect(url_for('aluno.versoes'))
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash('⚠️ Clique novamente para confirmar a exclusão.', 'warning')
        return redirect(url_for('aluno.versoes'))
    if VersaoService.delete(versao_id, user_id=current_user.id):
        flash('Versão excluída com sucesso!', 'success')
    else:
        flash('Erro ao excluir versão!', 'danger')
    return redirect(url_for('aluno.versoes'))

@aluno_bp.route('/versao/<int:versao_id>/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino_versao(versao_id):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    if versao.data_fim is not None:
        flash('Esta versão está arquivada e não pode ser alterada.', 'warning')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    if request.method == 'POST':
        treino_codigo = request.form.get('treino_id', '').strip().upper()
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        if not treino_codigo or not treino_codigo.isalpha() or len(treino_codigo) != 1:
            flash('Selecione uma letra válida para o treino.', 'danger')
            return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_id))
        treino = TreinoService.get_or_create(treino_codigo, nome_treino, descricao_treino, user_id=current_user.id)
        if not treino:
            flash('Erro ao criar treino!', 'danger')
            return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_id))
        existe = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        if existe:
            flash(f'Treino {treino.codigo} já existe nesta versão!', 'warning')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        exercicios = ExercicioService.get_by_treino(treino.id, user_id=current_user.id)
        exercicios_ids = [ex.id for ex in exercicios]
        observacoes = {
            f"{ex.prefixo}{ex.id}": ex.observacao_treino
            for ex in exercicios if getattr(ex, 'observacao_treino', None)
        }
        try:
            treino_versao = TreinoVersao(
                versao_id=versao_id,
                treino_id=treino.id,
                nome_treino=nome_treino,
                descricao_treino=descricao_treino,
                ordem=len(versao.treinos)
            )
            db.session.add(treino_versao)
            db.session.flush()
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, exercicios_ids, [], observacoes=observacoes)
            db.session.commit()
            flash(f'Treino {treino.codigo} adicionado!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        except Exception:
            db.session.rollback()
            logger.exception("Erro ao adicionar treino à versão")
            flash('Erro ao adicionar treino.', 'danger')
    letras_em_uso = {tv.treino_ref.codigo for tv in versao.treinos}
    letras_disponiveis = [l for l in versao.divisao if l not in letras_em_uso]
    return render_template('aluno/novo_treino_versao.html', versao=versao, letras=letras_disponiveis)

@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao(versao_id, treino_codigo):
    """Edita um treino específico dentro de uma versão do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    from models import VersaoExercicio, ExercicioCustomizado, ExercicioSistema
    import traceback

    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)

    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))

    if versao.data_fim is not None:
        flash('Esta versão está arquivada e não pode ser editada.', 'warning')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))

    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)

    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))

    # Encontrar o treino na versão
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break

    if not treino_versao:
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))

    # ==========================================================
    # MÉTODO POST - SALVAR
    # ==========================================================
    if request.method == 'POST':
        nome_treino = request.form.get('nome_treino', '').strip()
        descricao_treino = request.form.get('descricao_treino', '').strip()

        exercicios_raw = request.form.getlist('exercicios[]')

        # Método compartilhado com a rota do professor (routes/professor_routes.py)
        # -- mesma validação/parsing, evita duas implementações divergentes.
        usuarios_ids_validos, bases_ids_validos = VersaoService.processar_exercicios_formulario(
            exercicios_raw, current_user.id
        )

        if not usuarios_ids_validos and not bases_ids_validos:
            flash('Selecione pelo menos um exercício!', 'danger')
            return redirect(request.url)

        # Observação por exercício (campo observacao_<chave>, até 60 chars)
        observacoes = {
            chave: request.form.get(f'observacao_{chave}', '').strip()[:60]
            for chave in exercicios_raw if chave and chave.strip()
        }

        treino_versao.nome_treino = nome_treino
        treino_versao.descricao_treino = descricao_treino

        try:
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id, usuarios_ids_validos, bases_ids_validos, observacoes=observacoes
            )
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            logger.exception("Erro ao salvar treino da versão (aluno)")
            flash(f'Erro: {str(e)}', 'danger')
            return redirect(request.url)

    # ==========================================================
    # MÉTODO GET - CARREGAR FORMULÁRIO
    # ==========================================================
    # Mesmo serviço usado pela visão do professor (routes/professor_routes.py) --
    # já traz imagem/descrição de cada exercício, o que a montagem manual
    # anterior aqui não trazia.
    exercicios_display, exercicios_atuais, observacoes_atuais = VersaoService.get_exercicios_para_edicao(
        current_user.id, treino_versao
    )

    musculos = MusculoService.get_all_nomes()

    return render_template('aluno/editar_treino_versao.html',
                         versao=versao,
                         treino_id=treino_codigo,
                         treino={
                             "nome": treino_versao.nome_treino,
                             "descricao": treino_versao.descricao_treino,
                             "exercicios": exercicios_atuais
                         },
                         exercicios=exercicios_display,
                         observacoes_atuais=observacoes_atuais,
                         musculos=musculos)

@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir', methods=['POST'])
@login_required
def excluir_treino_versao(versao_id, treino_codigo):
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    try:
        VersaoService.excluir_treino_versao(versao_id, treino_codigo, current_user.id, current_user)
        flash(f'Treino {treino_codigo} removido da versão!', 'success')
    except (ValueError, PermissionError) as e:
        # Mensagens de validação de negócio (texto seguro e fixo,
        # definidas no service) -- ok mostrar direto ao usuário.
        flash(str(e), 'danger')
    except Exception:
        # CORREÇÃO seção 13 (hardening de segurança): qualquer outra
        # exceção (não prevista) fica só no log -- nunca no flash.
        logger.exception("Erro ao excluir treino da versão (aluno)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))