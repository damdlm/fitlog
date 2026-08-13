from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from . import aluno_bp
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.registro_service import RegistroService
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/treinos')
@login_required
def treinos():
    """
    Tela 'Meus Treinos': ver e editar sessões já registradas por data.

    Antes também listava os treinos avulsos (A/B/C) do usuário, com um
    botão 'Novo Treino' -- removido a pedido: os treinos passaram a ser
    geridos só dentro de cada versão (ver aluno.novo_treino_versao), e a
    lista avulsa não é mais usada. Sem ela, não há mais motivo para
    buscar TreinoService.get_all()/VersaoService.get_exercicios_agrupados_
    por_treino() nesta rota -- trabalho a menos em toda visita à página.
    """
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    return render_template('aluno/treinos.html')

@aluno_bp.route('/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino():
    """Cria um novo treino para o aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        if not codigo or not codigo.isalpha() or len(codigo) != 1:
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(url_for('aluno.novo_treino'))
        
        existente = TreinoService.get_by_codigo(codigo, user_id=current_user.id)
        if existente:
            flash(f'Treino {codigo} já existe!', 'danger')
            return redirect(url_for('aluno.novo_treino'))
        
        treino = TreinoService.create(codigo, nome, descricao, user_id=current_user.id)
        if treino:
            flash(f'Treino {codigo} criado com sucesso!', 'success')
            return redirect(url_for('aluno.treinos'))
        else:
            flash('Erro ao criar treino!', 'danger')
    
    return render_template('aluno/novo_treino.html')

@aluno_bp.route('/treino/<int:treino_id>', methods=['GET', 'POST'])
@login_required
def editar_treino(treino_id):
    """Edita um treino do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('aluno.treinos'))
    
    if request.method == 'POST':
        novo_codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        treino_atualizado = TreinoService.update(
            treino_id,
            codigo=novo_codigo,
            nome=nome,
            descricao=descricao,
            user_id=current_user.id
        )
        if treino_atualizado:
            flash('Treino atualizado!', 'success')
            return redirect(url_for('aluno.treinos'))
        else:
            flash('Erro ao atualizar treino!', 'danger')
    
    return render_template('aluno/editar_treino.html', treino=treino)

@aluno_bp.route('/treino/<int:treino_id>/excluir')
@login_required
def excluir_treino(treino_id):
    """Exclui um treino do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=current_user.id)
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('aluno.treinos'))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão do treino {treino.codigo}.', 'warning')
        return redirect(url_for('aluno.treinos'))
    
    if TreinoService.delete(treino_id, user_id=current_user.id):
        flash(f'Treino {treino.codigo} excluído!', 'success')
    else:
        flash('Erro ao excluir treino!', 'danger')
    
    return redirect(url_for('aluno.treinos'))


def _serializar_exercicios_do_dia(registros):
    """Monta a lista de exercícios (nome/músculo/carga/reps/séries) a
    partir dos registros de uma sessão, no mesmo formato de chave
    ("u_<id>"/"b_<id>") usado em registrar-treino — evita colisão entre
    um exercício personalizado e um do catálogo do sistema que
    coincidam em número de ID."""
    exercicios = []
    tempo_treino = None
    for r in registros:
        ex_obj = r.exercicio or r.exercicio_base
        if not ex_obj:
            continue

        prefixo = 'u' if r.exercicio_usuario_id is not None else 'b'
        ex_id = r.exercicio_usuario_id or r.exercicio_base_id
        series = sorted(r.series, key=lambda s: s.ordem)

        if series and tempo_treino is None:
            tempo_treino = series[0].tempo_treino

        musculo_nome = ''
        if getattr(ex_obj, 'musculo_ref', None):
            musculo_nome = ex_obj.musculo_ref.nome
        elif getattr(ex_obj, 'grupo_muscular', None):
            musculo_nome = ex_obj.grupo_muscular

        exercicios.append({
            'chave': f'{prefixo}_{ex_id}',
            'nome': ex_obj.nome,
            'musculo': musculo_nome,
            'carga': float(series[0].carga) if series else 0,
            'repeticoes': series[0].repeticoes if series else 0,
            'num_series': len(series),
        })
    return exercicios, tempo_treino


@aluno_bp.route('/treino-registro/por-data')
@login_required
def treino_registro_por_data():
    """Retorna (JSON) o treino registrado numa data, com os exercícios
    e valores já lançados — usado para popular o filtro por data e o
    modal de edição em 'Meus Treinos'."""
    data_str = request.args.get('data')
    if not data_str:
        return jsonify({'ok': False, 'erro': 'Data não informada.'}), 400

    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'erro': 'Data inválida.'}), 400

    primeiro = RegistroService.get_treino_por_data(data_obj, user_id=current_user.id)
    if not primeiro:
        return jsonify({'ok': False, 'erro': 'Nenhum treino registrado nesta data.'}), 404

    registros = RegistroService.get_by_data(
        treino_id=primeiro.treino_id,
        versao_id=primeiro.versao_id,
        data=data_obj,
        user_id=current_user.id
    )
    treino = TreinoService.get_by_id(primeiro.treino_id, user_id=current_user.id)
    exercicios, tempo_treino = _serializar_exercicios_do_dia(registros)

    return jsonify({
        'ok': True,
        'data': data_str,
        'treino': {'id': treino.id, 'codigo': treino.codigo, 'nome': treino.nome} if treino else None,
        'tempo_treino': tempo_treino,
        'exercicios': exercicios,
    })


@aluno_bp.route('/treino-registro/editar', methods=['POST'])
@login_required
def treino_registro_editar():
    """Salva as edições feitas no modal de exercícios de uma sessão já
    registrada. versao_id/periodo/semana nunca vêm do cliente -- são
    sempre relidos de um registro existente do próprio usuário, para
    não confiar em nada que o front-end mande sobre a sessão em si."""
    payload = request.get_json(silent=True) or {}
    data_str = payload.get('data')
    treino_id = payload.get('treino_id')
    exercicios_payload = payload.get('exercicios') or []

    if not data_str or not treino_id:
        return jsonify({'ok': False, 'erro': 'Dados incompletos.'}), 400

    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'erro': 'Data inválida.'}), 400

    original = RegistroService.get_treino_por_data(data_obj, user_id=current_user.id)
    if not original or str(original.treino_id) != str(treino_id):
        return jsonify({'ok': False, 'erro': 'Treino não encontrado para esta data.'}), 404

    dados_exercicios = {}
    for ex in exercicios_payload:
        chave = str(ex.get('chave', ''))
        try:
            carga = float(ex.get('carga'))
            reps = int(ex.get('repeticoes'))
            num_series = int(ex.get('num_series', 1))
        except (TypeError, ValueError):
            continue

        if not (carga >= 0 and reps >= 0 and 1 <= num_series <= 10):
            continue

        if chave.startswith('u_'):
            tipo, ex_id_str = 'usuario', chave[2:]
        elif chave.startswith('b_'):
            tipo, ex_id_str = 'sistema', chave[2:]
        else:
            continue

        try:
            ex_id = int(ex_id_str)
        except ValueError:
            continue

        dados_exercicios[chave] = {
            'carga': carga,
            'repeticoes': reps,
            'num_series': num_series,
            'tipo': tipo,
            'exercicio_id': ex_id,
            'data_registro': original.data_registro
        }

    if not dados_exercicios:
        return jsonify({'ok': False, 'erro': 'Nenhum exercício válido para salvar.'}), 400

    tempo_treino_atual = original.series[0].tempo_treino if original.series else None

    sucesso = RegistroService.salvar_registros(
        treino_id=original.treino_id,
        versao_id=original.versao_id,
        periodo=original.periodo,
        semana=original.semana,
        dados_exercicios=dados_exercicios,
        user_id=current_user.id,
        tempo_treino=tempo_treino_atual
    )

    if sucesso:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'erro': 'Erro ao salvar alterações.'}), 500


@aluno_bp.route('/treino-registro/excluir', methods=['POST'])
@login_required
def treino_registro_excluir():
    """Exclui a sessão inteira (todos os exercícios registrados) de um
    treino numa data específica."""
    payload = request.get_json(silent=True) or {}
    data_str = payload.get('data')
    treino_id = payload.get('treino_id')

    if not data_str or not treino_id:
        return jsonify({'ok': False, 'erro': 'Dados incompletos.'}), 400

    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'erro': 'Data inválida.'}), 400

    original = RegistroService.get_treino_por_data(data_obj, user_id=current_user.id)
    if not original or str(original.treino_id) != str(treino_id):
        return jsonify({'ok': False, 'erro': 'Treino não encontrado para esta data.'}), 404

    sucesso = RegistroService.excluir_por_treino_data(
        treino_id=original.treino_id,
        versao_id=original.versao_id,
        data=data_obj,
        user_id=current_user.id
    )

    if sucesso:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'erro': 'Erro ao excluir o treino.'}), 500