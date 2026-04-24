from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, TreinoVersao, VersaoExercicio, ExercicioCustomizado, ExercicioBase, Musculo
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
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versoes = VersaoService.get_all(user_id=current_user.id)
    return render_template('aluno/versoes.html', versoes=versoes)

@aluno_bp.route('/versao/nova', methods=['GET', 'POST'])
@login_required
def nova_versao():
    if not current_user.is_aluno():
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
    if not current_user.is_aluno():
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

@aluno_bp.route('/versao/<int:versao_id>/finalizar')
@login_required
def finalizar_versao(versao_id):
    if not current_user.is_aluno():
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

@aluno_bp.route('/versao/<int:versao_id>/clonar')
@login_required
def clonar_versao(versao_id):
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    if VersaoService.clone(versao_id, user_id=current_user.id):
        flash('Versão clonada com sucesso!', 'success')
    else:
        flash('Erro ao clonar versão!', 'danger')
    return redirect(url_for('aluno.versoes'))

@aluno_bp.route('/versao/<int:versao_id>/excluir')
@login_required
def excluir_versao(versao_id):
    if not current_user.is_aluno():
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
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    if request.method == 'POST':
        treino_id = request.form.get('treino_id')
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
        if not treino:
            flash('Treino não encontrado!', 'danger')
            return redirect(url_for('aluno.novo_treino_versao', versao_id=versao_id))
        existe = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        if existe:
            flash(f'Treino {treino.codigo} já existe nesta versão!', 'warning')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        exercicios = ExercicioService.get_by_treino(treino.id, user_id=current_user.id)
        exercicios_ids = [ex.id for ex in exercicios]
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
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, exercicios_ids, [])
            db.session.commit()
            flash(f'Treino {treino.codigo} adicionado!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar treino à versão: {e}")
            flash('Erro ao adicionar treino.', 'danger')
    treinos_disponiveis = TreinoService.get_all(user_id=current_user.id)
    treinos_na_versao = [tv.treino_id for tv in versao.treinos]
    treinos_livres = [t for t in treinos_disponiveis if t.id not in treinos_na_versao]
    return render_template('aluno/novo_treino_versao.html', versao=versao, treinos=treinos_livres)

@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao(versao_id, treino_codigo):
    """Edita um treino específico dentro de uma versão do aluno"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    from models import VersaoExercicio, ExercicioCustomizado, ExercicioBase
    import traceback

    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)

    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))

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
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        
        exercicios_raw = request.form.getlist('exercicios[]')
        
        # Separar IDs por tipo
        usuarios_ids = []
        bases_ids = []
        
        for item in exercicios_raw:
            if item and item.strip():
                if item.startswith('u_'):
                    try:
                        usuarios_ids.append(int(item[2:]))
                    except ValueError:
                        pass
                elif item.startswith('b_'):
                    try:
                        bases_ids.append(int(item[2:]))
                    except ValueError:
                        pass
        
        usuarios_ids = list(set(usuarios_ids))
        bases_ids = list(set(bases_ids))
        
        if not usuarios_ids and not bases_ids:
            flash('Selecione pelo menos um exercício!', 'danger')
            return redirect(request.url)
        
        # Validar IDs de usuário
        usuarios_ids_validos = []
        for ex_id in usuarios_ids:
            exercicio = ExercicioCustomizado.query.filter_by(
                id=ex_id,
                usuario_id=current_user.id
            ).first()
            if exercicio:
                usuarios_ids_validos.append(ex_id)
        
        # Validar IDs de base
        bases_ids_validos = []
        for ex_id in bases_ids:
            exercicio = ExercicioBase.query.get(ex_id)
            if exercicio:
                bases_ids_validos.append(ex_id)
        
        # Atualizar treino
        treino_versao.nome_treino = nome_treino
        treino_versao.descricao_treino = descricao_treino
        
        # Remover antigos
        VersaoExercicio.query.filter_by(treino_versao_id=treino_versao.id).delete()
        
        ordem = 0
        
        # Adicionar exercícios do usuário
        for ex_id in usuarios_ids_validos:
            ve = VersaoExercicio(
                treino_versao_id=treino_versao.id,
                exercicio_usuario_id=ex_id,
                ordem=ordem
            )
            db.session.add(ve)
            ordem += 1
        
        # Adicionar exercícios da base
        for ex_id in bases_ids_validos:
            ve = VersaoExercicio(
                treino_versao_id=treino_versao.id,
                exercicio_base_id=ex_id,
                ordem=ordem
            )
            db.session.add(ve)
            ordem += 1
        
        try:
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {str(e)}', 'danger')
            return redirect(request.url)
    
    # ==========================================================
    # MÉTODO GET - CARREGAR FORMULÁRIO
    # ==========================================================
    
    # Buscar exercícios do usuário
    exercicios_usuario = ExercicioCustomizado.query\
        .filter_by(usuario_id=current_user.id)\
        .order_by(ExercicioCustomizado.nome)\
        .all()
    
    # Buscar exercícios da base
    exercicios_base = ExercicioBase.query\
        .order_by(ExercicioBase.nome)\
        .all()
    
    # Montar lista para template (COM PREFIXO)
    exercicios_display = []
    
    for ex in exercicios_usuario:
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A',
            'tipo': 'usuario',
            'prefixo': 'u_'
        })
    
    for ex in exercicios_base:
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A',
            'tipo': 'base',
            'prefixo': 'b_'
        })
    
    exercicios_display.sort(key=lambda x: x['nome'])
    
    # Buscar exercícios já salvos na versão (COM PREFIXO)
    exercicios_atuais = []
    for ve in treino_versao.exercicios:
        if ve.exercicio_usuario_id:
            exercicios_atuais.append(f"u_{ve.exercicio_usuario_id}")
        elif ve.exercicio_base_id:
            exercicios_atuais.append(f"b_{ve.exercicio_base_id}")
    
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
                         musculos=musculos)

@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir')
@login_required
def excluir_treino_versao(versao_id, treino_codigo):
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    try:
        VersaoService.excluir_treino_versao(versao_id, treino_codigo, current_user.id, current_user)
        flash(f'Treino {treino_codigo} removido da versão!', 'success')
    except Exception as e:
        flash(str(e), 'danger')
    return redirect(url_for('aluno.ver_versao', versao_id=versao_id))