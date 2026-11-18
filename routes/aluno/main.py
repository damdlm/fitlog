from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from . import aluno_bp
from models import db, User, AlunoProfessor, SolicitacaoVinculo, TreinoVersao, VersaoGlobal, ExercicioCustomizado, RegistroTreino
from utils.decorators import acesso_premium_required
from services.avaliacao_professor_service import AvaliacaoProfessorService
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from services.onboarding_service import passos_comece_por_aqui
from utils.format_utils import formatar_kg
from zoneinfo import ZoneInfo
import logging
import re

logger = logging.getLogger(__name__)

def _resumo_series(series):
    """ "32,5 kg × 8–10 · 3 séries" (mesma leitura do selo "Última" do
    registro); peso corporal/sem carga mostra só as repetições."""
    if not series:
        return ''
    if series[0].eh_cardio:
        return series[0].resumo_cardio
    cargas = [s.carga for s in series if s.carga is not None and s.carga > 0]
    reps = [s.repeticoes for s in series if s.repeticoes is not None]
    faixa = ''
    if reps:
        faixa = str(min(reps)) if min(reps) == max(reps) else f'{min(reps)}–{max(reps)}'
    if len(set(cargas)) == 1:
        texto = formatar_kg(cargas[0]) + (f' × {faixa}' if faixa else '')
    elif cargas:
        texto = f'até {formatar_kg(max(cargas))}'
    else:
        texto = f'{faixa} reps' if faixa else ''
    n = len(series)
    return (texto + ' · ' if texto else '') + f'{n} série' + ('s' if n != 1 else '')


def _nome_sem_codigo(nome, codigo):
    """ "Treino C - Braços" -> "Braços" quando o código já aparece ao lado
    ("Treino C · Braços"); nome igual a "Treino C" -> "" (nada a repetir)."""
    nome = (nome or '').strip()
    if codigo:
        m = re.match(r'^treino\s+' + re.escape(codigo) + r'\b\s*[-–—:·.]?\s*', nome, re.I)
        if m:
            nome = nome[m.end():].strip()
    return nome


def _ultimas_sessoes(user_id, limite=3):
    """As `limite` sessões mais recentes (dia + treino), cada uma com os
    exercícios, o volume (carga × repetições) e o tempo do cronômetro."""
    dia = func.date(RegistroTreino.data_registro)
    chaves = db.session.query(
        dia.label('dia'), RegistroTreino.treino_versao_id, func.max(RegistroTreino.created_at)
    ).filter(
        RegistroTreino.user_id == user_id
    ).group_by(
        dia, RegistroTreino.treino_versao_id
    ).order_by(
        dia.desc(), func.max(RegistroTreino.created_at).desc().nullslast()
    ).limit(limite).all()
    if not chaves:
        return []

    def _como_data(valor):
        return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])

    ordem = [(_como_data(d), tv) for d, tv, _ in chaves]
    inicio = min(d for d, _ in ordem)
    fim = max(d for d, _ in ordem) + timedelta(days=1)
    registros = RegistroTreino.query.options(
        selectinload(RegistroTreino.series),
        selectinload(RegistroTreino.exercicio),
        selectinload(RegistroTreino.exercicio_base),
        selectinload(RegistroTreino.treino_ref),
    ).filter(
        RegistroTreino.user_id == user_id,
        RegistroTreino.treino_versao_id.in_({tv for _, tv in ordem}),
        RegistroTreino.data_registro >= datetime.combine(inicio, datetime.min.time()),
        RegistroTreino.data_registro < datetime.combine(fim, datetime.min.time()),
    ).order_by(RegistroTreino.created_at.asc().nullsfirst(), RegistroTreino.id.asc()).all()

    por_sessao = {}
    for r in registros:
        por_sessao.setdefault((r.data_registro.date(), r.treino_versao_id), []).append(r)

    sessoes = []
    for chave in ordem:
        regs = por_sessao.get(chave, [])
        if not regs:
            continue
        treino = regs[0].treino_ref
        volume = 0.0
        tempo = None
        exercicios = []
        for r in regs:
            series = sorted(r.series or [], key=lambda s: (s.ordem or 0))
            for s in series:
                if not s.eh_cardio and s.carga and s.repeticoes:
                    volume += float(s.carga) * s.repeticoes
                if s.tempo_treino and (tempo is None or s.tempo_treino > tempo):
                    tempo = s.tempo_treino
            ex = r.exercicio or r.exercicio_base
            exercicios.append({'nome': ex.nome if ex else 'Exercício', 'resumo': _resumo_series(series)})
        sessoes.append({
            'data': chave[0],
            'codigo': treino.codigo if treino else '',
            'nome': _nome_sem_codigo(treino.nome_treino if treino else '', treino.codigo if treino else ''),
            'exercicios': exercicios,
            'volume': volume,
            'tempo': f"{tempo // 3600:02d}:{(tempo % 3600) // 60:02d}" if tempo else None,
        })
    return sessoes


def _proximo_treino(user_id):
    """Treino sugerido para hoje (R1) na ficha ativa, para o botão
    "Registrar próximo treino"; None sem ficha ativa com treinos."""
    from routes.register_routes import _anotar_sugestao_treino
    from services.versao_service import VersaoService
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    versao = VersaoService.get_ativa(user_id=user_id)
    if not versao or versao.data_fim:
        return None
    treinos = _anotar_sugestao_treino(VersaoService.get_treinos_para_registro(versao.id), user_id, hoje)
    escolhido = next((t for t in treinos if t.get('sugerido')), treinos[0] if treinos else None)
    if escolhido:
        escolhido = dict(escolhido, nome_curto=_nome_sem_codigo(escolhido.get('nome'), escolhido.get('codigo')))
    return escolhido


@aluno_bp.route('/dashboard')
@login_required
@acesso_premium_required('dashboard')
def dashboard():
    """Dashboard do aluno (também acessível pelo professor, para seus próprios treinos)"""
    if not current_user.pode_gerenciar_treino_proprio():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    # Estatísticas básicas
    total_treinos = TreinoVersao.query.join(
        VersaoGlobal, TreinoVersao.versao_id == VersaoGlobal.id
    ).filter(VersaoGlobal.user_id == current_user.id).count()
    total_exercicios = ExercicioCustomizado.query.filter_by(usuario_id=current_user.id).count()
    total_versoes = VersaoGlobal.query.filter_by(user_id=current_user.id).count()
    total_registros = RegistroTreino.query.filter_by(user_id=current_user.id).count()
    
    # Últimos treinos (D1): uma sessão = dia + treino (mesma regra da
    # contagem de "Treinos realizados", ver estatistica_service). Antes a
    # sessão era treino + período + semana, e dois dias do mesmo treino na
    # mesma semana viravam uma lista só de exercícios misturados.
    ultimas_sessoes = _ultimas_sessoes(current_user.id, limite=3)
    proximo_treino = _proximo_treino(current_user.id)

    # Atividade dos últimos 7 dias (para o gráfico de constância). Data de
    # São Paulo, como o registro: em UTC, das 21h à meia-noite o gráfico
    # já mostrava o dia seguinte como "hoje".
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    inicio_semana = hoje - timedelta(days=6)
    registros_semana = RegistroTreino.query.filter(
        RegistroTreino.user_id == current_user.id,
        RegistroTreino.data_registro >= inicio_semana
    ).all()
    contagem_por_dia = {}
    # tempo_treino é o cronômetro do topo (duração total da sessão),
    # guardado em cada série (HistoricoTreino) — como pode haver mais
    # de uma sessão no mesmo dia, ficamos com o maior valor do dia.
    tempo_treino_por_dia = {}
    for registro in registros_semana:
        dia = registro.data_registro.date()
        contagem_por_dia[dia] = contagem_por_dia.get(dia, 0) + 1
        if registro.series:
            tempo = registro.series[0].tempo_treino
            if tempo and tempo > tempo_treino_por_dia.get(dia, 0):
                tempo_treino_por_dia[dia] = tempo

    dias_semana_labels = []
    dias_semana_valores = []
    dias_semana_detalhes = []
    nomes_dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
    for i in range(7):
        dia = inicio_semana + timedelta(days=i)
        dias_semana_labels.append(nomes_dias[dia.weekday()])
        dias_semana_valores.append(contagem_por_dia.get(dia, 0))
        tempo_segundos = tempo_treino_por_dia.get(dia, 0)
        dias_semana_detalhes.append({
            'data': dia.strftime('%d/%m'),
            'exercicios': contagem_por_dia.get(dia, 0),
            'tempo_treino': f"{tempo_segundos // 3600:02d}:{(tempo_segundos % 3600) // 60:02d}" if tempo_segundos else None
        })

    dias_treinados_semana = sum(1 for v in dias_semana_valores if v > 0)

    hora_atual = datetime.now(ZoneInfo('America/Sao_Paulo')).hour
    if hora_atual < 12:
        saudacao = 'Bom dia'
    elif hora_atual < 18:
        saudacao = 'Boa tarde'
    else:
        saudacao = 'Boa noite'
    
    return render_template('aluno/dashboard.html',
                         total_treinos=total_treinos,
                         total_exercicios=total_exercicios,
                         total_versoes=total_versoes,
                         total_registros=total_registros,
                         ultimas_sessoes=ultimas_sessoes,
                         proximo_treino=proximo_treino,
                         comece=passos_comece_por_aqui(current_user),
                         dias_semana_labels=dias_semana_labels,
                         dias_semana_valores=dias_semana_valores,
                         dias_semana_detalhes=dias_semana_detalhes,
                         dias_treinados_semana=dias_treinados_semana,
                         saudacao=saudacao)

@aluno_bp.route('/meu-professor')
@login_required
def meu_professor():
    """Visualiza informações do professor vinculado"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    professor = current_user.get_professor()
    resumo_avaliacoes = None
    minha_nota = None
    solicitacoes_enviadas = []
    vinculo = None
    if professor:
        resumo_avaliacoes = AvaliacaoProfessorService.resumo(professor.id)
        minha_nota = AvaliacaoProfessorService.nota_do_aluno(current_user.id, professor.id)
        # current_user.professor_associado é uma lista (backref sem
        # uselist=False em models.py), não o registro único -- por isso
        # a data de vínculo não aparecia no template. Buscando direto:
        vinculo = AlunoProfessor.query.filter_by(
            aluno_id=current_user.id, professor_id=professor.id, ativo=True
        ).first()
    else:
        # Sem professor vinculado: mostra as solicitações que o aluno já
        # enviou (pendentes ou recusadas), pra ele não ter a impressão de
        # que nada aconteceu depois de solicitar vínculo com alguém.
        # 'aprovado' fica de fora -- se existisse um registro aprovado e o
        # aluno está aqui sem professor, é porque o vínculo foi desfeito
        # depois (ver remover_vinculo), e reexibir aquele pedido antigo
        # como se estivesse em aberto só confundiria.
        solicitacoes_enviadas = SolicitacaoVinculo.query.filter(
            SolicitacaoVinculo.aluno_id == current_user.id,
            SolicitacaoVinculo.status.in_(['pendente', 'recusado'])
        ).order_by(SolicitacaoVinculo.data_solicitacao.desc()).all()

    return render_template(
        'aluno/meu_professor.html',
        professor=professor,
        resumo_avaliacoes=resumo_avaliacoes,
        minha_nota=minha_nota,
        vinculo=vinculo,
        solicitacoes_enviadas=solicitacoes_enviadas,
    )

@aluno_bp.route('/avaliar-professor', methods=['POST'])
@login_required
def avaliar_professor():
    """Registra (ou atualiza) a nota de 1-5 estrelas do aluno pro seu
    professor vinculado."""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    professor = current_user.get_professor()
    if not professor:
        flash('Você não está vinculado a nenhum professor.', 'warning')
        return redirect(url_for('aluno.meu_professor'))

    ok, mensagem = AvaliacaoProfessorService.avaliar(current_user, professor.id, request.form.get('nota'))
    flash(mensagem, 'success' if ok else 'danger')
    return redirect(url_for('aluno.meu_professor'))

@aluno_bp.route('/buscar-professores')
@login_required
def buscar_professores():
    """Página para buscar professores disponíveis"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    termo = request.args.get('busca', '')
    professores = []
    if termo:
        professores = User.query.filter(
            User.tipo_usuario == 'professor',
            User.ativo == True,
            (User.nome_completo.ilike(f'%{termo}%') | User.username.ilike(f'%{termo}%'))
        ).all()
    
    return render_template('aluno/buscar_professores.html', 
                         professores=professores,
                         termo=termo)

@aluno_bp.route('/enviar-solicitacao/<int:professor_id>', methods=['POST'])
@login_required
def enviar_solicitacao(professor_id):
    """Envia solicitação de vínculo para um professor"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.get_professor():
        flash('Você já tem um professor vinculado. Para solicitar outro, remova o vínculo atual primeiro.', 'warning')
        return redirect(url_for('aluno.meu_professor'))
    
    professor = User.query.get_or_404(professor_id)
    if professor.tipo_usuario != 'professor':
        flash('Usuário não é um professor válido.', 'danger')
        return redirect(url_for('aluno.buscar_professores'))
    
    solicitacao_existente = SolicitacaoVinculo.query.filter_by(
        aluno_id=current_user.id,
        professor_id=professor_id,
        status='pendente'
    ).first()
    
    if solicitacao_existente:
        flash('Você já possui uma solicitação pendente para este professor.', 'warning')
        return redirect(url_for('aluno.buscar_professores'))
    
    solicitacao = SolicitacaoVinculo(
        aluno_id=current_user.id,
        professor_id=professor_id,
        status='pendente',
        data_solicitacao=datetime.now(timezone.utc)
    )
    db.session.add(solicitacao)
    db.session.commit()

    # Registro de auditoria LGPD: o próprio ato de enviar a solicitação já
    # é a manifestação de vontade do aluno em compartilhar seus dados de
    # treino com este professor específico (ver models.py:ConsentimentoLGPD
    # e services/privacidade_service.py) -- não é a base legal em si (essa
    # é execução de contrato + o vínculo aceito), só evidência adicional.
    from services.privacidade_service import PrivacidadeService, TIPO_COMPARTILHAMENTO_PROFESSOR
    PrivacidadeService.registrar_consentimento(
        current_user.id, TIPO_COMPARTILHAMENTO_PROFESSOR, concedido=True,
        contexto=f"professor_id={professor_id}",
    )

    flash(f'Solicitação enviada para {professor.nome_completo or professor.username}!', 'success')
    return redirect(url_for('aluno.meu_professor'))

@aluno_bp.route('/cancelar-solicitacao/<int:solicitacao_id>', methods=['POST'])
@login_required
def cancelar_solicitacao(solicitacao_id):
    """Cancela uma solicitação de vínculo que o próprio aluno enviou e
    que ainda está pendente (ver tela 'Meu Professor')."""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))

    solicitacao = SolicitacaoVinculo.query.get_or_404(solicitacao_id)

    if solicitacao.aluno_id != current_user.id:
        flash('Você não tem permissão para cancelar esta solicitação.', 'danger')
        return redirect(url_for('aluno.meu_professor'))

    if solicitacao.status != 'pendente':
        flash('Esta solicitação já foi processada e não pode mais ser cancelada.', 'warning')
        return redirect(url_for('aluno.meu_professor'))

    # Mantém o registro (não apaga) para preservar o histórico/auditoria,
    # no mesmo espírito de aprovar/recusar do lado do professor.
    solicitacao.status = 'cancelado'
    solicitacao.data_resposta = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(f"Solicitação {solicitacao_id} cancelada pelo aluno {current_user.id}")
    flash('Solicitação cancelada.', 'info')
    return redirect(url_for('aluno.meu_professor'))

@aluno_bp.route('/remover-vinculo', methods=['POST'])
@login_required
def remover_vinculo():
    """Remove vínculo com o professor atual"""
    if not current_user.is_aluno():
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.index'))
    
    professor = current_user.get_professor()
    if not professor:
        flash('Você não está vinculado a nenhum professor.', 'warning')
        return redirect(url_for('aluno.meu_professor'))
    
    assoc = AlunoProfessor.query.filter_by(aluno_id=current_user.id, ativo=True).first()
    if assoc:
        assoc.ativo = False
        db.session.commit()
        flash(f'Vínculo com {professor.nome_completo or professor.username} removido com sucesso!', 'success')
    
    return redirect(url_for('aluno.meu_professor'))