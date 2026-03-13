from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from services.registro_service import RegistroService
from services.treino_service import TreinoService
from datetime import datetime, timedelta
import calendar
import logging

calendar_bp = Blueprint('calendar', __name__)
logger = logging.getLogger(__name__)

@calendar_bp.route("/calendario")
@login_required
def calendario():
    """Página do calendário de treinos"""
    treinos = TreinoService.get_all()
    
    # 👇 PASSAR A DATA ATUAL PARA O TEMPLATE
    data_atual = datetime.now()
    
    return render_template(
        "calendar/calendario.html", 
        treinos=treinos,
        data_atual=data_atual  # 👈 ADICIONADO
    )


@calendar_bp.route("/api/eventos")
@login_required
def api_eventos():
    """API para retornar os eventos do calendário"""
    try:
        # Parâmetros opcionais de filtro
        ano = request.args.get('ano', type=int)
        mes = request.args.get('mes', type=int)
        treino_id = request.args.get('treino_id')
        
        # Buscar todos os registros do usuário
        registros = RegistroService.get_all(load_series=True)
        
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
            treino = None
            for t in TreinoService.get_all():
                if t.id == r.treino_id:
                    treino = t
                    break
            
            volumes_por_dia[data_str]['treinos'].append({
                'id': r.id,
                'treino_id': r.treino_id,
                'treino_codigo': treino.codigo if treino else '?',
                'treino_nome': treino.nome if treino else 'Treino',
                'volume': volume_total,
                'exercicios': len(list(r.series)) if r.series else 0
            })
        
        # Criar eventos para o calendário
        for data_str, dados in volumes_por_dia.items():
            # Determinar cor baseada no volume
            cor = _get_color_by_volume(dados['volume_total'])
            
            # Título resumido
            titulo = f"{dados['exercicios']} ex • {dados['volume_total']:.0f}kg"
            
            # Descrição detalhada para o tooltip
            descricao = f"<strong>{data_str}</strong><br>"
            descricao += f"Total: {dados['volume_total']:.0f}kg<br>"
            descricao += f"Exercícios: {dados['exercicios']}<br><br>"
            
            for t in dados['treinos']:
                descricao += f"🏋️ {t['treino_codigo']}: {t['volume']:.0f}kg ({t['exercicios']} ex)<br>"
            
            eventos.append({
                'title': titulo,
                'start': data_str,
                'end': data_str,
                'color': cor,
                'textColor': '#ffffff',
                'extendedProps': {
                    'volume': dados['volume_total'],
                    'exercicios': dados['exercicios'],
                    'treinos': dados['treinos'],
                    'descricao': descricao
                }
            })
        
        return jsonify(eventos)
        
    except Exception as e:
        logger.error(f"Erro ao gerar eventos: {e}")
        return jsonify([])


@calendar_bp.route("/api/evento/<int:registro_id>")
@login_required
def api_evento_detalhe(registro_id):
    """Retorna detalhes de um evento específico"""
    from models import RegistroTreino, ExercicioCustomizado, Musculo

    registro = RegistroTreino.query.get(registro_id)
    if not registro or registro.user_id != current_user.id:
        return jsonify({"error": "Registro não encontrado"}), 404

    # Buscar treino
    treino = None
    for t in TreinoService.get_all():
        if t.id == registro.treino_id:
            treino = t
            break

    # Buscar exercício e suas séries
    exercicio = ExercicioCustomizado.query.get(registro.exercicio_id)
    musculo = Musculo.query.get(exercicio.musculo_id) if exercicio and exercicio.musculo_id else None

    exercicios = []
    for serie in registro.series:
        exercicios.append({
            'nome': exercicio.nome if exercicio else 'Desconhecido',
            'musculo': musculo.nome_exibicao if musculo else 'N/A',
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
    except:
        pass
    return None


def _get_color_by_volume(volume):
    """Retorna uma cor baseada no volume do treino"""
    if volume < 1000:
        return '#90be6d'  # Verde claro (volume baixo)
    elif volume < 3000:
        return '#f9c74f'  # Amarelo (volume médio)
    elif volume < 6000:
        return '#f9844a'  # Laranja (volume alto)
    else:
        return '#f94144'  # Vermelho (volume muito alto)