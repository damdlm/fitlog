"""Cardio: exercícios registrados por TEMPO (com distância e intensidade
opcionais) em vez de carga × repetições.

Cada exercício (exercicios_usuario e exercicios_sistema) tem
`modo_registro`: 'carga' (padrão, como sempre foi) ou 'tempo'. A série de
um cardio (historico_treino) guarda duracao_segundos, distancia_km e
intensidade, com carga/repetições vazias -- assim o cardio nunca entra no
volume de força (carga × repetições), em recordes ou no 1RM estimado.

Os 9 tipos do combo da tela de registro apontam para exercícios do
catálogo (id_original). Os que não existiam no catálogo original foram
acrescentados pela migração c4d2a1b9e8f7 e em data/exercises.json.
"""

MODO_CARGA = 'carga'
MODO_TEMPO = 'tempo'
MODOS_REGISTRO = (MODO_CARGA, MODO_TEMPO)

INTENSIDADES = (('leve', 'Leve'), ('moderada', 'Moderada'), ('forte', 'Forte'))
INTENSIDADES_VALIDAS = {valor for valor, _rotulo in INTENSIDADES}

# Limites de sanidade do formulário (o servidor recusa o que passar disso).
DURACAO_MAX_MINUTOS = 600     # 10 h
DISTANCIA_MAX_KM = 500

# Combo "tipo de cardio" da tela de registro, nesta ordem.
TIPOS_CARDIO = (
    ('Esteira', '9001'),
    ('Bike', '9002'),
    ('Elíptico', '2331'),
    ('Escada', '9007'),
    ('Caminhada', '9005'),
    ('Corrida', '0685'),
    ('Spinning', '9003'),
    ('Remo', '9004'),
    ('Natação', '9006'),
)

# Exercícios do catálogo original que passam a ser registrados por tempo.
# Burpee, polichinelo, escalador etc. continuam por repetições.
IDS_ORIGINAIS_POR_TEMPO = (
    '2331',  # Bicicleta elíptica
    '2612',  # Pular corda
    '0685',  # Corrida
    '0684',  # Corrida (equipamento)
    '2138',  # Corrida na bicicleta ergométrica v. 3
    '0798',  # Caminhada na bicicleta ergométrica
    '2141',  # Caminhada na bicicleta elíptica
    '3666',  # Caminhada na esteira inclinada
    '2311',  # Caminhada no stepmill
    '5225',  # Bicicleta de ar
    '5227',  # Escalada no Jacob's ladder
    '5228',  # Escalada no escalador vertical
)


def eh_cardio(exercicio) -> bool:
    return getattr(exercicio, 'modo_registro', None) == MODO_TEMPO


def formatar_duracao(segundos) -> str:
    """1500 -> '25 min'; 5400 -> '1h30'; 90 -> '1min30s'."""
    if not segundos:
        return '0 min'
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f'{horas}h{minutos:02d}' if minutos else f'{horas}h'
    if seg and minutos < 10:
        return f'{minutos}min{seg:02d}s' if minutos else f'{seg}s'
    return f'{minutos} min'


def formatar_distancia(km) -> str:
    """2.5 -> '2,5 km'; 10 -> '10 km'."""
    if km is None:
        return ''
    valor = float(km)
    texto = f'{valor:.2f}'.rstrip('0').rstrip('.')
    return texto.replace('.', ',') + ' km'


def ritmo_e_velocidade(segundos, km):
    """(ritmo 'm:ss /km', velocidade 'x,x km/h') ou (None, None)."""
    if not segundos or not km or float(km) <= 0:
        return None, None
    km = float(km)
    seg_por_km = segundos / km
    ritmo = f'{int(seg_por_km // 60)}:{int(round(seg_por_km % 60)):02d} /km'
    velocidade = f'{km / (segundos / 3600):.1f}'.replace('.', ',') + ' km/h'
    return ritmo, velocidade


def resumo_serie_cardio(serie) -> str:
    """'25 min · 8,5 km · Moderada' para uma série de cardio."""
    partes = [formatar_duracao(getattr(serie, 'duracao_segundos', None))]
    if getattr(serie, 'distancia_km', None):
        partes.append(formatar_distancia(serie.distancia_km))
    intensidade = getattr(serie, 'intensidade', None)
    if intensidade:
        partes.append(dict(INTENSIDADES).get(intensidade, intensidade))
    return ' · '.join(partes)


def _numero(texto):
    """'2,5' / '2.5' / ' 20 ' -> float; vazio ou inválido -> None."""
    if texto is None:
        return None
    texto = str(texto).strip().replace(',', '.')
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def ler_cardio_do_formulario(form, chave):
    """Lê os campos de cardio de uma linha da tela de registro.

    Campos (mesma convenção de chave dos de força, ex.: "b_12"):
      duracao_<chave>     minutos (obrigatório, > 0)
      distancia_<chave>   km (opcional)
      intensidade_<chave> leve | moderada | forte (opcional)

    Retorna dict {duracao_segundos, distancia_km, intensidade} ou None
    quando não há tempo válido (linha não preenchida = não treinou).
    """
    minutos = _numero(form.get(f'duracao_{chave}'))
    if minutos is None or minutos <= 0 or minutos > DURACAO_MAX_MINUTOS:
        return None
    distancia = _numero(form.get(f'distancia_{chave}'))
    if distancia is not None and (distancia <= 0 or distancia > DISTANCIA_MAX_KM):
        distancia = None
    intensidade = (form.get(f'intensidade_{chave}') or '').strip().lower() or None
    if intensidade not in INTENSIDADES_VALIDAS:
        intensidade = None
    return {
        'duracao_segundos': int(round(minutos * 60)),
        'distancia_km': round(distancia, 2) if distancia is not None else None,
        'intensidade': intensidade,
    }


def opcoes_tipo_cardio():
    """[(rotulo, chave "b_<id>")] do combo de tipo, na ordem de TIPOS_CARDIO.
    Só os que existem no catálogo deste banco (a migração cria os novos)."""
    from models import ExercicioSistema
    ids = [id_original for _rotulo, id_original in TIPOS_CARDIO]
    por_id = {
        ex.id_original: ex.id
        for ex in ExercicioSistema.query.filter(ExercicioSistema.id_original.in_(ids)).all()
    }
    return [(rotulo, f'b_{por_id[id_original]}') for rotulo, id_original in TIPOS_CARDIO if id_original in por_id]


def volume_da_serie(serie) -> float:
    """carga × repetições de uma série de força; 0 para cardio (sem carga)."""
    if serie.carga is None or not serie.repeticoes:
        return 0.0
    return float(serie.carga) * serie.repeticoes


def serie_para_dict(serie) -> dict:
    """Série em JSON para telas/APIs. Força: carga/repeticoes como sempre.
    Cardio: carga/repeticoes None + duracao/distancia/intensidade e o
    texto pronto ("25 min · 8,5 km · Moderada")."""
    if getattr(serie, 'duracao_segundos', None) is not None:
        return {
            'cardio': True,
            'carga': None,
            'repeticoes': None,
            'duracao_segundos': serie.duracao_segundos,
            'distancia_km': float(serie.distancia_km) if serie.distancia_km is not None else None,
            'intensidade': serie.intensidade,
            'resumo': resumo_serie_cardio(serie),
        }
    return {
        'carga': float(serie.carga) if serie.carga is not None else 0.0,
        'repeticoes': serie.repeticoes if serie.repeticoes is not None else 0,
    }


DIAS_SEMANA_CURTOS = ('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')


def resumo_cardio_semana(user_id, hoje=None, recentes=5):
    """Cartão "Cardio" da página Progresso: totais da semana corrente
    (segunda a domingo que contém `hoje`), minutos por dia e as últimas
    sessões de cardio. Retorna None se o usuário nunca registrou cardio
    (o cartão nem aparece)."""
    from datetime import datetime, timedelta
    from models import HistoricoTreino, RegistroTreino
    from utils.format_utils import _agora_brasil

    hoje = hoje or _agora_brasil().date()
    inicio = hoje - timedelta(days=hoje.weekday())
    fim = inicio + timedelta(days=7)

    base = (HistoricoTreino.query
            .join(RegistroTreino, HistoricoTreino.registro_id == RegistroTreino.id)
            .filter(RegistroTreino.user_id == user_id,
                    HistoricoTreino.duracao_segundos.isnot(None)))

    ultimas = (base.order_by(RegistroTreino.data_registro.desc(), HistoricoTreino.id.desc())
               .limit(recentes).all())
    if not ultimas:
        return None

    da_semana = (base.filter(RegistroTreino.data_registro >= datetime.combine(inicio, datetime.min.time()),
                             RegistroTreino.data_registro < datetime.combine(fim, datetime.min.time()))
                 .all())

    minutos_por_dia = [0.0] * 7
    km_total = 0.0
    for serie in da_semana:
        dia = serie.registro_ref.data_registro.date()
        minutos_por_dia[(dia - inicio).days] += serie.duracao_segundos / 60
        km_total += float(serie.distancia_km or 0)
    maximo = max(minutos_por_dia) or 1

    def _nome(serie):
        reg = serie.registro_ref
        ex = reg.exercicio or reg.exercicio_base
        return ex.nome if ex else 'Cardio'

    return {
        'minutos': round(sum(minutos_por_dia)),
        'km': round(km_total, 1),
        'sessoes': len(da_semana),
        'dias': [
            {'rotulo': DIAS_SEMANA_CURTOS[i], 'minutos': round(m),
             'pct': round(m / maximo * 100), 'hoje': inicio + timedelta(days=i) == hoje}
            for i, m in enumerate(minutos_por_dia)
        ],
        'recentes': [
            {'data': s.registro_ref.data_registro.date(), 'nome': _nome(s), 'resumo': resumo_serie_cardio(s)}
            for s in ultimas
        ],
    }


# Valores da linha nova do "+ Cardio" para quem nunca registrou cardio.
CARDIO_PADRAO = {'tipo_rotulo': 'Esteira', 'duracao_min': 20, 'distancia_km': 2.5, 'intensidade': 'moderada'}


def ultimo_cardio(user_id):
    """Último cardio registrado pelo usuário (qualquer tipo/treino), para
    o "+ Cardio" já criar a linha preenchida -- igual aos exercícios de
    força, que abrem com a carga/reps da última sessão. None se nunca
    registrou cardio."""
    from models import HistoricoTreino, RegistroTreino

    serie = (HistoricoTreino.query
             .join(RegistroTreino, HistoricoTreino.registro_id == RegistroTreino.id)
             .filter(RegistroTreino.user_id == user_id,
                     HistoricoTreino.duracao_segundos.isnot(None))
             .order_by(RegistroTreino.data_registro.desc(), HistoricoTreino.id.desc())
             .first())
    if serie is None:
        return None
    reg = serie.registro_ref
    if reg.exercicio_usuario_id is not None:
        tipo, ex = f'u_{reg.exercicio_usuario_id}', reg.exercicio
    else:
        tipo, ex = f'b_{reg.exercicio_base_id}', reg.exercicio_base
    return {
        'tipo': tipo,
        'nome': ex.nome if ex else 'Cardio',
        'duracao_min': round(serie.duracao_segundos / 60, 1),
        'distancia_km': float(serie.distancia_km) if serie.distancia_km is not None else None,
        'intensidade': serie.intensidade or '',
    }


def cardio_inicial(user_id, opcoes=None):
    """Valores da linha criada pelo "+ Cardio": o último cardio do usuário
    ou, se não houver, Esteira 20 min / 2,5 km / moderada."""
    ultimo = ultimo_cardio(user_id)
    if ultimo:
        return ultimo
    opcoes = opcoes if opcoes is not None else opcoes_tipo_cardio()
    chave = next((c for rotulo, c in opcoes if rotulo == CARDIO_PADRAO['tipo_rotulo']),
                 opcoes[0][1] if opcoes else '')
    return {
        'tipo': chave,
        'nome': CARDIO_PADRAO['tipo_rotulo'],
        'duracao_min': CARDIO_PADRAO['duracao_min'],
        'distancia_km': CARDIO_PADRAO['distancia_km'],
        'intensidade': CARDIO_PADRAO['intensidade'],
    }
