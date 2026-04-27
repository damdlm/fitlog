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
        # Monta lista de dicts com tipo para evitar ambiguidade de ID entre tabelas
        exercicios_com_tipo = [
            {'id': ex.id, 'tipo': getattr(ex, 'tipo', 'usuario')}
            for ex in exercicios
        ]
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
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, exercicios_com_tipo)
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

# ==========================================================
# ROTA EDITAR TREINO VERSÃO (CORRIGIDA COM PREFIXO)
# ==========================================================
@aluno_bp.route('/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao(versao_id, treino_codigo):
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    # ========== MÉTODO POST ==========
    if request.method == 'POST':
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        
        # Coletar valores com prefixo e montar lista de dicts com tipo
        valores = request.form.getlist('exercicios[]')
        exercicios_com_tipo = []
        for val in valores:
            if val.startswith('u_'):
                exercicios_com_tipo.append({'id': int(val[2:]), 'tipo': 'usuario'})
            elif val.startswith('b_'):
                exercicios_com_tipo.append({'id': int(val[2:]), 'tipo': 'base'})
        
        if not exercicios_com_tipo:
            flash('Selecione pelo menos um exercício para o treino!', 'danger')
            return redirect(request.url)
        
        # Validar que os IDs existem
        from models import ExercicioUsuario, ExercicioBase
        exercicios_validos = []
        for item in exercicios_com_tipo:
            ex_id, tipo = item['id'], item['tipo']
            if tipo == 'usuario' and ExercicioUsuario.query.get(ex_id):
                exercicios_validos.append(item)
            elif tipo == 'base' and ExercicioBase.query.get(ex_id):
                exercicios_validos.append(item)
            else:
                logger.warning(f"Exercício {tipo} ID {ex_id} não encontrado")
        
        if not exercicios_validos:
            flash('Nenhum exercício válido foi selecionado.', 'danger')
            return redirect(request.url)
        
        try:
            versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
            if not versao:
                flash('Versão não encontrada!', 'danger')
                return redirect(request.url)
            
            treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)
            if not treino_ref:
                flash('Treino não encontrado!', 'danger')
                return redirect(request.url)
            
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino_ref.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                flash('Treino não encontrado nesta versão!', 'danger')
                return redirect(request.url)
            
            treino_versao.nome_treino = nome_treino
            treino_versao.descricao_treino = descricao_treino
            
            # Usar método unificado com lista de dicts {'id', 'tipo'}
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id,
                exercicios_validos
            )
            
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado com sucesso!', 'success')
            return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao editar treino: {e}")
            flash(f'Erro ao atualizar treino: {str(e)}', 'danger')
            return redirect(request.url)
    
    # ========== MÉTODO GET ==========
    versao = VersaoService.get_by_id(versao_id, user_id=current_user.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('aluno.versoes'))
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=current_user.id)
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for('aluno.ver_versao', versao_id=versao_id))
    
    # Buscar todos os exercícios (base + customizados) com o tipo
    todos_exercicios = ExercicioService.get_exercicios_completos(user_id=current_user.id)
    exercicios_atuais = [ve.exercicio_id for ve in treino_versao.exercicios]
    
    exercicios_display = []
    for ex in todos_exercicios:
        musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': musculo_nome,
            'tipo': getattr(ex, 'tipo', 'base'),
            'checked': ex.id in exercicios_atuais
        })
    
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