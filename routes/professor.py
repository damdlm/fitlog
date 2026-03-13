# /routes/professor.py
from flask import render_template, flash, redirect, url_for, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.treino import Treino
from app.models.exercicio import Exercicio
from app.models.registro import Registro
from app.models.versao import Versao
from app.models.vinculo import Vinculo
from app.utils.decorators import professor_pode_ver_aluno, admin_required
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@professor_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard do professor"""
    if not current_user.is_professor:
        flash('Acesso restrito a professores.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Buscar alunos vinculados com dados otimizados
    vinculos = Vinculo.query.filter_by(
        professor_id=current_user.id, 
        ativo=True
    ).options(
        db.joinedload(Vinculo.aluno)
    ).all()
    
    alunos = [v.aluno for v in vinculos]
    
    # Estatísticas
    total_alunos = len(alunos)
    total_treinos = Treino.query.filter(Treino.aluno_id.in_([a.id for a in alunos])).count()
    total_registros = Registro.query.filter(Registro.aluno_id.in_([a.id for a in alunos])).count()
    
    return render_template('professor/dashboard.html',
                         alunos=alunos,
                         total_alunos=total_alunos,
                         total_treinos=total_treinos,
                         total_registros=total_registros)


@professor_bp.route('/alunos')
@login_required
def listar_alunos():
    """Lista todos os alunos do professor"""
    if not current_user.is_professor:
        flash('Acesso restrito a professores.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Filtros
    busca = request.args.get('busca', '')
    status = request.args.get('status', 'ativos')
    
    # Query base
    query = Vinculo.query.filter_by(professor_id=current_user.id)
    
    # Filtrar por status
    if status == 'ativos':
        query = query.filter_by(ativo=True)
    elif status == 'inativos':
        query = query.filter_by(ativo=False)
    
    # Busca por nome/email
    if busca:
        query = query.join(User, Vinculo.aluno_id == User.id).filter(
            db.or_(
                User.nome_completo.ilike(f'%{busca}%'),
                User.username.ilike(f'%{busca}%'),
                User.email.ilike(f'%{busca}%')
            )
        )
    
    vinculos = query.options(db.joinedload(Vinculo.aluno)).all()
    alunos = [v.aluno for v in vinculos]
    
    return render_template('professor/alunos.html',
                         alunos=alunos,
                         busca=busca,
                         status=status)


@professor_bp.route('/aluno/<int:aluno_id>')
@login_required
@professor_pode_ver_aluno  # <-- ADICIONADO
def visualizar_aluno(aluno_id, aluno=None):  # <-- aluno vem do decorador
    """Visualizar detalhes do aluno"""
    # O decorador já carregou o aluno e verificou permissão
    # Buscar dados adicionais
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    exercicios = Exercicio.query.filter_by(aluno_id=aluno.id).all()
    registros = Registro.query.filter_by(aluno_id=aluno.id).count()
    
    # Últimos 10 registros
    ultimos_registros = Registro.query.filter_by(aluno_id=aluno.id)\
        .order_by(Registro.data_registro.desc())\
        .limit(10)\
        .all()
    
    # Versão ativa
    versao_ativa = Versao.query.filter_by(
        aluno_id=aluno.id, 
        data_fim=None
    ).first()
    
    return render_template('professor/visualizar_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         exercicios=exercicios,
                         registros=registros,
                         ultimos_registros=ultimos_registros,
                         versao_ativa=versao_ativa)


@professor_bp.route('/aluno/<int:aluno_id>/editar', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def editar_aluno(aluno_id, aluno=None):
    """Editar dados do aluno"""
    if request.method == 'POST':
        # Validar CSRF (já feito pelo WTForms)
        aluno.nome_completo = request.form.get('nome_completo', '').strip()
        aluno.email = request.form.get('email', '').strip()
        aluno.telefone = request.form.get('telefone', '').strip()
        
        # Alterar senha se fornecida
        nova_senha = request.form.get('nova_senha')
        if nova_senha and len(nova_senha) >= 6:
            aluno.set_password(nova_senha)
            flash('Senha alterada com sucesso!', 'success')
        
        db.session.commit()
        flash('Dados do aluno atualizados com sucesso!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    return render_template('professor/editar_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/desativar')
@login_required
@professor_pode_ver_aluno
def desativar_aluno(aluno_id, aluno=None):
    """Desativar aluno (manter vínculo mas bloquear acesso)"""
    aluno.ativo = False
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} desativou aluno {aluno_id}")
    flash('Aluno desativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/<int:aluno_id>/reativar')
@login_required
@professor_pode_ver_aluno
def reativar_aluno(aluno_id, aluno=None):
    """Reativar aluno"""
    aluno.ativo = True
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} reativou aluno {aluno_id}")
    flash('Aluno reativado com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


@professor_bp.route('/aluno/<int:aluno_id>/remover-vinculo')
@login_required
@professor_pode_ver_aluno
def remover_vinculo(aluno_id, aluno=None):
    """Remover vínculo com aluno (não exclui o aluno)"""
    vinculo = Vinculo.query.filter_by(
        professor_id=current_user.id,
        aluno_id=aluno_id,
        ativo=True
    ).first_or_404()
    
    vinculo.ativo = False
    vinculo.data_encerramento = datetime.utcnow()
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} removeu vínculo com aluno {aluno_id}")
    flash('Vínculo removido com sucesso!', 'success')
    return redirect(url_for('professor.listar_alunos'))


# =============================================
# ROTAS DE TREINOS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/treinos')
@login_required
@professor_pode_ver_aluno
def treinos_aluno(aluno_id, aluno=None):
    """Listar treinos do aluno"""
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    
    # Agrupar exercícios por treino
    exercicios_por_treino = {}
    for treino in treinos:
        exercicios_por_treino[treino.id] = Exercicio.query.filter_by(
            aluno_id=aluno.id,
            treino_id=treino.id
        ).all()
    
    return render_template('professor/treinos_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         exercicios_por_treino=exercicios_por_treino)


@professor_bp.route('/aluno/<int:aluno_id>/treinos/novo', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def novo_treino_aluno(aluno_id, aluno=None):
    """Criar novo treino para o aluno"""
    if request.method == 'POST':
        codigo = request.form.get('id', '').upper().strip()
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        
        # Validar
        if not codigo or len(codigo) != 1 or not codigo.isalpha():
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(request.url)
        
        # Verificar se já existe
        existente = Treino.query.filter_by(
            aluno_id=aluno.id,
            codigo=codigo
        ).first()
        
        if existente:
            flash(f'Já existe um treino com código {codigo} para este aluno!', 'danger')
            return redirect(request.url)
        
        treino = Treino(
            aluno_id=aluno.id,
            codigo=codigo,
            nome=nome,
            descricao=descricao
        )
        db.session.add(treino)
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} criou treino {codigo} para aluno {aluno_id}")
        flash('Treino criado com sucesso!', 'success')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    return render_template('professor/novo_treino_aluno.html', aluno=aluno)


@professor_bp.route('/aluno/<int:aluno_id>/treinos/<int:treino_id>/editar', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def editar_treino_aluno(aluno_id, treino_id, aluno=None):
    """Editar treino do aluno"""
    treino = Treino.query.filter_by(id=treino_id, aluno_id=aluno.id).first_or_404()
    
    if request.method == 'POST':
        novo_codigo = request.form.get('id', '').upper().strip()
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        
        # Validar
        if not novo_codigo or len(novo_codigo) != 1 or not novo_codigo.isalpha():
            flash('ID do treino deve ser uma única letra!', 'danger')
            return redirect(request.url)
        
        # Verificar se código já existe (se mudou)
        if novo_codigo != treino.codigo:
            existente = Treino.query.filter_by(
                aluno_id=aluno.id,
                codigo=novo_codigo
            ).first()
            
            if existente:
                flash(f'Já existe um treino com código {novo_codigo} para este aluno!', 'danger')
                return redirect(request.url)
        
        treino.codigo = novo_codigo
        treino.nome = nome
        treino.descricao = descricao
        db.session.commit()
        
        flash('Treino atualizado com sucesso!', 'success')
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    return render_template('professor/editar_treino_aluno.html',
                         aluno=aluno,
                         treino=treino)


@professor_bp.route('/aluno/<int:aluno_id>/treinos/<int:treino_id>/excluir')
@login_required
@professor_pode_ver_aluno
def excluir_treino_aluno(aluno_id, treino_id, aluno=None):
    """Excluir treino do aluno"""
    confirmar = request.args.get('confirmar', 'false').lower() == 'true'
    
    if not confirmar:
        return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))
    
    treino = Treino.query.filter_by(id=treino_id, aluno_id=aluno.id).first_or_404()
    
    # Excluir exercícios associados
    Exercicio.query.filter_by(treino_id=treino.id, aluno_id=aluno.id).delete()
    
    db.session.delete(treino)
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} excluiu treino {treino_id} do aluno {aluno_id}")
    flash('Treino excluído com sucesso!', 'success')
    return redirect(url_for('professor.treinos_aluno', aluno_id=aluno.id))


# =============================================
# ROTAS DE EXERCÍCIOS DO ALUNO
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/exercicios')
@login_required
@professor_pode_ver_aluno
def exercicios_aluno(aluno_id, aluno=None):
    """Listar exercícios do aluno"""
    exercicios = Exercicio.query.filter_by(aluno_id=aluno.id).all()
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    
    # Últimas cargas
    ultimas_cargas = {}
    for ex in exercicios:
        ultimo_registro = Registro.query.filter_by(
            aluno_id=aluno.id,
            exercicio_id=ex.id
        ).order_by(Registro.data_registro.desc()).first()
        
        if ultimo_registro and ultimo_registro.series:
            ultimas_cargas[ex.id] = ultimo_registro.series[0].carga
    
    return render_template('professor/exercicios_aluno.html',
                         aluno=aluno,
                         exercicios=exercicios,
                         treinos=treinos,
                         ultimas_cargas=ultimas_cargas)


@professor_bp.route('/aluno/<int:aluno_id>/exercicios/novo', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def novo_exercicio_aluno(aluno_id, aluno=None):
    """Criar novo exercício para o aluno"""
    from app.models.musculo import Musculo
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        musculo_nome = request.form.get('musculo', '').strip()
        treino_id = request.form.get('treino')
        descricao = request.form.get('descricao', '').strip()
        
        # Validar
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(request.url)
        
        # Buscar ou criar músculo
        musculo = Musculo.query.filter_by(nome_exibicao=musculo_nome).first()
        if not musculo:
            # Criar novo músculo
            musculo = Musculo(
                nome=musculo_nome.lower().replace(' ', '_'),
                nome_exibicao=musculo_nome
            )
            db.session.add(musculo)
            db.session.flush()
        
        exercicio = Exercicio(
            aluno_id=aluno.id,
            nome=nome,
            musculo_id=musculo.id,
            descricao=descricao
        )
        
        if treino_id and treino_id.isdigit():
            # Verificar se treino pertence ao aluno
            treino = Treino.query.filter_by(id=int(treino_id), aluno_id=aluno.id).first()
            if treino:
                exercicio.treino_id = treino.id
        
        db.session.add(exercicio)
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} criou exercício {exercicio.id} para aluno {aluno_id}")
        flash('Exercício criado com sucesso!', 'success')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    musculos = Musculo.query.order_by(Musculo.nome_exibicao).all()
    musculos_list = [m.nome_exibicao for m in musculos]
    
    return render_template('professor/novo_exercicio_aluno.html',
                         aluno=aluno,
                         treinos=treinos,
                         musculos=musculos_list)


@professor_bp.route('/aluno/<int:aluno_id>/exercicios/<int:exercicio_id>/editar', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def editar_exercicio_aluno(aluno_id, exercicio_id, aluno=None):
    """Editar exercício do aluno"""
    from app.models.musculo import Musculo
    
    exercicio = Exercicio.query.filter_by(
        id=exercicio_id, 
        aluno_id=aluno.id
    ).first_or_404()
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        musculo_nome = request.form.get('musculo', '').strip()
        treino_id = request.form.get('treino')
        descricao = request.form.get('descricao', '').strip()
        
        # Validar
        if not nome:
            flash('Nome do exercício é obrigatório!', 'danger')
            return redirect(request.url)
        
        # Buscar ou criar músculo
        musculo = Musculo.query.filter_by(nome_exibicao=musculo_nome).first()
        if not musculo:
            musculo = Musculo(
                nome=musculo_nome.lower().replace(' ', '_'),
                nome_exibicao=musculo_nome
            )
            db.session.add(musculo)
            db.session.flush()
        
        exercicio.nome = nome
        exercicio.musculo_id = musculo.id
        exercicio.descricao = descricao
        
        # Atualizar treino
        if treino_id and treino_id.isdigit():
            treino = Treino.query.filter_by(id=int(treino_id), aluno_id=aluno.id).first()
            exercicio.treino_id = treino.id if treino else None
        else:
            exercicio.treino_id = None
        
        db.session.commit()
        
        flash('Exercício atualizado com sucesso!', 'success')
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    musculos = Musculo.query.order_by(Musculo.nome_exibicao).all()
    musculos_list = [m.nome_exibicao for m in musculos]
    
    return render_template('professor/editar_exercicio_aluno.html',
                         aluno=aluno,
                         exercicio=exercicio,
                         treinos=treinos,
                         musculos=musculos_list)


@professor_bp.route('/aluno/<int:aluno_id>/exercicios/<int:exercicio_id>/excluir')
@login_required
@professor_pode_ver_aluno
def excluir_exercicio_aluno(aluno_id, exercicio_id, aluno=None):
    """Excluir exercício do aluno"""
    confirmar = request.args.get('confirmar', 'false').lower() == 'true'
    
    if not confirmar:
        return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))
    
    exercicio = Exercicio.query.filter_by(
        id=exercicio_id, 
        aluno_id=aluno.id
    ).first_or_404()
    
    # Excluir registros associados
    Registro.query.filter_by(exercicio_id=exercicio.id).delete()
    
    db.session.delete(exercicio)
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} excluiu exercício {exercicio_id} do aluno {aluno_id}")
    flash('Exercício excluído com sucesso!', 'success')
    return redirect(url_for('professor.exercicios_aluno', aluno_id=aluno.id))


# =============================================
# ROTAS DE ESTATÍSTICAS
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/estatisticas')
@login_required
@professor_pode_ver_aluno
def estatisticas_aluno(aluno_id, aluno=None):
    """Estatísticas detalhadas do aluno"""
    from collections import defaultdict
    
    # Buscar todos os registros do aluno
    registros = Registro.query.filter_by(aluno_id=aluno.id)\
        .options(
            db.joinedload(Registro.exercicio_ref)
            .joinedload(Exercicio.musculo_ref)
        ).all()
    
    # Estatísticas por músculo
    musculo_stats = defaultdict(lambda: {
        'volume_total': 0,
        'qtd_exercicios': 0,
        'qtd_registros': 0
    })
    
    exercicios_unicos = set()
    
    for registro in registros:
        if not registro.exercicio_ref or not registro.exercicio_ref.musculo_ref:
            continue
            
        musculo = registro.exercicio_ref.musculo_ref.nome_exibicao
        exercicio_id = registro.exercicio_id
        
        # Calcular volume do registro
        volume = sum(s.carga * s.repeticoes for s in registro.series) if registro.series else 0
        
        musculo_stats[musculo]['volume_total'] += volume
        musculo_stats[musculo]['qtd_registros'] += 1
        
        if exercicio_id not in exercicios_unicos:
            exercicios_unicos.add(exercicio_id)
            musculo_stats[musculo]['qtd_exercicios'] += 1
    
    # Estatísticas por treino
    treino_stats = {}
    treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    
    for treino in treinos:
        exercicios_treino = Exercicio.query.filter_by(
            aluno_id=aluno.id,
            treino_id=treino.id
        ).all()
        
        registros_treino = Registro.query.filter(
            Registro.aluno_id == aluno.id,
            Registro.exercicio_id.in_([e.id for e in exercicios_treino])
        ).all()
        
        volume_total = 0
        for reg in registros_treino:
            volume_total += sum(s.carga * s.repeticoes for s in reg.series) if reg.series else 0
        
        treino_stats[treino.id] = {
            'codigo': treino.codigo,
            'nome': treino.nome,
            'qtd_exercicios': len(exercicios_treino),
            'qtd_registros': len(registros_treino),
            'volume_total': volume_total
        }
    
    return render_template('professor/estatisticas_aluno.html',
                         aluno=aluno,
                         musculo_stats=dict(musculo_stats),
                         treino_stats=treino_stats)


# =============================================
# ROTAS DE VERSÕES
# =============================================

@professor_bp.route('/aluno/<int:aluno_id>/versoes')
@login_required
@professor_pode_ver_aluno
def versoes_aluno(aluno_id, aluno=None):
    """Listar versões de treino do aluno"""
    versoes = Versao.query.filter_by(aluno_id=aluno.id)\
        .order_by(Versao.numero_versao.desc())\
        .all()
    
    return render_template('professor/versoes_aluno.html',
                         aluno=aluno,
                         versoes=versoes)


@professor_bp.route('/aluno/<int:aluno_id>/versoes/nova', methods=['GET', 'POST'])
@login_required
@professor_pode_ver_aluno
def nova_versao_aluno(aluno_id, aluno=None):
    """Criar nova versão de treino"""
    if request.method == 'POST':
        descricao = request.form.get('descricao', '').strip()
        divisao = request.form.get('divisao', 'ABC')
        data_inicio = datetime.strptime(request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim = request.form.get('data_fim')
        
        if data_fim:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        else:
            data_fim = None
        
        # Calcular próximo número de versão
        ultima_versao = Versao.query.filter_by(aluno_id=aluno.id)\
            .order_by(Versao.numero_versao.desc())\
            .first()
        
        if ultima_versao:
            # Finalizar versão atual
            if ultima_versao.data_fim is None:
                ultima_versao.data_fim = data_inicio
                db.session.add(ultima_versao)
            
            novo_numero = ultima_versao.numero_versao + 1
        else:
            novo_numero = 1
        
        versao = Versao(
            aluno_id=aluno.id,
            numero_versao=novo_numero,
            descricao=descricao,
            divisao=divisao,
            data_inicio=data_inicio,
            data_fim=data_fim
        )
        
        db.session.add(versao)
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} criou versão {novo_numero} para aluno {aluno_id}")
        flash('Versão criada com sucesso!', 'success')
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    # Data atual para o campo data_inicio
    from datetime import date
    data_atual = date.today().isoformat()
    
    return render_template('professor/nova_versao_aluno.html',
                         aluno=aluno,
                         data_atual_iso=lambda: data_atual)


@professor_bp.route('/aluno/<int:aluno_id>/versoes/<int:versao_id>')
@login_required
@professor_pode_ver_aluno
def ver_versao_aluno(aluno_id, versao_id, aluno=None):
    """Visualizar/editar versão específica"""
    versao = Versao.query.filter_by(id=versao_id, aluno_id=aluno.id).first_or_404()
    
    # Organizar treinos da versão
    treinos_versao = {}
    for tv in versao.treinos:
        treino = Treino.query.get(tv.treino_id)
        if treino:
            treinos_versao[treino.codigo] = {
                'id': treino.id,
                'nome': tv.nome_treino,
                'descricao': tv.descricao,
                'exercicios': [ve.exercicio_id for ve in tv.exercicios]
            }
    
    # Lista de todos exercícios do aluno
    exercicios = Exercicio.query.filter_by(aluno_id=aluno.id)\
        .options(db.joinedload(Exercicio.musculo_ref)).all()
    
    # Treinos disponíveis (não usados na versão)
    todos_treinos = Treino.query.filter_by(aluno_id=aluno.id).all()
    treinos_usados = [tv.treino_id for tv in versao.treinos]
    treinos_disponiveis = [t for t in todos_treinos if t.id not in treinos_usados]
    
    return render_template('professor/ver_versao_aluno.html',
                         aluno=aluno,
                         versao=versao,
                         treinos=treinos_versao,
                         exercicios=exercicios,
                         treinos_disponiveis=treinos_disponiveis)


@professor_bp.route('/aluno/<int:aluno_id>/versoes/<int:versao_id>/editar', methods=['POST'])
@login_required
@professor_pode_ver_aluno
def editar_versao_aluno(aluno_id, versao_id, aluno=None):
    """Editar dados da versão"""
    versao = Versao.query.filter_by(id=versao_id, aluno_id=aluno.id).first_or_404()
    
    versao.descricao = request.form.get('descricao', '').strip()
    versao.divisao = request.form.get('divisao', 'ABC')
    
    data_inicio = request.form.get('data_inicio')
    if data_inicio:
        versao.data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
    
    data_fim = request.form.get('data_fim')
    if data_fim:
        versao.data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
    else:
        versao.data_fim = None
    
    db.session.commit()
    
    flash('Versão atualizada com sucesso!', 'success')
    return redirect(url_for('professor.ver_versao_aluno', 
                         aluno_id=aluno.id, 
                         versao_id=versao.id))


@professor_bp.route('/aluno/<int:aluno_id>/versoes/<int:versao_id>/finalizar')
@login_required
@professor_pode_ver_aluno
def finalizar_versao_aluno(aluno_id, versao_id, aluno=None):
    """Finalizar versão (definir data_fim = hoje)"""
    versao = Versao.query.filter_by(id=versao_id, aluno_id=aluno.id).first_or_404()
    
    from datetime import date
    versao.data_fim = date.today()
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} finalizou versão {versao_id} do aluno {aluno_id}")
    flash('Versão finalizada com sucesso!', 'success')
    return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))


@professor_bp.route('/aluno/<int:aluno_id>/versoes/<int:versao_id>/clonar')
@login_required
@professor_pode_ver_aluno
def clonar_versao_aluno(aluno_id, versao_id, aluno=None):
    """Criar nova versão baseada em uma existente"""
    versao_original = Versao.query.filter_by(id=versao_id, aluno_id=aluno.id).first_or_404()
    
    # Criar nova versão
    from datetime import date
    
    nova_versao = Versao(
        aluno_id=aluno.id,
        numero_versao=versao_original.numero_versao + 1,
        descricao=f"Clonada de v{versao_original.numero_versao}: {versao_original.descricao}",
        divisao=versao_original.divisao,
        data_inicio=date.today(),
        data_fim=None
    )
    
    db.session.add(nova_versao)
    db.session.flush()
    
    # Clonar treinos
    for tv in versao_original.treinos:
        novo_tv = TreinoVersao(
            versao_id=nova_versao.id,
            treino_id=tv.treino_id,
            nome_treino=tv.nome_treino,
            descricao=tv.descricao
        )
        db.session.add(novo_tv)
        db.session.flush()
        
        # Clonar exercícios
        for ve in tv.exercicios:
            novo_ve = VersaoExercicio(
                treino_versao_id=novo_tv.id,
                exercicio_id=ve.exercicio_id,
                ordem=ve.ordem
            )
            db.session.add(novo_ve)
    
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} clonou versão {versao_id} para nova versão {nova_versao.id}")
    flash('Versão clonada com sucesso!', 'success')
    return redirect(url_for('professor.ver_versao_aluno', 
                         aluno_id=aluno.id, 
                         versao_id=nova_versao.id))


@professor_bp.route('/aluno/<int:aluno_id>/versoes/<int:versao_id>/excluir')
@login_required
@professor_pode_ver_aluno
def excluir_versao_aluno(aluno_id, versao_id, aluno=None):
    """Excluir versão"""
    confirmar = request.args.get('confirmar', 'false').lower() == 'true'
    
    if not confirmar:
        return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))
    
    versao = Versao.query.filter_by(id=versao_id, aluno_id=aluno.id).first_or_404()
    
    # Excluir registros relacionados
    db.session.delete(versao)
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} excluiu versão {versao_id} do aluno {aluno_id}")
    flash('Versão excluída com sucesso!', 'success')
    return redirect(url_for('professor.versoes_aluno', aluno_id=aluno.id))


# =============================================
# ROTAS DE SOLICITAÇÕES
# =============================================

@professor_bp.route('/solicitacoes')
@login_required
def solicitacoes():
    """Listar solicitações de vínculo pendentes"""
    if not current_user.is_professor:
        flash('Acesso restrito a professores.', 'danger')
        return redirect(url_for('auth.login'))
    
    solicitacoes = Vinculo.query.filter_by(
        professor_id=current_user.id,
        ativo=False,
        data_aprovacao=None
    ).options(
        db.joinedload(Vinculo.aluno)
    ).all()
    
    return render_template('professor/solicitacoes.html', 
                         solicitacoes=solicitacoes)


@professor_bp.route('/solicitacoes/<int:solicitacao_id>/aprovar')
@login_required
def aprovar_solicitacao(solicitacao_id):
    """Aprovar solicitação de vínculo"""
    solicitacao = Vinculo.query.get_or_404(solicitacao_id)
    
    # Verificar se a solicitação é para este professor
    if solicitacao.professor_id != current_user.id:
        flash('Esta solicitação não pertence a você.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    solicitacao.aprovar()
    
    logger.info(f"Professor {current_user.id} aprovou solicitação {solicitacao_id}")
    flash('Solicitação aprovada! Aluno vinculado com sucesso.', 'success')
    return redirect(url_for('professor.solicitacoes'))


@professor_bp.route('/solicitacoes/<int:solicitacao_id>/recusar')
@login_required
def recusar_solicitacao(solicitacao_id):
    """Recusar solicitação de vínculo"""
    solicitacao = Vinculo.query.get_or_404(solicitacao_id)
    
    if solicitacao.professor_id != current_user.id:
        flash('Esta solicitação não pertence a você.', 'danger')
        return redirect(url_for('professor.dashboard'))
    
    db.session.delete(solicitacao)
    db.session.commit()
    
    logger.info(f"Professor {current_user.id} recusou solicitação {solicitacao_id}")
    flash('Solicitação recusada.', 'success')
    return redirect(url_for('professor.solicitacoes'))


# =============================================
# ROTAS DE NOVO ALUNO
# =============================================

@professor_bp.route('/aluno/novo', methods=['GET', 'POST'])
@login_required
def novo_aluno():
    """Criar novo aluno e vincular automaticamente"""
    if not current_user.is_professor:
        flash('Acesso restrito a professores.', 'danger')
        return redirect(url_for('auth.login'))
    
    from app.models.musculo import Musculo
    from werkzeug.security import generate_password_hash
    
    if request.method == 'POST':
        # Validar dados
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        nome_completo = request.form.get('nome_completo', '').strip()
        telefone = request.form.get('telefone', '').strip()
        
        # Validações
        if not username or len(username) < 3:
            flash('Usuário deve ter pelo menos 3 caracteres.', 'danger')
            return redirect(request.url)
        
        if not email or '@' not in email:
            flash('E-mail inválido.', 'danger')
            return redirect(request.url)
        
        if not password or len(password) < 6:
            flash('Senha deve ter pelo menos 6 caracteres.', 'danger')
            return redirect(request.url)
        
        # Verificar se já existe
        if User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe.', 'danger')
            return redirect(request.url)
        
        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
            return redirect(request.url)
        
        # Criar aluno
        aluno = User(
            username=username,
            email=email,
            nome_completo=nome_completo,
            telefone=telefone,
            is_professor=False,
            is_admin=False,
            ativo=True
        )
        aluno.set_password(password)
        
        db.session.add(aluno)
        db.session.flush()
        
        # Criar vínculo
        vinculo = Vinculo(
            professor_id=current_user.id,
            aluno_id=aluno.id,
            ativo=True,
            data_aprovacao=datetime.utcnow()
        )
        db.session.add(vinculo)
        
        # Criar treinos padrão (A, B, C)
        treinos_padrao = [
            {'codigo': 'A', 'nome': 'Treino A', 'descricao': 'Peitoral e Tríceps'},
            {'codigo': 'B', 'nome': 'Treino B', 'descricao': 'Costas e Bíceps'},
            {'codigo': 'C', 'nome': 'Treino C', 'descricao': 'Pernas e Ombros'}
        ]
        
        for t in treinos_padrao:
            treino = Treino(
                aluno_id=aluno.id,
                codigo=t['codigo'],
                nome=t['nome'],
                descricao=t['descricao']
            )
            db.session.add(treino)
        
        db.session.commit()
        
        logger.info(f"Professor {current_user.id} criou novo aluno {aluno.id}")
        flash('Aluno criado com sucesso!', 'success')
        return redirect(url_for('professor.visualizar_aluno', aluno_id=aluno.id))
    
    return render_template('professor/novo_aluno.html')