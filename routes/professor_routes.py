from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, AlunoProfessor, Treino, ExercicioCustomizado, RegistroTreino, SolicitacaoVinculo
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
from services.estatistica_service import EstatisticaService
from services.seed_service import SeedService
from datetime import datetime
import logging

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
    
    # Estatísticas gerais
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
    
    # Filtros
    busca = request.args.get('busca', '')
    status = request.args.get('status', 'ativos')
    
    query = AlunoProfessor.query.filter_by(professor_id=current_user.id, ativo=True)
    
    alunos = []
    for assoc in query.all():
        aluno = User.query.get(assoc.aluno_id)
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
        
        # Validações
        if not username or not email or not password:
            flash('Todos os campos são obrigatórios', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if len(username) < 3:
            flash('Usuário deve ter pelo menos 3 caracteres', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if len(password) < 6:
            flash('Senha deve ter pelo menos 6 caracteres', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        # Verificar se usuário já existe
        if User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado', 'danger')
            return redirect(url_for('professor.novo_aluno'))
        
        # Criar novo aluno
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
        db.session.flush()  # Para obter o ID do aluno
        
        # Criar vínculo com o professor
        vinculo = AlunoProfessor(
            aluno_id=aluno.id,
            professor_id=current_user.id,
            data_associacao=datetime.now(),
            ativo=True
        )
        db.session.add(vinculo)
        
        # Criar treinos mínimos para o aluno
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    # Estatísticas do aluno
    treinos = TreinoService.get_all(user_id=aluno.id)
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    registros = RegistroTreino.query.filter_by(user_id=aluno.id).count()
    
    # Últimos registros
    ultimos_registros = RegistroTreino.query.filter_by(user_id=aluno.id)\
        .order_by(RegistroTreino.data_registro.desc())\
        .limit(10).all()
    
    # Versão ativa
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
    """Desativa um aluno (não exclui, apenas marca como inativo)"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
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
    
    # Verificar permissão
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
    
    # Verificar permissão
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
# ROTAS DE SOLICITAÇÕES (ADICIONADAS)
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
    
    # Verificar se a solicitação é para este professor
    if solicitacao.professor_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para aprovar esta solicitação.', 'danger')
        return redirect(url_for('professor.solicitacoes'))
    
    # Verificar se já está aprovada
    if solicitacao.status != 'pendente':
        flash('Esta solicitação já foi processada.', 'warning')
        return redirect(url_for('professor.solicitacoes'))
    
    # Atualizar status
    solicitacao.status = 'aprovado'
    solicitacao.data_resposta = datetime.now()
    
    # Criar vínculo se não existir
    vinculo_existente = AlunoProfessor.query.filter_by(
        aluno_id=solicitacao.aluno_id,
        ativo=True
    ).first()
    
    if not vinculo_existente:
        vinculo = AlunoProfessor(
            aluno_id=solicitacao.aluno_id,
            professor_id=current_user.id,
            data_associacao=datetime.now(),
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
    
    # Verificar se a solicitação é para este professor
    if solicitacao.professor_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para recusar esta solicitação.', 'danger')
        return redirect(url_for('professor.solicitacoes'))
    
    # Verificar se já está processada
    if solicitacao.status != 'pendente':
        flash('Esta solicitação já foi processada.', 'warning')
        return redirect(url_for('professor.solicitacoes'))
    
    # Atualizar status
    solicitacao.status = 'recusado'
    solicitacao.data_resposta = datetime.now()
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versoes = VersaoService.get_all(user_id=aluno.id)
    
    return render_template('professor/versoes_aluno.html',
                         aluno=aluno,
                         versoes=versoes)


@professor_bp.route('/aluno/<int:aluno_id>/versao/nova', methods=['GET', 'POST'])
@login_required
def nova_versao_aluno(aluno_id):
    """Cria uma nova versão para o aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        divisao = request.form.get('divisao', 'ABC')
        data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        
        # Finalizar versão atual do aluno se existir
        versao_atual = VersaoService.get_ativa(user_id=aluno.id)
        if versao_atual and not data_fim:
            versao_atual.data_fim = data_inicio
            db.session.add(versao_atual)
        
        # Criar nova versão
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
    
    # GET - exibir formulário
    return render_template('professor/nova_versao_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>', methods=['GET', 'POST'])
@login_required
def ver_versao_aluno(aluno_id, versao_id):
    """Visualiza e edita uma versão específica do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id, load_relations=True)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        # Atualizar dados da versão
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
    
    # GET - exibir detalhes
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
    
    # Verificar permissão
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
    
    # Verificar permissão
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    # Verificar se é a versão atual
    versao_ativa = VersaoService.get_ativa(user_id=aluno.id)
    if versao_ativa and versao_ativa.id == versao_id:
        flash('Não é possível excluir a versão ativa. Finalize-a primeiro.', 'warning')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    # Verificar registros
    registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=aluno.id).first()
    
    if registros:
        flash('Não é possível excluir esta versão pois existem registros vinculados.', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    # Confirmar exclusão
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    
    # Contar exercícios por treino
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        # Validar código
        if not codigo or not codigo.isalpha() or len(codigo) != 1:
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(url_for('professor.novo_treino_aluno', aluno_id=aluno.id))
        
        # Verificar se já existe
        existente = TreinoService.get_by_codigo(codigo, user_id=aluno.id)
        if existente:
            flash(f'Treino {codigo} já existe para este aluno!', 'danger')
            return redirect(url_for('professor.novo_treino_aluno', aluno_id=aluno.id))
        
        # Criar treino
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
    import logging
    logger = logging.getLogger(__name__)
    
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
    
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        logger.info("=" * 50)
        logger.info("EDITANDO TREINO - DADOS RECEBIDOS")
        logger.info(f"Aluno ID: {aluno_id}")
        logger.info(f"Treino ID: {treino_id}")
        
        novo_codigo = request.form.get('id').upper()
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')
        
        logger.info(f"Dados básicos: código={novo_codigo}, nome={nome}, descricao={descricao}")
        
        # Atualizar treino
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
    
    return render_template('professor/editar_treino_aluno.html',
                         aluno=aluno,
                         treino=treino)

@professor_bp.route('/aluno/editar/<int:aluno_id>', methods=['GET', 'POST'])
@login_required
def editar_aluno(aluno_id):
    """Edita os dados de um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para editar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        nova_senha = request.form.get('nova_senha')
        
        # Validar email único
        if email != aluno.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('Este e-mail já está em uso por outro usuário.', 'danger')
                return redirect(url_for('professor.editar_aluno', aluno_id=aluno.id))
        
        # Atualizar dados
        aluno.nome_completo = nome_completo
        aluno.email = email
        aluno.telefone = telefone
        
        # Atualizar senha se fornecida
        if nova_senha and len(nova_senha) >= 6:
            aluno.set_password(nova_senha)
            flash('Senha alterada com sucesso!', 'success')
        
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} editou aluno {aluno.id}")
        flash(f'Dados de {aluno.nome_completo or aluno.username} atualizados!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    # GET - exibir formulário
    return render_template('professor/editar_aluno.html', aluno=aluno)

@professor_bp.route('/aluno/<int:aluno_id>/treino/<int:treino_id>/excluir')
@login_required
def excluir_treino_aluno(aluno_id, treino_id):
    """Exclui um treino do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
    
    if not treino:
        flash('Treino não encontrado!', 'danger')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    # Confirmar exclusão
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    treinos = TreinoService.get_all(user_id=aluno.id)
    
    # Buscar últimas cargas
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
    
    # Verificar permissão
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
        
        # Criar exercício
        exercicio = ExercicioService.create(
            nome=nome,
            musculo_nome=musculo or 'Outros',
            treino_id=treino_id,
            descricao=descricao,
            user_id=aluno.id
        )
        
        if exercicio:
            logger.info(f"Professor {current_user.id} criou exercício {exercicio.id} para aluno {aluno.id}")
            flash(f'Exercício {nome} criado para {aluno.nome_completo or aluno.username}!', 'success')
            return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao criar exercício!', 'danger')
    
    # GET - exibir formulário
    treinos = TreinoService.get_all(user_id=aluno.id)
    from services.musculo_service import MusculoService
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
    
    # Verificar permissão
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
        
        # Atualizar exercício
        exercicio_atualizado = ExercicioService.update(
            exercicio_id=exercicio_id,
            nome=nome,
            musculo_nome=musculo,
            treino_id=treino_id,
            descricao=descricao,
            user_id=aluno.id
        )
        
        if exercicio_atualizado:
            logger.info(f"Professor {current_user.id} editou exercício {exercicio_id} do aluno {aluno.id}")
            flash('Exercício atualizado!', 'success')
            return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
        else:
            flash('Erro ao atualizar exercício!', 'danger')
    
    # GET - exibir formulário
    treinos = TreinoService.get_all(user_id=aluno.id)
    from services.musculo_service import MusculoService
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
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=aluno.id)
    
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    # Confirmar exclusão
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão de "{exercicio.nome}".', 'warning')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    if ExercicioService.delete(exercicio_id, user_id=aluno.id):
        logger.info(f"Professor {current_user.id} excluiu exercício {exercicio_id} do aluno {aluno.id}")
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))


# =============================================
# GERENCIAMENTO DE TREINOS EM VERSÕES
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/novo', methods=['GET', 'POST'])
@login_required
def novo_treino_versao_aluno(aluno_id, versao_id):
    """Adiciona um treino existente a uma versão"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
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
        
        # Validar campos obrigatórios
        if not treino_id or not nome_treino:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        treino = TreinoService.get_by_id(treino_id, user_id=aluno.id)
        
        if not treino:
            flash('Treino não encontrado!', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        # Verificar se o treino já existe na versão
        from models import TreinoVersao
        existe = TreinoVersao.query.filter_by(
            versao_id=versao_id,
            treino_id=treino.id
        ).first()
        
        if existe:
            flash(f'Treino {treino.codigo} já existe nesta versão!', 'warning')
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
        
        # Buscar exercícios do treino
        exercicios = ExercicioService.get_by_treino(treino.id, user_id=aluno.id)
        exercicios_ids = [ex.id for ex in exercicios]
        
        # Adicionar treino à versão
        try:
            from models import TreinoVersao, VersaoExercicio
            from datetime import datetime
            
            # Criar nova associação do treino com a versão
            treino_versao = TreinoVersao(
                versao_id=versao_id,
                treino_id=treino.id,
                nome_treino=nome_treino,
                descricao_treino=descricao_treino,
                ordem=len(versao.treinos)  # Adicionar no final
            )
            db.session.add(treino_versao)
            db.session.flush()  # Para obter o ID
            
            # Adicionar exercícios
            for ordem, ex_id in enumerate(exercicios_ids):
                # Verificar se o exercício é do tipo ExercicioCustomizado
                exercicio_custom = ExercicioCustomizado.query.filter_by(id=ex_id).first()

                if exercicio_custom:
                    # É um exercício customizado
                    ve = VersaoExercicio(
                        treino_versao_id=treino_versao.id,
                        exercicio_custom_id=ex_id,
                        ordem=ordem
                    )
                else:
                    # É um exercício normal (da tabela exercicios)
                    ve = VersaoExercicio(
                        treino_versao_id=treino_versao.id,
                        exercicio_id=ex_id,
                        ordem=ordem
                    )
                db.session.add(ve)
            
            db.session.commit()
            
            logger.info(f"Professor {current_user.id} adicionou treino {treino.codigo} à versão {versao_id} do aluno {aluno.id}")
            flash(f'Treino {treino.codigo} adicionado à versão com sucesso!', 'success')
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar treino à versão: {str(e)}")
            flash(f'Erro ao adicionar treino: {str(e)}', 'danger')
            return redirect(url_for('professor.novo_treino_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    # GET - exibir formulário
    treinos_disponiveis = TreinoService.get_all(user_id=aluno.id)
    
    # Filtrar apenas treinos que ainda não estão na versão
    treinos_na_versao = [tv.treino_id for tv in versao.treinos]
    treinos_livres = [t for t in treinos_disponiveis if t.id not in treinos_na_versao]
    
    return render_template('professor/novo_treino_versao_aluno.html',
                         aluno=aluno,
                         versao=versao,
                         treinos=treinos_livres)


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<string:treino_codigo>/editar', methods=['GET', 'POST'])
@login_required
def editar_treino_versao_aluno(aluno_id, versao_id, treino_codigo):
    """Edita um treino específico dentro de uma versão"""
    import logging
    import sys
    import traceback
    import hashlib
    import json
    
    logger = logging.getLogger(__name__)
    
    # Configurar logging para debug
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    
    logger.info("=" * 60)
    logger.info("INICIANDO EDIÇÃO DE TREINO NA VERSÃO")
    logger.info(f"Aluno ID: {aluno_id}")
    logger.info(f"Versão ID: {versao_id}")
    logger.info(f"Treino Código: {treino_codigo}")
    
    from models import db, VersaoExercicio, TreinoVersao, User, ExercicioCustomizado, ExercicioBase
    from services.catalogo_service import CatalogoService
    from services.musculo_service import MusculoService
    
    aluno = User.query.get_or_404(aluno_id)
    logger.info(f"Aluno encontrado: {aluno.username}")
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        logger.warning(f"Permissão negada para usuário {current_user.id}")
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        logger.error(f"Versão {versao_id} não encontrada para aluno {aluno.id}")
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    logger.info(f"Versão encontrada: {versao.descricao} (divisão: {versao.divisao})")
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=aluno.id)
    
    if not treino_ref:
        logger.error(f"Treino {treino_codigo} não encontrado para aluno {aluno.id}")
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    logger.info(f"Treino encontrado: {treino_ref.nome} (ID: {treino_ref.id})")
    
    # Encontrar o treino na versão
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            logger.info(f"Treino na versão encontrado: ID {tv.id}, nome: {tv.nome_treino}")
            break
    
    if not treino_versao:
        logger.error(f"Treino {treino_codigo} não encontrado na versão {versao_id}")
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    if request.method == 'POST':
        logger.info("-" * 40)
        logger.info("PROCESSANDO SUBMISSÃO DO FORMULÁRIO")
        
        logger.info(f"Form data keys: {list(request.form.keys())}")
        logger.info(f"Form data values: {dict(request.form)}")
        
        nome_treino = request.form.get('nome_treino')
        descricao_treino = request.form.get('descricao_treino', '')
        exercicios_ids_raw = request.form.getlist('exercicios[]')
        
        logger.info(f"🔍 RAW - Nome do Treino: {nome_treino}")
        logger.info(f"🔍 RAW - Descrição: {descricao_treino}")
        logger.info(f"🔍 RAW - Exercícios IDs recebidos: {exercicios_ids_raw}")
        logger.info(f"🔍 RAW - Quantidade de exercícios: {len(exercicios_ids_raw)}")
        
        # Tentar obter dados dos exercícios do formulário
        exercicios_dados_raw = request.form.get('exercicios_dados', '[]')
        try:
            exercicios_dados = json.loads(exercicios_dados_raw)
            logger.info(f"📦 Dados dos exercícios recebidos: {len(exercicios_dados)} itens")
        except:
            exercicios_dados = []
            logger.info("📦 Nenhum dado adicional de exercícios recebido")
        
        dados_por_id = {str(item['id']): item for item in exercicios_dados}
        
        # Converter para inteiros
        exercicios_ids = []
        for id_str in exercicios_ids_raw:
            if id_str and id_str.strip():
                try:
                    exercicios_ids.append(int(id_str))
                except ValueError as e:
                    logger.error(f"Erro ao converter ID '{id_str}' para inteiro: {e}")
        
        logger.info(f"🔍 CONVERTIDOS - Exercícios IDs: {exercicios_ids}")
        logger.info(f"🔍 CONVERTIDOS - Quantidade: {len(exercicios_ids)}")
        
        if not exercicios_ids:
            logger.warning("❌ Nenhum exercício selecionado!")
            flash('Selecione pelo menos um exercício para o treino!', 'danger')
            return redirect(request.url)
        
        exercicios_atuais = [ve.exercicio_id for ve in treino_versao.exercicios]
        logger.info(f"🔍 ANTES - Exercícios atuais na versão: {exercicios_atuais}")
        
        treino_versao.nome_treino = nome_treino
        treino_versao.descricao_treino = descricao_treino
        logger.info("Dados básicos do treino atualizados")
        
        exercicios_finais = []
        exercicios_criados = 0
        
        # Processar cada exercício
        for ex_id in exercicios_ids:
            logger.info(f"Processando exercício ID: {ex_id}")

            exercicio_custom = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id, id=ex_id).first()
            if exercicio_custom:
                logger.info(f"✅ Exercício ID {ex_id} já existe (customizado)")
                exercicios_finais.append(ex_id)
                continue
                continue
            
            exercicio_base = ExercicioBase.query.filter_by(id=ex_id).first()
            if exercicio_base:
                logger.info(f"✅ Exercício ID {ex_id} já existe (base)")
                exercicios_finais.append(ex_id)
                continue
            
            logger.info(f"🔍 Exercício ID {ex_id} não encontrado. Buscando no catálogo...")
            
            # Buscar no catálogo
            catalogo = CatalogoService.get_catalogo()
            
            exercicio_catalogo = None
            for ex in catalogo:
                hash_id = int(hashlib.md5(ex.get('name', '').encode()).hexdigest()[:8], 16)
                if hash_id == ex_id:
                    exercicio_catalogo = ex
                    logger.info(f"✅ Exercício encontrado no catálogo: {ex.get('name')}")
                    break
            
            if exercicio_catalogo:
                primary_muscles = exercicio_catalogo.get('primaryMuscles', [])
                musculo_original = primary_muscles[0] if primary_muscles else "Outros"
                
                mapa_musculos = {
                    'abdominais': 'Abdômen', 'abductors': 'Abdutores', 'adductors': 'Adutores',
                    'biceps': 'Bíceps', 'calves': 'Panturrilhas', 'chest': 'Peitoral',
                    'forearms': 'Antebraços', 'glutes': 'Glúteos', 'hamstrings': 'Posterior de Coxa',
                    'lats': 'Dorsal', 'lower back': 'Lombar', 'middle back': 'Costas',
                    'neck': 'Pescoço', 'quadriceps': 'Quadríceps', 'shoulders': 'Ombros',
                    'traps': 'Trapézio', 'triceps': 'Tríceps'
                }
                
                musculo_nome = mapa_musculos.get(musculo_original.lower(), musculo_original.title())
                logger.info(f"Músculo mapeado: {musculo_nome}")
                
                musculo_base = Musculo.query.filter_by(nome_exibicao=musculo_nome).first()
                if not musculo_base:
                    musculo_base = Musculo(nome=musculo_nome.lower(), nome_exibicao=musculo_nome)
                    db.session.add(musculo_base)
                    db.session.flush()
                
                # Criar como ExercicioCustomizado
                novo_exercicio = ExercicioCustomizado(
                    usuario_id=aluno.id,
                    nome=exercicio_catalogo.get('name', ''),
                    descricao="Exercício do catálogo",
                    musculo_id=musculo_base.id
                )
                db.session.add(novo_exercicio)
                db.session.flush()
                
                logger.info(f"✅ Novo exercício customizado criado: ID {novo_exercicio.id}")
                exercicios_finais.append(novo_exercicio.id)
                exercicios_criados += 1
            else:
                logger.warning(f"❌ Exercício ID {ex_id} não encontrado no catálogo")
                dados_ex = dados_por_id.get(str(ex_id), {})
                nome_exercicio = dados_ex.get('nome', f"Exercício {ex_id}")
                musculo_ex = dados_ex.get('musculo', 'Outros')
                
                logger.info(f"Criando exercício fallback: {nome_exercicio}")
                
                musculo_base = Musculo.query.filter_by(nome_exibicao=musculo_ex).first()
                if not musculo_base:
                    musculo_base = Musculo(nome=musculo_ex.lower(), nome_exibicao=musculo_ex)
                    db.session.add(musculo_base)
                    db.session.flush()
                
                novo_exercicio = ExercicioCustomizado(
                    usuario_id=aluno.id,
                    nome=nome_exercicio,
                    descricao="Exercício criado automaticamente",
                    musculo_id=musculo_base.id
                )
                db.session.add(novo_exercicio)
                db.session.flush()
                
                logger.info(f"✅ Exercício fallback criado: ID {novo_exercicio.id}")
                exercicios_finais.append(novo_exercicio.id)
                exercicios_criados += 1
        
        logger.info(f"🔍 FINAIS - Exercícios: {exercicios_finais}")
        
        # Remover exercícios antigos
        antigos = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao.id).all()
        logger.info(f"Removendo {len(antigos)} exercícios antigos")
        
        deleted = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao.id).delete()
        logger.info(f"Registros deletados: {deleted}")
        db.session.flush()
        
        # =============================================
        # PARTE CORRIGIDA - ADICIONAR EXERCÍCIOS COM O CAMPO CORRETO
        # =============================================
        for ordem, ex_id in enumerate(exercicios_finais):
            logger.info(f"Adicionando exercício ID {ex_id} na ordem {ordem}")
            
            # Todos os exercícios agora são ExercicioCustomizado
            exercicio_custom = ExercicioCustomizado.query.filter_by(id=ex_id).first()

            if exercicio_custom:
                ve = VersaoExercicio(
                    treino_versao_id=treino_versao.id,
                    exercicio_id=ex_id,
                    ordem=ordem
                )
                logger.info(f"✅ Exercício {ex_id} adicionado")
            else:
                logger.error(f"❌ Exercício ID {ex_id} não encontrado!")
                continue
            
            db.session.add(ve)
        
        # Commit final
        try:
            db.session.commit()
            logger.info(f"✅ COMMIT REALIZADO COM SUCESSO!")
            
            exercicios_salvos = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao.id).all()
            logger.info(f"🔍 APÓS - {len(exercicios_salvos)} exercícios salvos")
            
            if exercicios_criados > 0:
                flash(f'Treino atualizado! {exercicios_criados} novo(s) exercício(s) foram criados.', 'success')
            else:
                flash(f'Treino {treino_codigo} atualizado com sucesso!', 'success')
                
            return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ ERRO AO COMMIT: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f'Erro ao atualizar treino: {str(e)}', 'danger')
            return redirect(request.url)
    
    # GET - mostrar formulário
    logger.info("Carregando formulário GET")

    exercicios_custom = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id).all()
    logger.info(f"Exercícios customizados: {len(exercicios_custom)}")
    
    catalogo_exercicios = CatalogoService.get_todos_exercicios(limite=500)
    logger.info(f"Exercícios no catálogo: {len(catalogo_exercicios)}")
    
    exercicios_display = []
    
    for ex in exercicios_banco:
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A',
            'tipo': 'banco'
        })
    
    for ex in exercicios_custom:
        musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
        exercicios_display.append({
            'id': ex.id,
            'nome': ex.nome,
            'musculo': musculo_nome,
            'tipo': 'custom'
        })
    
    for ex in catalogo_exercicios:
        existe = False
        for ex_display in exercicios_display:
            if ex_display['nome'].lower() == ex['nome'].lower():
                existe = True
                break
        if not existe:
            exercicios_display.append({
                'id': ex['id'],
                'nome': ex['nome'],
                'musculo': ex['musculo'],
                'tipo': 'catalogo'
            })
    
    exercicios_display.sort(key=lambda x: x['nome'])
    
    exercicios_atuais = [ve.exercicio_id for ve in treino_versao.exercicios]
    logger.info(f"Exercícios atuais na versão: {exercicios_atuais}")
    
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

@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<string:treino_codigo>/excluir')
@login_required
def excluir_treino_versao_aluno(aluno_id, versao_id, treino_codigo):
    """Remove um treino de uma versão"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id)
    
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=aluno.id)
    
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))
    
    from models import TreinoVersao
    resultado = TreinoVersao.query.filter_by(
        versao_id=versao_id,
        treino_id=treino_ref.id
    ).delete()
    
    if resultado:
        db.session.commit()
        logger.info(f"Professor {current_user.id} removeu treino {treino_codigo} da versão {versao_id} do aluno {aluno.id}")
        flash(f'Treino {treino_codigo} removido da versão!', 'success')
    else:
        flash(f'Erro ao remover treino {treino_codigo}!', 'danger')
    
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))

# =============================================
# ESTATÍSTICAS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/estatisticas')
@login_required
def estatisticas_aluno(aluno_id):
    """Estatísticas detalhadas de um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    # Verificar permissão
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver as estatísticas deste aluno.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    # Calcular estatísticas por músculo
    from models import db, Musculo, ExercicioCustomizado, RegistroTreino, HistoricoTreino
    from sqlalchemy import func, and_

    # Estatísticas por músculo
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
    
    # Estatísticas por treino
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
        # Professores só veem alunos já vinculados
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