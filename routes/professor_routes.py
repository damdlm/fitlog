from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, AlunoProfessor, RegistroTreino, SolicitacaoVinculo, VersaoGlobal, HistoricoTreino
from services.treino_service import TreinoService
from services.exercicio_service import ExercicioService
from services.versao_service import VersaoService
from services.estatistica_service import EstatisticaService
from services.musculo_service import MusculoService
from services.billing_service import BillingService
from services.dashboard_service import DashboardService
from utils.decorators import professor_acesso_alunos_required
from extensions import limiter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import json

professor_bp = Blueprint('professor', __name__, url_prefix='/professor')
logger = logging.getLogger(__name__)

# =============================================
# DASHBOARD OPERACIONAL
# =============================================

@professor_bp.route('/dashboard')
@login_required
def dashboard():
    """Painel operacional do professor: 'o que eu preciso fazer hoje'.

    Todos os números vêm de DashboardService.dados_professor, sempre
    escopados a current_user.id (nunca a um ID vindo do request) --
    mesmo padrão de autorização das demais rotas deste arquivo. Não é
    uma tela premium (não passa por @acesso_premium_required): é a
    ferramenta de trabalho básica do professor, igual a listar_alunos.
    """
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    dados = DashboardService.dados_professor(current_user.id)

    hora_atual = datetime.now(ZoneInfo('America/Sao_Paulo')).hour
    if hora_atual < 12:
        saudacao = 'Bom dia'
    elif hora_atual < 18:
        saudacao = 'Boa tarde'
    else:
        saudacao = 'Boa noite'

    return render_template('professor/dashboard.html', dados=dados, saudacao=saudacao)


# =============================================
# GERENCIAMENTO DE ALUNOS
# =============================================

@professor_bp.route('/alunos')
@login_required
def listar_alunos():
    """Lista os alunos vinculados e ativos do professor"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    busca = request.args.get('busca', '').strip()
    
    # Uma única query com joinedload evita o N+1 de buscar cada aluno
    # individualmente (db.session.get dentro do loop).
    vinculos = (AlunoProfessor.query
                .options(joinedload(AlunoProfessor.aluno))
                .filter_by(professor_id=current_user.id, ativo=True)
                .all())
    
    busca_lower = busca.lower()
    alunos_data = []
    for vinculo in vinculos:
        aluno = vinculo.aluno
        if not aluno or not aluno.ativo:
            continue
        if busca_lower and busca_lower not in (aluno.nome_completo or '').lower() \
                and busca_lower not in aluno.username.lower() \
                and busca_lower not in aluno.email.lower():
            continue
        alunos_data.append({'aluno': aluno, 'vinculado_desde': vinculo.data_associacao})
    
    alunos_data.sort(key=lambda d: (d['aluno'].nome_completo or d['aluno'].username).lower())
    
    # Contagem de registros por aluno em uma única query (sem N+1 no template)
    registros_por_aluno = {}
    aluno_ids = [d['aluno'].id for d in alunos_data]
    if aluno_ids:
        contagem = (db.session.query(RegistroTreino.user_id, func.count(RegistroTreino.id))
                    .filter(RegistroTreino.user_id.in_(aluno_ids))
                    .group_by(RegistroTreino.user_id)
                    .all())
        registros_por_aluno = dict(contagem)
    
    return render_template('professor/alunos.html', 
                         alunos_data=alunos_data,
                         registros_por_aluno=registros_por_aluno,
                         busca=busca)


@professor_bp.route('/aluno/novo', methods=['GET', 'POST'])
@login_required
def novo_aluno():
    """Cadastra um novo aluno e já vincula ao professor"""
    if not current_user.is_professor() and not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        if not current_user.is_admin:
            pode, mensagem = BillingService.pode_cadastrar_aluno(current_user)
            if not pode:
                flash(mensagem, 'warning')
                return redirect(url_for('professor.novo_aluno'))

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

        # Mesmo trial de 30 dias do cadastro público (auth.register) --
        # ver services/billing_service.py:iniciar_trial. Entra na
        # mesma transação (commit único logo abaixo).
        BillingService.iniciar_trial(aluno)

        db.session.commit()
        
        logger.info(f"Professor {current_user.id} cadastrou novo aluno {aluno.id}")
        flash(f'Aluno {nome_completo or username} cadastrado com sucesso!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    return render_template('professor/novo_aluno.html')


@professor_bp.route('/aluno/<int:aluno_id>')
@login_required
@professor_acesso_alunos_required
def visualizar_aluno(aluno_id):
    """Visualiza detalhes de um aluno específico"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
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


@professor_bp.route('/aluno/desativar/<int:aluno_id>', methods=['POST'])
@login_required
@professor_acesso_alunos_required
def desativar_aluno(aluno_id):
    """Desativa um aluno — ação restrita ao admin"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not current_user.is_admin:
        flash('Você não tem permissão para desativar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    aluno.ativo = False
    db.session.commit()
    flash(f'Aluno {aluno.nome_completo or aluno.username} desativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/reativar/<int:aluno_id>', methods=['POST'])
@login_required
@professor_acesso_alunos_required
def reativar_aluno(aluno_id):
    """Reativa um aluno — ação restrita ao admin"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not current_user.is_admin:
        flash('Você não tem permissão para reativar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    aluno.ativo = True
    db.session.commit()
    flash(f'Aluno {aluno.nome_completo or aluno.username} reativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/remover-vinculo/<int:aluno_id>', methods=['POST'])
@login_required
@professor_acesso_alunos_required
def remover_vinculo(aluno_id):
    """Remove o vínculo entre professor e aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para remover este vínculo.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    assoc = AlunoProfessor.query.filter_by(aluno_id=aluno_id, ativo=True).first()
    if assoc:
        assoc.ativo = False
        db.session.commit()
        flash(f'Vínculo com {aluno.nome_completo or aluno.username} removido!', 'success')
    
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/editar/<int:aluno_id>', methods=['GET', 'POST'])
@login_required
@professor_acesso_alunos_required
def editar_aluno(aluno_id):
    """Edita os dados de um aluno — ação restrita ao admin"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not current_user.is_admin:
        flash('Você não tem permissão para editar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
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

    if not current_user.is_admin:
        pode, mensagem = BillingService.pode_cadastrar_aluno(current_user)
        if not pode:
            flash(mensagem, 'warning')
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
# GERENCIAMENTO DE EXERCÍCIOS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/exercicios')
@login_required
@professor_acesso_alunos_required
def exercicios_aluno(aluno_id):
    """Lista todos os exercícios do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    exercicios = ExercicioService.get_exercicios_completos(user_id=aluno.id)
    treinos = TreinoService.get_all(user_id=aluno.id)
    
    subq = db.session.query(
        RegistroTreino.exercicio_id,
        func.max(RegistroTreino.data_registro).label('max_data')
    ).filter_by(user_id=aluno.id).group_by(RegistroTreino.exercicio_id).subquery()
    
    cargas_query = db.session.query(
        RegistroTreino.exercicio_id,
        HistoricoTreino.carga
    ).join(subq, (RegistroTreino.exercicio_id == subq.c.exercicio_id) & 
                  (RegistroTreino.data_registro == subq.c.max_data))\
     .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
     .filter(HistoricoTreino.ordem == 1).all()
    
    ultimas_cargas = {ex_id: float(carga) for ex_id, carga in cargas_query}
    
    return render_template('professor/exercicios_aluno.html',
                         aluno=aluno,
                         exercicios=exercicios,
                         treinos=treinos,
                         ultimas_cargas=ultimas_cargas)


@professor_bp.route('/aluno/<int:aluno_id>/exercicio/novo', methods=['GET', 'POST'])
@login_required
@professor_acesso_alunos_required
def novo_exercicio_aluno(aluno_id):
    """Cria um novo exercício para o aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(url_for('professor.novo_exercicio_aluno', aluno_id=aluno.id))
        
        exercicio = ExercicioService.criar_exercicio_customizado(
            user_id=aluno.id,
            nome=nome,
            musculo_nome=musculo or 'Outros',
            descricao=descricao
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
@professor_acesso_alunos_required
def editar_exercicio_aluno(aluno_id, exercicio_id):
    """Edita um exercício do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=aluno.id, load_relations=True)
    
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))

    if not (hasattr(exercicio, 'is_custom') and exercicio.is_custom):
        flash('Este exercício faz parte do catálogo geral e não pode ser editado. Crie um exercício personalizado para o aluno se quiser algo diferente.', 'warning')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        musculo = request.form.get('musculo')
        descricao = request.form.get('descricao', '')
        
        musculo_obj = MusculoService.get_or_create(musculo)
        exercicio_atualizado = ExercicioService.update_exercicio_customizado(
            exercicio_custom_id=exercicio_id,
            user_id=aluno.id,
            nome=nome,
            descricao=descricao,
            musculo_id=musculo_obj.id if musculo_obj else None
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


@professor_bp.route('/aluno/<int:aluno_id>/exercicio/<int:exercicio_id>/excluir', methods=['POST'])
@login_required
@professor_acesso_alunos_required
def excluir_exercicio_aluno(aluno_id, exercicio_id):
    """Exclui um exercício do aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    exercicio = ExercicioService.get_by_id(exercicio_id, user_id=aluno.id)
    
    if not exercicio:
        flash('Exercício não encontrado!', 'danger')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))

    if not (hasattr(exercicio, 'is_custom') and exercicio.is_custom):
        flash('Este exercício faz parte do catálogo geral e não pode ser excluído.', 'warning')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    confirmado = request.args.get('confirmar', 'false').lower() == 'true'
    if not confirmado:
        flash(f'⚠️ Clique novamente para confirmar a exclusão de "{exercicio.nome}".', 'warning')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    sucesso = ExercicioService.delete_exercicio_customizado(exercicio_id, user_id=aluno.id)
    
    if sucesso:
        logger.info(f"Professor {current_user.id} excluiu exercício {exercicio_id} do aluno {aluno.id}")
        flash(f'Exercício "{exercicio.nome}" excluído!', 'success')
    else:
        flash('Erro ao excluir exercício!', 'danger')
    
    return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))


# =============================================
# ESTATÍSTICAS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/estatisticas')
@login_required
@professor_acesso_alunos_required
def estatisticas_aluno(aluno_id):
    """Estatísticas detalhadas de um aluno"""
    aluno = User.query.get_or_404(aluno_id)
    
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver as estatísticas deste aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))
    
    musculo_stats = EstatisticaService.calcular_por_musculo(user_id=aluno.id)
    
    treinos = TreinoService.get_all(user_id=aluno.id)
    registros = RegistroTreino.query.filter_by(user_id=aluno.id).all()

    treino_stats = {}
    for t in treinos:
        registros_treino = [r for r in registros if r.treino_versao_id == t.id]
        volume_total = 0
        total_series = 0
        exercicios_ids = set()
        for r in registros_treino:
            # Mesmo cuidado de services/estatistica_service.py: usar o
            # par (usuario_id, base_id) em vez de r.exercicio_id, que
            # colide quando um exercício personalizado e um do catálogo
            # do sistema têm o mesmo número de ID em tabelas diferentes.
            exercicios_ids.add((r.exercicio_usuario_id, r.exercicio_base_id))
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

    musculo_destaque = None
    if musculo_stats:
        musculos_com_volume = {k: v for k, v in musculo_stats.items() if v['volume_total'] > 0}
        if musculos_com_volume:
            musculo_destaque = max(musculos_com_volume, key=lambda k: musculos_com_volume[k]['volume_total'])

    volume_maximo_musculo = max((v['volume_total'] for v in musculo_stats.values()), default=0)
    
    return render_template('professor/estatisticas_aluno.html',
                         aluno=aluno,
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats,
                         musculo_destaque=musculo_destaque,
                         volume_maximo_musculo=volume_maximo_musculo)


@professor_bp.route('/aluno/<int:aluno_id>/calendario')
@login_required
@professor_acesso_alunos_required
def calendario_aluno(aluno_id):
    """Calendário de treinos de um aluno específico.

    Reaproveita o template calendar/calendario.html (já preparado para
    receber `aluno` e `eventos_api_url`) em vez de duplicar o HTML —
    só troca a URL da API de eventos para incluir aluno_id, e a própria
    /calendar/api/eventos já valida (via BaseService.get_target_user_id)
    se este professor tem vínculo ativo com o aluno.
    """
    aluno = User.query.get_or_404(aluno_id)

    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para ver o calendário deste aluno.', 'danger')
        return redirect(url_for('professor.listar_alunos'))

    data_atual = datetime.now(timezone.utc)

    return render_template(
        'calendar/calendario.html',
        aluno=aluno,
        data_atual=data_atual,
        eventos_api_url=url_for('calendar.api_eventos', aluno_id=aluno.id),
    )


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


# =============================================
# VERSÕES DO ALUNO (tela compartilhada com routes/aluno/versao.py --
# mesmo VersaoService, mesmos templates aluno/versoes.html e
# aluno/ver_versao.html, só que operando em nome do aluno em vez do
# próprio current_user. Ver templates/aluno/versoes.html e
# templates/aluno/ver_versao.html: eles recebem as URLs prontas por
# parâmetro (voltar_url, ver_versao_url, finalizar_url etc.) em vez de
# montar url_for('aluno....') fixo, exatamente para permitir esse reuso.)
# =============================================

def _aluno_ou_negar(aluno_id):
    """Busca o aluno e garante posse (professor dono ou admin). Retorna
    (aluno, None) se ok, ou (None, redirect) se acesso negado."""
    aluno = User.query.get_or_404(aluno_id)
    if not (current_user.is_admin or (current_user.is_professor() and aluno.get_professor() and aluno.get_professor().id == current_user.id)):
        flash('Você não tem permissão para acessar este aluno.', 'danger')
        return None, redirect(url_for('professor.listar_alunos'))
    return aluno, None


def _chave_por_professor():
    return f"professor-versoes-{current_user.id}"


@professor_bp.route('/aluno/<int:aluno_id>/versoes')
@login_required
@professor_acesso_alunos_required
def versoes_aluno(aluno_id):
    """Lista todas as versões do aluno (ativa + finalizadas), mais recente primeiro."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    todas_versoes = VersaoService.get_all(user_id=aluno.id)
    nome_aluno = aluno.nome_completo or aluno.username
    return render_template(
        'aluno/versoes.html',
        versoes=todas_versoes,
        titulo=f'Versões de {nome_aluno}',
        voltar_url=url_for('professor.visualizar_aluno', aluno_id=aluno.id),
        voltar_label='Voltar ao aluno',
        vazio_texto=f'{nome_aluno} ainda não tem nenhuma versão de treino.',
        ver_versao_url=lambda vid: url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=vid),
        pagina_inicial_url=url_for('professor.visualizar_aluno', aluno_id=aluno.id),
        pagina_inicial_label='Voltar ao aluno',
    )


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>')
@login_required
@professor_acesso_alunos_required
def ver_versao_aluno(aluno_id, versao_id):
    """Detalhe de uma versão do aluno (ativa ou finalizada): treinos + exercícios."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    versao = VersaoService.get_by_id(versao_id, user_id=aluno.id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))

    treinos_versao = sorted(versao.treinos, key=lambda tv: tv.ordem or 0)
    exercicios_catalogo = ExercicioService.get_exercicios_completos(user_id=aluno.id)
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

    nome_aluno = aluno.nome_completo or aluno.username
    return render_template(
        'aluno/ver_versao.html',
        versao=versao,
        treinos_versao=treinos_versao,
        exercicios_catalogo=exercicios_catalogo,
        musculos_catalogo=musculos_catalogo,
        treino_exercicios_map=treino_exercicios_map,
        treino_observacoes_map=treino_observacoes_map,
        max_treinos=VersaoService.MAX_TREINOS_POR_VERSAO,
        titulo_sufixo=f' — {nome_aluno}',
        voltar_url=url_for('professor.versoes_aluno', aluno_id=aluno.id),
        voltar_label=f'Versões de {nome_aluno}',
        finalizar_url=url_for('professor.versao_finalizar_aluno', aluno_id=aluno.id, versao_id=versao.id),
        clonar_url=url_for('professor.versao_clonar_aluno', aluno_id=aluno.id, versao_id=versao.id),
        excluir_url=url_for('professor.versao_excluir_aluno', aluno_id=aluno.id, versao_id=versao.id),
        editar_descricao_url=url_for('professor.versao_editar_descricao_aluno', aluno_id=aluno.id, versao_id=versao.id),
        adicionar_treino_url=url_for('professor.versao_adicionar_treino_aluno', aluno_id=aluno.id, versao_id=versao.id),
        salvar_treino_url=lambda tv_id: url_for('professor.versao_salvar_treino_aluno', aluno_id=aluno.id, versao_id=versao.id, treino_versao_id=tv_id),
        remover_treino_url=lambda tv_id: url_for('professor.versao_remover_treino_aluno', aluno_id=aluno.id, versao_id=versao.id, treino_versao_id=tv_id),
        novo_exercicio_url=url_for('professor.novo_exercicio_aluno', aluno_id=aluno.id),
        reordenar_url=url_for('professor.reordenar_exercicios_aluno', aluno_id=aluno.id),
    )


@professor_bp.route('/aluno/<int:aluno_id>/reordenar-exercicios', methods=['POST'])
@login_required
@professor_acesso_alunos_required
def reordenar_exercicios_aluno(aluno_id):
    """Reordena exercícios de um treino do aluno -- espelha
    /api/reordenar-exercicios (routes/api_routes.py), mas resolvendo a
    posse pelo ALUNO (aluno.id), não pelo professor logado. É o mesmo
    bug de fundo que os outros *_aluno abaixo evitam: a versão
    pertence ao aluno, então usar current_user.id (o professor) na
    busca nunca encontra a versão e sempre falha com "Erro ao
    reordenar" -- ver _aluno_ou_negar para a checagem de posse."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return jsonify({"success": False, "error": "Acesso negado"}), 403

    data = request.get_json(silent=True) or {}
    versao_id = data.get('versao_id')
    treino_codigo = data.get('treino_codigo')
    nova_ordem = data.get('nova_ordem')

    if not versao_id or not treino_codigo or not nova_ordem:
        return jsonify({"success": False, "error": "Dados incompletos"}), 400

    sucesso = ExercicioService.reordenar_exercicios(
        versao_id=versao_id,
        treino_codigo=treino_codigo,
        nova_ordem_ids=nova_ordem,
        user_id=aluno.id,
    )

    if sucesso:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Erro ao reordenar"}), 500


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/editar', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("30 per hour", key_func=_chave_por_professor)
def versao_editar_descricao_aluno(aluno_id, versao_id):
    """Edita a descrição de uma versão do aluno -- só permitido se ainda estiver ativa."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    descricao = request.form.get('descricao', '')
    try:
        VersaoService.editar_descricao_livre(
            versao_id, descricao, user_id=aluno.id, permitir_finalizada=False
        )
        flash('Versão atualizada!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao editar versão do aluno (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("60 per hour", key_func=_chave_por_professor)
def versao_adicionar_treino_aluno(aluno_id, versao_id):
    """Adiciona um treino a uma versão do aluno -- só permitido se ainda estiver ativa."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    nome_treino = request.form.get('nome_treino', '')
    descricao_treino = request.form.get('descricao_treino', '')
    try:
        VersaoService.adicionar_treino_livre(
            versao_id, nome_treino, descricao_treino,
            user_id=aluno.id, permitir_finalizada=False
        )
        flash('Treino adicionado! Agora selecione os exercícios.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao adicionar treino do aluno (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<int:treino_versao_id>', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("120 per hour", key_func=_chave_por_professor)
def versao_salvar_treino_aluno(aluno_id, versao_id, treino_versao_id):
    """Salva nome/descrição/exercícios de um treino do aluno -- só permitido se a versão ainda estiver ativa."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

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
            exercicios_raw, user_id=aluno.id, observacoes=observacoes,
            permitir_finalizada=False
        )
        flash('Treino salvo com sucesso!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao salvar treino do aluno (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/treino/<int:treino_versao_id>/remover', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("60 per hour", key_func=_chave_por_professor)
def versao_remover_treino_aluno(aluno_id, versao_id, treino_versao_id):
    """Remove um treino de uma versão do aluno -- só permitido se ainda estiver ativa
    (e bloqueado pelo service se já houver histórico de registro para esse treino)."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    try:
        VersaoService.remover_treino_livre(
            versao_id, treino_versao_id, user_id=aluno.id, permitir_finalizada=False
        )
        flash('Treino removido da versão.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao remover treino do aluno (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/finalizar', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("10 per hour", key_func=_chave_por_professor)
def versao_finalizar_aluno(aluno_id, versao_id):
    """Finaliza a versão ativa do aluno."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    try:
        versao = VersaoService.finalizar_livre(versao_id, user_id=aluno.id)
        flash(f'Versão {versao.numero_versao} finalizada!', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao finalizar versão do aluno (histórico)")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/clonar', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("10 per hour", key_func=_chave_por_professor)
def versao_clonar_aluno(aluno_id, versao_id):
    """Cria uma nova versão ativa para o aluno copiando a estrutura desta versão."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    try:
        nova_versao = VersaoService.clonar_versao(versao_id, user_id=aluno.id)
        flash(f'Versão clonada como v{nova_versao.numero_versao}!', 'success')
        return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=nova_versao.id))
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao clonar versão do aluno")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))


@professor_bp.route('/aluno/<int:aluno_id>/versao/<int:versao_id>/excluir', methods=['POST'])
@login_required
@professor_acesso_alunos_required
@limiter.limit("10 per hour", key_func=_chave_por_professor)
def versao_excluir_aluno(aluno_id, versao_id):
    """Exclui uma versão finalizada do aluno sem histórico de registro."""
    aluno, negado = _aluno_ou_negar(aluno_id)
    if negado:
        return negado

    try:
        VersaoService.excluir_versao(versao_id, user_id=aluno.id)
        flash('Versão excluída com sucesso!', 'success')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception:
        logger.exception("Erro inesperado ao excluir versão do aluno")
        flash('Não foi possível concluir a operação.', 'danger')
    return redirect(url_for('professor.ver_versao_aluno', aluno_id=aluno.id, versao_id=versao_id))