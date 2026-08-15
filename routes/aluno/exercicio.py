from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, ExercicioCustomizado, ExercicioSistema, RegistroTreino, HistoricoTreino
from services.exercicio_service import ExercicioService
from services.musculo_service import MusculoService
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

@aluno_bp.route('/exercicios')
@login_required
def exercicios():
    """Lista os exercícios do aluno"""
    try:
        exercicios = ExercicioCustomizado.query \
            .filter_by(usuario_id=current_user.id) \
            .options(joinedload(ExercicioCustomizado.musculo_ref)) \
            .order_by(ExercicioCustomizado.nome) \
            .all()

        # Esta página só lista ExercicioCustomizado, então "ultimas_cargas"
        # precisa ser calculado só a partir de registros contra exercícios
        # do próprio usuário -- usar RegistroTreino.exercicio_id (hybrid
        # property = COALESCE(exercicio_usuario_id, exercicio_base_id))
        # aqui é um bug real: como ExercicioCustomizado e ExercicioSistema
        # têm sequências de ID independentes, um exercício de sistema pode
        # colidir numericamente com um exercício customizado do usuário, e
        # a carga de um "vaza" pro outro no dict (confirmado com teste).
        # Usar direto a coluna exercicio_usuario_id evita a ambiguidade.
        subq = db.session.query(
            RegistroTreino.exercicio_usuario_id,
            func.max(RegistroTreino.data_registro).label('max_data')
        ).filter(
            RegistroTreino.user_id == current_user.id,
            RegistroTreino.exercicio_usuario_id.isnot(None)
        ).group_by(RegistroTreino.exercicio_usuario_id).subquery()

        cargas_query = db.session.query(
            RegistroTreino.exercicio_usuario_id,
            HistoricoTreino.carga
        ).join(
            subq,
            (RegistroTreino.exercicio_usuario_id == subq.c.exercicio_usuario_id) &
            (RegistroTreino.data_registro == subq.c.max_data)
        ).join(
            HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id
        ).filter(HistoricoTreino.ordem == 1).all()

        ultimas_cargas = {ex_id: float(carga) for ex_id, carga in cargas_query}

        # Resumo exibido no cabeçalho da tela (cards de destaque). Contagem
        # simples em Python sobre a lista já carregada -- sem query extra,
        # já que `exercicios` já veio com musculo_ref via joinedload acima.
        musculo_contagem = {}
        for ex in exercicios:
            nome_musculo = ex.musculo_ref.nome_exibicao if ex.musculo_ref else None
            if nome_musculo:
                musculo_contagem[nome_musculo] = musculo_contagem.get(nome_musculo, 0) + 1
        musculo_destaque = max(musculo_contagem, key=musculo_contagem.get) if musculo_contagem else None

        return render_template('aluno/exercicios.html',
                             exercicios=exercicios,
                             ultimas_cargas=ultimas_cargas,
                             musculo_destaque=musculo_destaque,
                             total_registros=sum(len(ex.registros) for ex in exercicios))
    except Exception:
        logger.exception("Erro ao carregar exercícios")
        flash(f'Erro ao carregar exercícios.', 'danger')
        return redirect(url_for('aluno.dashboard'))

@aluno_bp.route('/exercicio/novo', methods=['GET', 'POST'])
@login_required
def novo_exercicio():
    """Cria um novo exercício para o aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(url_for('aluno.novo_exercicio'))
        
        exercicio = ExercicioService.criar_exercicio_customizado(
            user_id=current_user.id,
            nome=nome,
            musculo_nome=musculo or 'Outros',
            descricao=descricao
        )
        
        if exercicio:
            flash(f'Exercício {nome} criado com sucesso!', 'success')
            return redirect(url_for('aluno.exercicios'))
        else:
            flash('Erro ao criar exercício!', 'danger')
    
    musculos = MusculoService.get_all_nomes()
    return render_template('aluno/novo_exercicio.html', musculos=musculos)


def _buscar_exercicio_proprio_ou_flash(exercicio_id, acao_verbo):
    """
    Busca um exercício customizado do usuário logado, escopado por
    (id, usuario_id) -- direto na tabela do usuário, sem passar pelo
    ExercicioService.get_by_id() genérico.

    Por quê: get_by_id() checa o catálogo global (exercicios_sistema)
    ANTES dos exercícios do próprio usuário. exercicios_sistema e
    exercicios_usuario têm sequências de ID independentes, e o catálogo
    tem centenas de linhas -- então IDs baixos colidem com frequência.
    Resultado: um exercício que É do usuário podia ser identificado como
    "do catálogo" só por coincidência numérica, bloqueando edição/exclusão
    de exercícios que o usuário legitimamente possui (bug relatado).

    Aqui a posse (usuario_id) decide primeiro: se o ID pertence a um
    exercício do próprio usuário, é nele que a ação deve operar --
    nunca ambíguo nas telas do app, já que os links de editar/excluir
    em "Meus Exercícios" sempre apontam para IDs de exercícios que
    pertencem ao usuário. Só cai no catálogo geral para dar uma mensagem
    de erro mais clara quando o ID realmente não é do usuário.
    """
    exercicio = ExercicioCustomizado.query.filter_by(
        id=exercicio_id, usuario_id=current_user.id
    ).options(joinedload(ExercicioCustomizado.musculo_ref)).first()

    if exercicio:
        return exercicio

    if ExercicioSistema.query.get(exercicio_id) is not None:
        flash(f'Este exercício faz parte do catálogo geral e não pode ser {acao_verbo}. '
              f'Crie um exercício personalizado se quiser algo diferente.', 'warning')
    else:
        flash('Exercício não encontrado!', 'danger')

    return None


@aluno_bp.route('/exercicio/<int:exercicio_id>', methods=['GET', 'POST'])
@login_required
def editar_exercicio(exercicio_id):
    """Edita um exercício do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    exercicio = _buscar_exercicio_proprio_ou_flash(exercicio_id, 'editado')
    if not exercicio:
        return redirect(url_for('aluno.exercicios'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        musculo_obj = MusculoService.get_or_create(musculo)
        exercicio_atualizado = ExercicioService.update_exercicio_customizado(
            exercicio_custom_id=exercicio_id,
            user_id=current_user.id,
            nome=nome,
            descricao=descricao,
            musculo_id=musculo_obj.id if musculo_obj else None
        )
        
        if exercicio_atualizado:
            flash('Exercício atualizado!', 'success')
            return redirect(url_for('aluno.exercicios'))
        else:
            flash('Erro ao atualizar exercício!', 'danger')
    
    musculos = MusculoService.get_all_nomes()
    return render_template('aluno/editar_exercicio.html', exercicio=exercicio, musculos=musculos)

@aluno_bp.route('/exercicio/<int:exercicio_id>/excluir', methods=['POST'])
@login_required
def excluir_exercicio(exercicio_id):
    """Exclui um exercício do aluno"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    exercicio = _buscar_exercicio_proprio_ou_flash(exercicio_id, 'excluído')
    if not exercicio:
        return redirect(url_for('aluno.exercicios'))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão de "{exercicio.nome}".', 'warning')
        return redirect(url_for('aluno.exercicios'))
    
    sucesso = ExercicioService.delete_exercicio_customizado(exercicio_id, user_id=current_user.id)
    
    if sucesso:
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('aluno.exercicios'))
