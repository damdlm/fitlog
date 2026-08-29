from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from services.registro_service import RegistroService
from services.treino_service import TreinoService
from utils.decorators import acesso_premium_required
from datetime import datetime, timezone, timedelta
import calendar
import logging

calendar_bp = Blueprint('calendar', __name__)
logger = logging.getLogger(__name__)

# Cor única para os dias com treino registrado (mesma cor da marca).
# Antes variava por volume (verde/amarelo/laranja/vermelho); simplificado
# para um único indicador, sem precisar de legenda explicando níveis.
COR_TREINO = '#F28C33'

@calendar_bp.route("/calendario")
@login_required
@acesso_premium_required('calendario')
def calendario():
    """Página do calendário de treinos"""
    treinos = TreinoService.get_all()
    
    # 👇 PASSAR A DATA ATUAL PARA O TEMPLATE
    data_atual = datetime.now(timezone.utc)
    
    return render_template(
        "calendar/calendario.html", 
        treinos=treinos,
        data_atual=data_atual  # 👈 ADICIONADO
    )


@calendar_bp.route("/api/eventos")
@login_required
@acesso_premium_required('calendario')
def api_eventos():
    """API para retornar os eventos do calendário"""
    try:
        from services.base_service import BaseService

        # Parâmetros opcionais de filtro
        ano = request.args.get('ano', type=int)
        mes = request.args.get('mes', type=int)
        treino_id = request.args.get('treino_id')
        aluno_id = request.args.get('aluno_id', type=int)

        # get_target_user_id já valida: se aluno_id não pertencer a este
        # professor (nem for admin), cai de volta para o próprio usuário.
        target_user_id = BaseService.get_target_user_id(aluno_id)

        # Buscar registros do usuário (ou do aluno, se professor consultando).
        # Quando ano/mes são passados, filtra no banco por intervalo de data
        # (usa o índice idx_registro_user_data), em vez de carregar todo o
        # histórico e filtrar em Python. Hoje o frontend do calendário busca
        # tudo de uma vez de propósito (ver comentário em calendario.html:
        # permite navegar entre meses sem nova requisição), então isto não
        # muda o comportamento atual — só evita carregar histórico inteiro
        # quando algum chamador (ex: app mobile futuro, professor filtrando
        # aluno por mês específico) passar ano/mes.
        data_inicio = data_fim_exclusiva = None
        if ano and mes:
            data_inicio = datetime(ano, mes, 1, tzinfo=timezone.utc)
            data_fim_exclusiva = datetime(ano + 1, 1, 1, tzinfo=timezone.utc) if mes == 12 \
                else datetime(ano, mes + 1, 1, tzinfo=timezone.utc)
        elif ano and not mes:
            data_inicio = datetime(ano, 1, 1, tzinfo=timezone.utc)
            data_fim_exclusiva = datetime(ano + 1, 1, 1, tzinfo=timezone.utc)
        # "mes" sem "ano" é ambíguo (mesmo mês em anos diferentes) — mantém
        # comportamento antigo (filtro em Python) só para esse caso raro.

        registros = RegistroService.get_all(
            user_id=target_user_id,
            load_series=True,
            data_inicio=data_inicio,
            data_fim=data_fim_exclusiva,
        )

        # Buscar os treinos do usuário uma única vez (evita repetir a query
        # dentro do loop de registros abaixo — antes TreinoService.get_all()
        # era chamado a cada iteração).
        treinos_por_id = {t.id: t for t in TreinoService.get_all(user_id=target_user_id)}

        eventos = []
        volumes_por_dia = {}
        
        for r in registros:
            # Usar data_registro se disponível, senão estimar a partir do período
            if r.data_registro:
                data = r.data_registro.date() if hasattr(r.data_registro, 'date') else r.data_registro
            else:
                # Estimar data a partir do período e semana
                data = _estimar_data(r.periodo, r.semana)
                if not data:
                    continue
            
            # Filtrar por ano/mês se especificado
            if ano and data.year != ano:
                continue
            if mes and data.month != mes:
                continue
            
            # Calcular volume total do treino
            volume_total = 0
            for serie in r.series:
                volume_total += float(serie.carga) * serie.repeticoes
            
            # Agrupar por data
            data_str = data.strftime('%Y-%m-%d')
            if data_str not in volumes_por_dia:
                volumes_por_dia[data_str] = {
                    'data': data,
                    'volume_total': 0,
                    'treinos': [],
                    'exercicios': 0
                }
            
            volumes_por_dia[data_str]['volume_total'] += volume_total
            volumes_por_dia[data_str]['exercicios'] += 1
            
            # Adicionar detalhe do treino
            treino = treinos_por_id.get(r.treino_versao_id)
            
            # Nome do exercício (pode ser do catálogo do usuário ou global)
            exercicio_obj = r.exercicio if r.exercicio_usuario_id else r.exercicio_base
            exercicio_nome = exercicio_obj.nome if exercicio_obj else 'Exercício'
            
            series_detalhe = [
                {'carga': float(s.carga), 'repeticoes': s.repeticoes}
                for s in r.series
            ]
            
            volumes_por_dia[data_str]['treinos'].append({
                'id': r.id,
                'treino_id': r.treino_versao_id,
                'treino_codigo': treino.codigo if treino else '?',
                'treino_nome': treino.nome if treino else 'Treino',
                'exercicio_nome': exercicio_nome,
                'series': series_detalhe,
                'volume': volume_total,
                'exercicios': len(list(r.series)) if r.series else 0
            })
        
        # Criar eventos para o calendário
        for data_str, dados in volumes_por_dia.items():
            # Título resumido
            titulo = f"{dados['exercicios']} ex • {dados['volume_total']:.0f}kg"
            
            # Descrição detalhada para o tooltip
            descricao = f"<strong>{data_str}</strong><br>"
            descricao += f"Total: {dados['volume_total']:.0f}kg<br>"
            descricao += f"Exercícios: {dados['exercicios']}<br><br>"
            
            for t in dados['treinos']:
                descricao += f"🏋️ {t['treino_codigo']} · {t['exercicio_nome']}: {t['volume']:.0f}kg<br>"
            
            eventos.append({
                'title': titulo,
                'start': data_str,
                'end': data_str,
                'color': COR_TREINO,
                'textColor': '#ffffff',
                'extendedProps': {
                    'volume': dados['volume_total'],
                    'exercicios': dados['exercicios'],
                    'treinos': dados['treinos'],
                    'descricao': descricao
                }
            })
        
        return jsonify(eventos)
        
    except Exception:
        logger.exception("Erro ao gerar eventos")
        return jsonify([])


@calendar_bp.route("/api/evento/<int:registro_id>")
@login_required
@acesso_premium_required('calendario')
def api_evento_detalhe(registro_id):
    """Retorna detalhes de um evento (um exercício registrado) específico"""
    from models import db, RegistroTreino
    from services.base_service import BaseService

    registro = db.session.get(RegistroTreino, registro_id)
    if not registro:
        return jsonify({"error": "Registro não encontrado"}), 404

    # Dono do registro, admin, ou professor vinculado ao dono podem ver
    pode_acessar = (
        registro.user_id == current_user.id
        or current_user.is_admin
        or BaseService.get_target_user_id(registro.user_id) == registro.user_id
    )
    if not pode_acessar:
        return jsonify({"error": "Registro não encontrado"}), 404

    # Buscar treino
    treino = None
    for t in TreinoService.get_all(user_id=registro.user_id):
        if t.id == registro.treino_versao_id:
            treino = t
            break

    # Buscar exercício (do catálogo do usuário ou global) e suas séries
    exercicio_obj = registro.exercicio if registro.exercicio_usuario_id else registro.exercicio_base
    musculo_nome = exercicio_obj.musculo_nome if exercicio_obj and hasattr(exercicio_obj, 'musculo_nome') else (
        exercicio_obj.musculo_ref.nome_exibicao if exercicio_obj and exercicio_obj.musculo_ref else None
    )

    exercicios = []
    for serie in registro.series:
        exercicios.append({
            'nome': exercicio_obj.nome if exercicio_obj else 'Desconhecido',
            'musculo': musculo_nome or 'N/A',
            'carga': float(serie.carga),
            'repeticoes': serie.repeticoes,
            'volume': float(serie.carga) * serie.repeticoes
        })
    
    return jsonify({
        'id': registro.id,
        'data': registro.data_registro.strftime('%d/%m/%Y') if registro.data_registro else 'N/A',
        'treino': {
            'id': treino.id if treino else None,
            'codigo': treino.codigo if treino else 'N/A',
            'nome': treino.nome if treino else 'N/A'
        },
        'exercicios': exercicios,
        'total_volume': sum(e['volume'] for e in exercicios)
    })


def _estimar_data(periodo, semana):
    """Estima uma data a partir do período e semana"""
    try:
        from utils.date_utils import MESES
        if '/' in periodo:
            mes_nome, ano_str = periodo.split('/')
            mes_num = MESES.get(mes_nome.lower())
            ano = int(ano_str)
            
            if mes_num:
                # Primeiro dia do mês + (semana-1)*7 dias
                data_base = datetime(ano, mes_num, 1).date()
                dias = (semana - 1) * 7
                return data_base + timedelta(days=dias)
    except (ValueError, TypeError, KeyError):
        # Entrada de "periodo" mal formada (ex: mês inválido, ano não
        # numérico) -- comportamento já era cair pra None; só deixamos
        # de engolir QUALQUER exceção (bare except) e passamos a pegar
        # só os erros esperados de parsing, sem mascarar bugs futuros.
        pass
    return None