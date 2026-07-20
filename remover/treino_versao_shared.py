"""
Função compartilhada para edição de treinos em versões.
Usado tanto pelo aluno quanto pelo professor.
"""
from flask import render_template, request, redirect, url_for, flash
from models import db, ExercicioCustomizado, ExercicioBase
from services.versao_service import VersaoService
from services.treino_service import TreinoService
from services.musculo_service import MusculoService
import logging

logger = logging.getLogger(__name__)


def _editar_treino_versao(versao_id, treino_codigo, user_id, template, redirect_after, extra_context):
    """
    Função compartilhada para editar exercícios de um treino na versão.
    
    Args:
        versao_id: ID da versão
        treino_codigo: Código do treino (ex: 'A')
        user_id: ID do usuário dono dos dados (o aluno)
        template: Caminho do template (ex: 'aluno/editar_treino_versao.html')
        redirect_after: Nome da rota para redirecionar após salvar (ex: 'aluno.ver_versao')
        extra_context: Dicionário com dados extras para o template (ex: {'aluno': aluno})
    """
    
    # Buscar versão
    versao = VersaoService.get_by_id(versao_id, user_id=user_id, load_relations=True)
    if not versao:
        flash('Versão não encontrada!', 'danger')
        if extra_context:
            return redirect(url_for(redirect_after, **extra_context))
        return redirect(url_for(redirect_after, versao_id=versao_id))
    
    # Buscar treino pelo código
    treino_ref = TreinoService.get_by_codigo(treino_codigo, user_id=user_id)
    if not treino_ref:
        flash(f'Treino {treino_codigo} não encontrado!', 'danger')
        return redirect(url_for(redirect_after, versao_id=versao_id, **extra_context))
    
    # Encontrar o treino na versão
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino_ref.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        flash(f'Treino {treino_codigo} não encontrado nesta versão!', 'danger')
        return redirect(url_for(redirect_after, versao_id=versao_id, **extra_context))
    
    # ==========================================================
    # MÉTODO POST - SALVAR
    # ==========================================================
    if request.method == 'POST':
        nome_treino = request.form.get('nome_treino', '').strip()
        descricao_treino = request.form.get('descricao_treino', '').strip()
        exercicios_raw = request.form.getlist('exercicios[]')
        
        # Processar exercícios do formulário (separar u_ e b_)
        usuarios_ids, bases_ids = _parse_exercicios_ids(exercicios_raw, user_id)
        
        if not usuarios_ids and not bases_ids:
            flash('Selecione pelo menos um exercício válido!', 'danger')
            return redirect(request.url)
        
        # Atualizar dados básicos do treino
        treino_versao.nome_treino = nome_treino
        treino_versao.descricao_treino = descricao_treino
        
        # Salvar exercícios
        try:
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id,
                usuarios_ids=usuarios_ids,
                bases_ids=bases_ids
            )
            db.session.commit()
            flash(f'Treino {treino_codigo} atualizado com sucesso!', 'success')
            return redirect(url_for(redirect_after, versao_id=versao.id, **extra_context))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao salvar: {str(e)}")
            flash(f'Erro ao atualizar treino: {str(e)}', 'danger')
            return redirect(request.url)
    
    # ==========================================================
    # MÉTODO GET - CARREGAR FORMULÁRIO
    # ==========================================================
    
    # Buscar exercícios formatados para o template
    exercicios_display, exercicios_atuais = VersaoService.get_exercicios_para_edicao(
        user_id, treino_versao
    )
    
    # Buscar lista de músculos para o filtro
    musculos = MusculoService.get_all_nomes()
    
    # Construir contexto do template
    context = {
        'versao': versao,
        'treino_id': treino_codigo,
        'treino': {
            "nome": treino_versao.nome_treino,
            "descricao": treino_versao.descricao_treino,
            "exercicios": exercicios_atuais
        },
        'exercicios': exercicios_display,
        'musculos': musculos
    }
    
    # Adicionar contextos extras (ex: aluno para o professor)
    context.update(extra_context)
    
    return render_template(template, **context)


def _parse_exercicios_ids(raw_list, user_id):
    """
    Processa a lista de strings do formulário, separando por prefixo.
    
    Args:
        raw_list: Lista de strings (ex: ['u_1', 'b_5', 'u_3'])
        user_id: ID do usuário para validar exercícios customizados
    
    Returns:
        tuple: (usuarios_ids_validos, bases_ids_validos)
    """
    usuarios_ids = set()
    bases_ids = set()
    
    for item in raw_list:
        if not item or not item.strip():
            continue
        item = item.strip()
        
        if item.startswith('u_'):
            try:
                ex_id = int(item[2:])
                usuarios_ids.add(ex_id)
            except ValueError:
                pass
        elif item.startswith('b_'):
            try:
                ex_id = int(item[2:])
                bases_ids.add(ex_id)
            except ValueError:
                pass
    
    # Validar IDs de usuário (precisa pertencer ao user_id)
    usuarios_validos = []
    if usuarios_ids:
        exercicios = ExercicioCustomizado.query.filter(
            ExercicioCustomizado.id.in_(usuarios_ids),
            ExercicioCustomizado.usuario_id == user_id
        ).all()
        usuarios_validos = [e.id for e in exercicios]
    
    # Validar IDs da base (só precisa existir)
    bases_validos = []
    if bases_ids:
        exercicios = ExercicioBase.query.filter(
            ExercicioBase.id.in_(bases_ids)
        ).all()
        bases_validos = [e.id for e in exercicios]
    
    return usuarios_validos, bases_validos