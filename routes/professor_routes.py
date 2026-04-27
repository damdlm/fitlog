from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, AlunoProfessor, Treino, ExercicioCustomizado, RegistroTreino, SolicitacaoVinculo, TreinoVersao, VersaoExercicio, ExercicioBase, ExercicioUsuario
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
from services.estatistica_service import EstatisticaService
from services.seed_service import SeedService
from services.musculo_service import MusculoService
from datetime import datetime, timezone
import logging
import json

professor_bp = Blueprint('professor', __name__, url_prefix='/professor')
logger = logging.getLogger(__name__)

# =============================================
# DASHBOARD DO PROFESSOR
# =============================================

@professor_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal do professor"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado. Área restrita para professores.', 'danger')
        return redirect(url_for('main.index'))
    
    alunos = current_user.get_alunos() if current_user.is_professor() else User.query.filter_by(tipo_usuario='aluno', ativo=True).all()
    
    total_alunos = len(alunos)
    total_treinos = 0
    total_registros = 0
    
    for aluno in alunos:
        total_treinos += Treino.query.filter_by(user_id=aluno.id).count()
        total_registros += RegistroTreino.query.filter_by(user_id=aluno.id).count()
    
    return render_template('professor/dashboard.html',
                         alunos=alunos,
                         total_alunos=total_alunos,
                         total_treinos=total_treinos,
                         total_registros=total_registros)


# =============================================
# GERENCIAMENTO DE ALUNOS
# =============================================

@professor_bp.route('/alunos')
@login_required
def listar_alunos():
    """Lista todos os alunos do professor"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    busca = request.args.get('busca', '')
    status = request.args.get('status', 'ativos')
    
    query = AlunoProfessor.query.filter_by(professor_id=current_user.id, ativo=True)
    
    alunos = []
    for assoc in query.all():
        aluno = db.session.get(User, assoc.aluno_id)
        if aluno and (status == 'todos' or (status == 'ativos' and aluno.ativo) or (status == 'inativos' and not aluno.ativo)):
            if busca.lower() in (aluno.nome_completo or '').lower() or busca.lower() in aluno.username.lower() or busca.lower() in aluno.email.lower():
                alunos.append(aluno)
    
    return render_template('professor/alunos.html', 
                         alunos=alunos,
                         busca=busca,
                         status=status)


@professor_bp.route('/aluno/novo', methods=['GET', 'POST'])
@login_required
def novo_aluno():
    """Cadastra um novo aluno e já vincula ao professor"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        nome_completo = request.form.get('nome_completo')
        telefone = request.form.get('telefone')
        
        if not username or not email or not password:
            flash('Todos os campos são obrigatórios', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if len(username) < 3:
            flash('Usuário deve ter pelo menos 3 caracteres', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if len(password) < 6:
            flash('Senha deve ter pelo menos 6 caracteres', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        aluno = User(
            username=username,
            email=email,
            tipo_usuario='aluno',
            nome_completo=nome_completo,
            telefone=telefone,
            ativo=True
        )
        aluno.set_password(password)
        
        db.session.add(aluno)
        db.session.flush()
        
        vinculo = AlunoProfessor(
            aluno_id=aluno.id,
            professor_id=current_user.id,
            data_associacao=datetime.now(timezone.utc),
            ativo=True
        )
        db.session.add(vinculo)
        
        SeedService.create_minimal_workouts(aluno.id)
        
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} cadastrou novo aluno {aluno.id}")
        flash(f'Aluno {nome_completo or username} cadastrado com sucesso!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    return render_template('professor/novo_aluno.html')


@professor_bp.route('/aluno/<int:aluno_id>')
@login_required
def visualizar_aluno(aluno_id):
    """Visualiza detalhes de um aluno específico"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    registros = RegistroTreino.query.filter_by(user_id=aluno.id).count()
    
    ultimos_registros = RegistroTreino.query.filter_by(user_id=aluno.id)\
        .order_by(RegistroTreino.data_registro.desc())\
        .limit(10).all()
    
    versao_ativa = VersaoService.get_ativa(user_id=aluno.id)
    
    return render_template('professor/visualizar_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         exercicios=exercicios,
                         registros=registros,
                         ultimos_registros=ultimos_registros,
                         versao_ativa=versao_ativa)


@professor_bp.route('/aluno/desativar/<int:aluno_id>')
@login_required
def desativar_aluno(aluno_id):
    """Desativa um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para desativar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    aluno.ativo = False
    db.session.commit()
    flash(f'Aluno {aluno.nome_completo or aluno.username} desativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/reativar/<int:aluno_id>')
@login_required
def reativar_aluno(aluno_id):
    """Reativa um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para reativar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    aluno.ativo = True
    db.session.commit()
    flash(f'Aluno {aluno.nome_completo or aluno.username} reativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/remover-vinculo/<int:aluno_id>')
@login_required
def remover_vinculo(aluno_id):
    """Remove o vínculo entre professor e aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para remover este vínculo.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    assoc = AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first()
    if assoc:
        assoc.ativo = False
        db.session.commit()
        flash(f'Vínculo com {aluno.nome_completo or aluno.username} removido!', 'success')
    
    return redirect(url_for('professor.listar_alunos'))


# =============================================
# SOLICITAÇÕES
# =============================================

@professor_bp.route('/solicitacoes')
@login_required
def solicitacoes():
    """Lista todas as solicitações de vínculo pendentes"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    solicitacoes = SolicitacaoVinculo.query.filter_by(
        professor_id=current_user.id,
        status='pendente'
    ).order_by(SolicitacaoVinculo.data_solicitacao.desc()).all()
    
    return render_template('professor/solicitacoes.html', solicitacoes=solicitacoes)


@professor_bp.route('/solicitacao/<int:solicitacao_id>/aprovar')
@login_required
def aprovar_solicitacao(solicitacao_id):
    """Aprova uma solicitação de vínculo"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    solicitacao = SolicitacaoVinculo.query.get_or_404(solicitacao_id)
    
    if solicitacao.professor_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para aprovar esta solicitação.', 'danger')
        return redirect(url_for('professor.solicitacoes'))
    
    if solicitacao.status != 'pendente':
        flash('Esta solicitação já foi processada.', 'warning')
        return redirect(url_for('professor.solicitacoes'))
    
    solicitacao.status = 'aprovado'
    solicitacao.data_resposta = datetime.now(timezone.utc)
    
    vinculo_existente = AlunoProfessor.query.filter_by(aluno_id=solicitacao.aluno_id, ativo=True).first()
    if not vinculo_existente:
        vinculo = AlunoProfessor(
            aluno_id=solicitacao.aluno_id,
            professor_id=current_user.id,
            data_associacao=datetime.now(timezone.utc),
            ativo=True
        )
        db.session.add(vinculo)
    
    db.session.commit()
    
    logger.info(f"Solicitação {solicitacao_id} aprovada pelo professor {current_user.id}")
    flash(f'Solicitação de {solicitacao.aluno.nome_completo or solicitacao.aluno.username} aprovada!', 'success')
    return redirect(url_for('professor.solicitacoes'))


@professor_bp.route('/solicitacao/<int:solicitacao_id>/recusar')
@login_required
def recusar_solicitacao(solicitacao_id):
    """Recusa uma solicitação de vínculo"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    solicitacao = SolicitacaoVinculo.query.get_or_404(solicitacao_id)
    
    if solicitacao.professor_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para recusar esta solicitação.', 'danger')
        return redirect(url_for('professor.solicitacoes'))
    
    if solicitacao.status != 'pendente':
        flash('Esta solicitação já foi processada.', 'warning')
        return redirect(url_for('professor.solicitacoes'))
    
    solicitacao.status = 'recusado'
    solicitacao.data_resposta = datetime.now(timezone.utc)
    db.session.commit()
    
    logger.info(f"Solicitação {solicitacao_id} recusada pelo professor {current_user.id}")
    flash('Solicitação recusada.', 'info')
    return redirect(url_for('professor.solicitacoes'))


# =============================================
# GERENCIAMENTO DE VERSÕES DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/versoes')
@login_required
def versoes_aluno(aluno_id):
    """Lista todas as versões do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versoes = VersaoService.get_all(user_id=aluno.id)
    return render_template('professor/versoes_aluno.html', aluno=aluno, versoes=versoes)


@professor_bp.route('/aluno/<int:aluno_id>/versao/nova', methods=['GET', 'POST'])
@login_required
def nova_versao_aluno(aluno_id):
    """Cria uma nova versão para o aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        divisao = request.form.get('divisao', 'ABC')
        data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        
        versao_atual = VersaoService.get_ativa(user_id=aluno.id)
        if versao_atual and not data_fim:
            versao_atual.data_fim = data_inicio
            db.session.add(versao_atual)
        
        nova_versao = VersaoService.create(
            descricao=descricao,
            data_inicio=data_inicio,
            divisao=divisao,
            data_fim=data_fim,
            user_id=aluno.id
        )
        
        if nova_versao:
            logger.info(f"Professor {current_user.id} criou versão {nova_versao.id} para aluno {aluno.id}")
            flash(f'Versão criada para {aluno.nome_completo or aluno.username}!', 'success')
            return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao criar versão!', 'danger')
    
    return render_template('professor/nova_versao_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>', methods=['GET', 'POST'])
@login_required
def ver_versao_aluno(aluno_id, versao_id):
    """Visualiza e edita uma versão específica do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id, load_relations=True)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
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
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao.id))
    
    treinos_dict = VersaoService.get_treinos(versao.id, user_id=aluno.id)
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    
    return render_template('professor/ver_versao_aluno.html',
                         aluno=aluno,
                         versao=versao,
                         treinos=treinos_dict,
                         exercicios=exercicios)


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/finalizar')
@login_required
def finalizar_versao_aluno(aluno_id, versao_id):
    """Finaliza uma versão do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    if versao.data_fim:
        flash('Versão já finalizada!', 'warning')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    data_atual = datetime.now().date()
    
    if VersaoService.finalizar(versao_id, data_atual, user_id=aluno.id):
        logger.info(f"Professor {current_user.id} finalizou versão {versao_id} do aluno {aluno.id}")
        flash('Versão finalizada!', 'success')
    else:
        flash('Erro ao finalizar versão!', 'danger')
    
    return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/clonar')
@login_required
def clonar_versao_aluno(aluno_id, versao_id):
    """Clona uma versão do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if VersaoService.clone(versao_id, user_id=aluno.id):
        logger.info(f"Professor {current_user.id} clonou versão {versao_id} do aluno {aluno.id}")
        flash('Versão clonada com sucesso!', 'success')
    else:
        flash('Erro ao clonar versão!', 'danger')
    
    return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/excluir')
@login_required
def excluir_versao_aluno(aluno_id, versao_id):
    """Exclui uma versão do aluno (se não tiver registros)"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    versao_ativa = VersaoService.get_ativa(user_id=aluno.id)
    if versao_ativa and versao_ativa.id == versao_id:
        flash('Não é possível excluir a versão ativa. Finalize-a primeiro.', 'warning')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=aluno.id).first()
    if registros:
        flash('Não é possível excluir esta versão pois existem registros vinculados.', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash('⚠️ Clique novamente para confirmar a exclusão.', 'warning')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    if VersaoService.delete(versao_id, user_id=aluno.id):
        logger.info(f"Professor {current_user.id} excluiu versão {versao_id} do aluno {aluno.id}")
        flash('Versão excluída com sucesso!', 'success')
    else:
        flash('Erro ao excluir versão!', 'danger')
    
    return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))


# =============================================
# GERENCIAMENTO DE TREINOS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/treinos')
@login_required
def treinos_aluno(aluno_id):
    """Lista todos os treinos do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    
    exercicios_por_treino = {}
    for treino in treinos:
        exercicios_por_treino[treino.id] = ExercicioService.get_by_treino(treino.id, user_id=aluno.id)
    
    return render_template('professor/treinos_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         exercicios_por_treino=exercicios_por_treino)


@professor_bp.route('/aluno/<int:aluno_id>/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino_aluno(aluno_id):
    """Cria um novo treino para o aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        if not codigo or not codigo.isalpha() or len(codigo) != 1:
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(url_for('professor.novo_treino_aluno', aluno_id=aluno.id))
        
        existente = TreinoService.get_by_codigo(codigo, user_id=aluno.id)
        if existente:
            flash(f'Treino {codigo} já existe para este aluno!', 'danger')
            return redirect(url_for('professor.novo_treino_aluno', aluno_id=aluno.id))
        
        treino = TreinoService.create(codigo, nome, descricao, user_id=aluno.id)
        
        if treino:
            logger.info(f"Professor {current_user.id} criou treino {treino.id} para aluno {aluno.id}")
            flash(f'Treino {codigo} criado para {aluno.nome_completo or aluno.username}!', 'success')
            return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao criar treino!', 'danger')
    
    return render_template('professor/novo_treino_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/treino/<int:treino_id>', methods=['GET', 'POST'])
@login_required
def editar_treino_aluno(aluno_id, treino_id):
    """Edita um treino do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
    
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        novo_codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        treino_atualizado = TreinoService.update(
            treino_id,
            codigo=novo_codigo,
            nome=nome,
            descricao=descricao,
            user_id=aluno.id
        )
        
        if treino_atualizado:
            logger.info(f"Treino {treino_id} atualizado com sucesso")
            flash('Treino atualizado!', 'success')
            return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
        else:
            logger.error(f"Falha ao atualizar treino {treino_id}")
            flash('Erro ao atualizar treino!', 'danger')
    
    return render_template('professor/editar_treino_aluno.html', aluno=aluno, treino=treino)


@professor_bp.route('/aluno/editar/<int:aluno_id>', methods=['GET', 'POST'])
@login_required
def editar_aluno(aluno_id):
    """Edita os dados de um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para editar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        nova_senha = request.form.get('nova_senha')
        
        if email != aluno.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('Este e-mail já está em uso por outro usuário.', 'danger')
                return redirect(url_for('professor.editar_aluno', aluno_id=aluno.id))
        
        aluno.nome_completo = nome_completo
        aluno.email = email
        aluno.telefone = telefone
        
        if nova_senha and len(nova_senha) >= 6:
            aluno.set_password(nova_senha)
            flash('Senha alterada com sucesso!', 'success')
        
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} editou aluno {aluno.id}")
        flash(f'Dados de {aluno.nome_completo or aluno.username} atualizados!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    return render_template('professor/editar_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/treino/<int:treino_id>/excluir')
@login_required
def excluir_treino_aluno(aluno_id, treino_id):
    """Exclui um treino do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
    
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão do treino {treino.codigo}.', 'warning')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    if TreinoService.delete(treino_id, user_id=aluno.id):
        logger.info(f"Professor {current_user.id} excluiu treino {treino_id} do aluno {aluno.id}")
        flash(f'Treino {treino.codigo} excluído!', 'success')
    else:
        flash('Erro ao excluir treino!', 'danger')
    
    return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))


# =============================================
# GERENCIAMENTO DE EXERCÍCIOS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/exercicios')
@login_required
def exercicios_aluno(aluno_id):
    """Lista todos os exercícios do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    treinos = TreinoService.get_all(user_id=aluno.id)
    
    from sqlalchemy import func
    subq = db.session.query(
        RegistroTreino.exercicio_id,
        func.max(RegistroTreino.data_registro).label('max_data')
    ).filter_by(user_id=aluno.id).group_by(RegistroTreino.exercicio_id).subquery()
    
    ultimas_cargas_query = db.session.query(
        RegistroTreino.exercicio_id,
        RegistroTreino.series
    ).join(
        subq,
        (RegistroTreino.exercicio_id == subq.c.exercicio_id) &
        (RegistroTreino.data_registro == subq.c.max_data)
    ).all()
    
    ultimas_cargas = {}
    for ex_id, series in ultimas_cargas_query:
        if series and len(series) > 0:
            ultimas_cargas[ex_id] = float(series[0].carga)
    
    return render_template('professor/exercicios_aluno.html',
                         aluno=aluno,
                         exercicios=exercicios,
                         treinos=treinos,
                         ultimas_cargas=ultimas_cargas)


@professor_bp.route('/aluno/<int:aluno_id>/exercicio/novo', methods=['GET', 'POST'])
@login_required
def novo_exercicio_aluno(aluno_id):
    """Cria um novo exercício para o aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        treino_id = request.form.get('treino') or None
        descricao = request.form.get('descricao', '')
        
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(url_for('professor.novo_exercicio_aluno', aluno_id=aluno.id))
        
        exercicio = ExercicioService.criar_exercicio_customizado(
            user_id=aluno.id,
            nome=nome,
            musculo_nome=musculo or 'Outros',
            descricao=descricao,
            treino_id=treino_id
        )
        
        if exercicio:
            logger.info(f"Professor {current_user.id} criou exercício {exercicio.id} para aluno {aluno.id}")
            flash(f'Exercício {nome} criado para {aluno.nome_completo or aluno.username}!', 'success')
            return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao criar exercício!', 'danger')
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    musculos = MusculoService.get_all_nomes()
    
    return render_template('professor/novo_exercicio_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         musculos=musculos)


@professor_bp.route('/aluno/<int:aluno_id>/exercicio/<int:exercicio_id>', methods=['GET', 'POST'])
@login_required
def editar_exercicio_aluno(aluno_id, exercicio_id):
    """Edita um exercício do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=aluno.id, load_relations=True)
    
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        treino_id = request.form.get('treino') or None
        descricao = request.form.get('descricao', '')
        
        if hasattr(exercicio, 'is_custom') and exercicio.is_custom:
            musculo_obj = MusculoService.get_or_create(musculo)
            exercicio_atualizado = ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=exercicio_id,
                user_id=aluno.id,
                nome=nome,
                descricao=descricao,
                musculo_id=musculo_obj.id if musculo_obj else None
            )
        else:
            musculo_obj = MusculoService.get_or_create(musculo)
            exercicio_atualizado = ExercicioService.update_exercicio_usuario(
                exercicio_usuario_id=exercicio_id,
                user_id=aluno.id,
                nome_personalizado=nome,
                descricao_personalizada=descricao,
                musculo_personalizado_id=musculo_obj.id if musculo_obj else None
            )
        
        if exercicio_atualizado:
            logger.info(f"Professor {current_user.id} editou exercício {exercicio_id} do aluno {aluno.id}")
            flash('Exercício atualizado!', 'success')
            return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao atualizar exercício!', 'danger')
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    musculos = MusculoService.get_all_nomes()
    
    return render_template('professor/editar_exercicio_aluno.html',
                         aluno=aluno,
                         exercicio=exercicio,
                         treinos=treinos,
                         musculos=musculos)


@professor_bp.route('/aluno/<int:aluno_id>/exercicio/<int:exercicio_id>/excluir')
@login_required
def excluir_exercicio_aluno(aluno_id, exercicio_id):
    """Exclui um exercício do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=aluno.id)
    
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão de "{exercicio.nome}".', 'warning')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    if hasattr(exercicio, 'is_custom') and exercicio.is_custom:
        sucesso = ExercicioService.delete_exercicio_customizado(exercicio_id, user_id=aluno.id)
    else:
        sucesso = ExercicioService.delete_exercicio_usuario(exercicio_id, user_id=aluno.id)
    
    if sucesso:
        logger.info(f"Professor {current_user.id} excluiu exercício {exercicio_id} do aluno {aluno.id}")
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))


# =============================================
# GERENCIAMENTO DE TREINOS EM VERSÕES (CORRIGIDO)
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino_versao_aluno(aluno_id, versao_id):
    """Adiciona um treino existente a uma versão"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        treino_id = request.form.get('treino_id')
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        
        if not treino_id or not nome_treino:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
        
        if not treino:
            flash('Treino não encontrado!', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        existe = TreinoVersao.query.filter_by(versao_id=versao_id, treino_id=treino.id).first()
        if existe:
            flash(f'Treino {treino.codigo} já existe nesta versão!', 'warning')
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        exercicios = ExercicioService.get_by_treino(treino.id, user_id=aluno.id)
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
            logger.info(f"Professor {current_user.id} adicionou treino {treino.codigo} à versão {versao_id} do aluno {aluno.id}")
            flash(f'Treino {treino.codigo} adicionado à versão com sucesso!', 'success')
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar treino à versão: {str(e)}")
            flash(f'Erro ao adicionar treino: {str(e)}', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    treinos_disponiveis = TreinoService.get_all(user_id=aluno.id)
    treinos_na_versao = [tv.treino_id for tv in versao.treinos]
    treinos_livres = [t for t in treinos_disponiveis if t.id not in treinos_na_versao]
    
    return render_template('professor/novo_treino_versao_aluno.html',
                         aluno=aluno,
                         versao=versao,
                         treinos=treinos_livres)


# ==========================================================
# ROTA EDITAR TREINO VERSÃO ALUNO (CORRIGIDA - COMPLETA)
# ==========================================================

@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao_aluno(aluno_id, versao_id, treino_codigo):
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    aluno = User.query.get_or_404(aluno_id)
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        valores = request.form.getlist('exercicios[]')
        usuarios_ids = []
        bases_ids = []
        
        for val in valores:
            if val.startswith('u_'):
                usuarios_ids.append(int(val[2:]))
            elif val.startswith('b_'):
                bases_ids.append(int(val[2:]))
        
        if not usuarios_ids and not bases_ids:
            flash('Selecione pelo menos um exercício!', 'danger')
            return redirect(request.url)
        
        from models import ExercicioUsuario, ExercicioBase
        usuarios_ids_validos = [eid for eid in usuarios_ids if ExercicioUsuario.query.get(eid)]
        bases_ids_validos = [eid for eid in bases_ids if ExercicioBase.query.get(eid)]
        
        try:
            versao = VersaoService.get_by_id(versao_id, user_id=aluno.id, load_relations=True)
            if not versao:
                flash('Versão não encontrada!', 'danger')
                return redirect(request.url)
            
            treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=aluno.id)
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
            
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id,
                usuarios_ids_validos,
                bases_ids_validos
            )
            
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado!', 'success')
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao editar treino: {e}")
            flash(str(e), 'danger')
            return redirect(request.url)
    
    # ==========================================================
    # MÉTODO GET - CARREGAR FORMULÁRIO
    # ==========================================================
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=aluno.id)
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    if not treino_versao:
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    # ✅ CORREÇÃO: Construir lista de exercícios atuais com prefixo
    exercicios_atuais = []
    for ve in treino_versao.exercicios:
        if ve.exercicio_usuario_id:
            exercicios_atuais.append(f"u_{ve.exercicio_usuario_id}")
        elif ve.exercicio_base_id:
            exercicios_atuais.append(f"b_{ve.exercicio_base_id}")
    
    # Buscar todos os exercícios (base + usuário) do aluno
    todos_exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    exercicios_display = []
    
    # Criar conjunto de IDs selecionados para busca rápida
    selected_ids = set()
    for e in exercicios_atuais:
        if '_' in e:
            selected_ids.add(int(e.split('_')[1]))
    
    for ex in todos_exercicios:
        musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': musculo_nome,
            'tipo': getattr(ex, 'tipo', 'usuario'),
            'checked': ex.id in selected_ids
        })
    
    musculos = MusculoService.get_all_nomes()
    
    return render_template('professor/editar_treino_versao_aluno.html',
                         aluno=aluno,
                         versao=versao,
                         treino_id=treino_codigo,
                         treino={
                             "nome": treino_versao.nome_treino,
                             "descricao": treino_versao.descricao_treino,
                             "exercicios": exercicios_atuais
                         },
                         exercicios=exercicios_display,
                         musculos=musculos)


# ==========================================================
# ROTA EXCLUIR TREINO VERSÃO ALUNO
# ==========================================================

@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir')
@login_required
def excluir_treino_versao_aluno(aluno_id, versao_id, treino_codigo):
    """Remove um treino de uma versão do aluno"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    try:
        VersaoService.excluir_treino_versao(versao_id, treino_codigo, aluno.id, current_user)
        flash(f'Treino {treino_codigo} removido da versão!', 'success')
    except Exception as e:
        logger.error(f"Erro ao excluir treino da versão: {e}")
        flash(str(e), 'danger')
    
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


# =============================================
# ESTATÍSTICAS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/estatisticas')
@login_required
def estatisticas_aluno(aluno_id):
    """Estatísticas detalhadas de um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver as estatísticas deste aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    from models import db, Musculo, ExercicioCustomizado, RegistroTreino, HistoricoTreino
    from sqlalchemy import func, and_

    musculo_stats_raw = db.session.query(
        Musculo.nome_exibicao.label('musculo'),
        db.func.count(db.distinct(ExercicioCustomizado.id)).label('qtd_exercicios'),
        db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
        db.func.count(HistoricoTreino.id).label('total_series'),
        db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
    ).select_from(Musculo)\
     .outerjoin(ExercicioCustomizado, and_(ExercicioCustomizado.musculo_id == Musculo.id, ExercicioCustomizado.usuario_id == aluno.id))\
     .outerjoin(RegistroTreino, and_(RegistroTreino.exercicio_id == ExercicioCustomizado.id, RegistroTreino.user_id == aluno.id))\
     .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
     .group_by(Musculo.id, Musculo.nome_exibicao)\
     .all()
    
    musculo_stats = {}
    for r in musculo_stats_raw:
        musculo_stats[r.musculo] = {
            'qtd_exercicios': r.qtd_exercicios,
            'qtd_registros': r.qtd_registros,
            'total_series': r.total_series,
            'volume_total': float(r.volume_total)
        }
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    registros = RegistroTreino.query.filter_by(user_id=aluno.id).all()

    treino_stats = {}
    for t in treinos:
        registros_treino = [r for r in registros if r.treino_id == t.id]
        volume_total = 0
        total_series = 0
        exercicios_ids = set()
        for r in registros_treino:
            exercicios_ids.add(r.exercicio_id)
            for s in r.series:
                volume_total += float(s.carga) * s.repeticoes
                total_series += 1

        treino_stats[t.id] = {
            "codigo": t.codigo,
            "nome": t.nome,
            "descricao": t.descricao,
            "qtd_exercicios": len(exercicios_ids),
            "qtd_registros": len(registros_treino),
            "volume_total": volume_total,
            "total_series": total_series
        }
    
    return render_template('professor/estatisticas_aluno.html',
                         aluno=aluno,
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats)


# =============================================
# API PARA PROFESSORES
# =============================================

@professor_bp.route('/api/buscar-alunos')
@login_required
def api_buscar_alunos():
    """API para buscar alunos (usado em selects)"""
    termo = request.args.get('termo', '').lower()
    
    if not current_user.is_professor() and not current_user.is_admin:
        return jsonify([])
    
    if current_user.is_admin:
        query = User.query.filter_by(tipo_usuario='aluno', ativo=True)
    else:
        alunos_ids = [assoc.aluno_id for assoc in AlunoProfessor.query.filter_by(professor_id=current_user.id, ativo=True).all()]
        query = User.query.filter(User.id.in_(alunos_ids))
    
    if termo:
        query = query.filter(
            (User.nome_completo.ilike(f'%{termo}%')) |
            (User.username.ilike(f'%{termo}%')) |
            (User.email.ilike(f'%{termo}%'))
        )
    
    alunos = query.limit(20).all()
    
    return jsonify([{
        'id': a.id,
        'nome': a.nome_completo or a.username,
        'username': a.username,
        'email': a.email
    } for a in alunos])