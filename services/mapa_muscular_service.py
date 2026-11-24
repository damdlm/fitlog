"""Mapa muscular da tela Progresso: séries, recuperação e nível de força.

SÉRIES (segue o período escolhido na tela)
  Séries por região do corpo. Cada série de força conta 1 para o músculo
  principal do exercício e 0,5 para cada secundário ("séries efetivas").
  O volume em kg (carga × repetições) entra só no principal. Cardio fica
  de fora. `series_semana` é a média por semana no período, comparada com
  uma FAIXA DE REFERÊNCIA por região (FAIXAS_SEMANAIS: ordem de grandeza
  comum para hipertrofia; não é prescrição).

  De onde vem o músculo:
    - catálogo: principal = ExercicioSistema.alvo, secundários =
      musculos_secundarios (grupo_muscular NÃO é o principal no dataset).
    - exercício personalizado: o músculo escolhido, sem secundários.

PLANEJADO (ficha ativa)
  Séries que a ficha prevê por região em UM ciclo (cada treino uma vez):
  meta de séries do exercício (3 se a ficha não tiver meta). A tela
  converte para semana com "treinos por semana" (padrão: a média real das
  últimas 4 semanas; sem histórico, o número de treinos da ficha).

RECUPERAÇÃO (sempre "agora", ESTIMATIVA)
  Últimos 14 dias: a última sessão em que a região recebeu 2+ séries
  efetivas, na hora em que o treino foi salvo (created_at; se o treino foi
  lançado em outro dia, 18h do dia do treino). Janela: 72 h para músculos
  grandes, 48 h para os menores. Fração da janela já passada: < 50%
  "cedo", < 100% "quase", senão "recuperado".

NÍVEL DE FORÇA (precisa do peso corporal, User.peso_kg)
  Melhor 1RM estimado (Epley, séries de 1 a 12 repetições, últimos 180
  dias) dos levantamentos com barra de LEVANTAMENTOS, dividido pelo peso
  corporal e comparado com PADROES_FORCA (referência aproximada por sexo).
"""
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from models import (db, RegistroTreino, HistoricoTreino, ExercicioSistema, ExercicioUsuario, Musculo, User,
                    VersaoGlobal, TreinoVersao, VersaoExercicio)

FUSO_BR = ZoneInfo('America/Sao_Paulo')

# slug -> (nome na tela, janela de recuperação em horas)
REGIOES = {
    'peito': ('Peito', 72),
    'costas': ('Costas', 72),
    'lombar': ('Lombar', 72),
    'trapezio': ('Trapézio', 48),
    'ombros': ('Ombros', 48),
    'biceps': ('Bíceps', 48),
    'triceps': ('Tríceps', 48),
    'antebracos': ('Antebraços', 48),
    'abdomen': ('Abdômen', 48),
    'obliquos': ('Oblíquos', 48),
    'gluteos': ('Glúteos', 72),
    'quadriceps': ('Quadríceps', 72),
    'isquiotibiais': ('Posterior de coxa', 72),
    'adutores': ('Adutores', 48),
    'panturrilhas': ('Panturrilhas', 48),
    'canelas': ('Canelas', 48),
    'pescoco': ('Pescoço', 48),
}

# Séries por semana: faixa de referência (mín., máx.). Regiões sem faixa
# (pouco treinadas diretamente) aparecem sem a barra de meta.
FAIXAS_SEMANAIS = {
    'peito': (10, 20), 'costas': (10, 20), 'ombros': (8, 20), 'biceps': (8, 18), 'triceps': (6, 16),
    'quadriceps': (8, 18), 'isquiotibiais': (6, 14), 'gluteos': (4, 16), 'panturrilhas': (6, 16),
    'abdomen': (4, 16), 'trapezio': (4, 12), 'antebracos': (2, 10), 'obliquos': (2, 10), 'adutores': (2, 10),
    'lombar': (2, 8),
}

# Nome de músculo (sem acento, minúsculo) -> região
_MUSCULO_REGIAO = {
    'peitorais': 'peito', 'peito': 'peito', 'peito superior': 'peito',
    'abdomen': 'abdomen', 'abdominais': 'abdomen', 'core': 'abdomen', 'abdomen inferior': 'abdomen',
    'obliquos': 'obliquos', 'serratil anterior': 'obliquos',
    'deltoides': 'ombros', 'ombros': 'ombros', 'deltoides posteriores': 'ombros', 'manguito rotador': 'ombros',
    'biceps': 'biceps', 'braquial': 'biceps',
    'triceps': 'triceps',
    'antebracos': 'antebracos', 'flexores de punho': 'antebracos', 'extensores de punho': 'antebracos',
    'punhos': 'antebracos', 'musculos de preensao': 'antebracos', 'maos': 'antebracos',
    'trapezio': 'trapezio', 'levantador da escapula': 'trapezio',
    'costas superiores': 'costas', 'dorsais': 'costas', 'grande dorsal': 'costas', 'romboides': 'costas',
    'costas': 'costas',
    'lombar': 'lombar', 'coluna': 'lombar',
    'gluteos': 'gluteos', 'abdutores': 'gluteos',
    'quadriceps': 'quadriceps', 'flexores do quadril': 'quadriceps',
    'isquiotibiais': 'isquiotibiais', 'posterior de coxa': 'isquiotibiais',
    'adutores': 'adutores', 'parte interna das coxas': 'adutores', 'virilha': 'adutores',
    'panturrilhas': 'panturrilhas', 'soleo': 'panturrilhas',
    'tornozelos': 'canelas', 'estabilizadores do tornozelo': 'canelas', 'canelas': 'canelas', 'pes': 'canelas',
    'esternocleidomastoideo': 'pescoco', 'pescoco': 'pescoco',
    # nomes antigos/amplos da tabela Musculo
    'braco': 'biceps', 'bracos': 'biceps', 'perna': 'quadriceps', 'pernas': 'quadriceps', 'abdominal': 'abdomen',
}

DIAS_RECUPERACAO_OLHADOS = 14
SERIES_MINIMAS_RECUPERACAO = 2
SERIES_PADRAO_SEM_META = 3
HORA_PADRAO_TREINO = 18  # treino lançado em outro dia: considera 18h do dia do treino

# Levantamentos do nível de força: chave -> (nome na tela, nomes exatos no catálogo, minúsculos)
LEVANTAMENTOS = {
    'supino': ('Supino reto com barra', ['supino reto com barra']),
    'agachamento': ('Agachamento livre com barra', [
        'agachamento completo com barra', 'agachamento completo com barra (vista de trás)',
        'agachamento completo com barra (vista lateral)', 'agachamento barra alta com barra',
        'agachamento barra baixa com barra']),
    'terra': ('Levantamento terra com barra', ['levantamento terra com barra', 'levantamento terra sumô com barra']),
    'terra_romeno': ('Levantamento terra romeno com barra', ['levantamento terra romeno com barra']),
    'desenvolvimento': ('Desenvolvimento com barra', [
        'desenvolvimento militar pegada aberta em pé com barra', 'desenvolvimento militar pegada fechada em pé com barra',
        'desenvolvimento sentado com barra']),
    'remada': ('Remada curvada com barra', ['remada curvada com barra']),
}

NIVEIS_FORCA = ('Iniciante', 'Novato', 'Intermediário', 'Avançado', 'Elite')
# 1RM ÷ peso corporal para chegar a Novato, Intermediário, Avançado e Elite.
# Referência aproximada para adultos (tabelas populares de "strength
# standards"); serve para acompanhar a evolução, não é meta.
PADROES_FORCA = {
    'M': {'supino': (0.75, 1.0, 1.5, 2.0), 'agachamento': (1.0, 1.5, 2.0, 2.5), 'terra': (1.25, 1.75, 2.25, 3.0),
          'terra_romeno': (1.0, 1.4, 1.8, 2.4), 'desenvolvimento': (0.45, 0.65, 0.85, 1.1),
          'remada': (0.6, 0.85, 1.15, 1.5)},
    'F': {'supino': (0.4, 0.65, 0.9, 1.25), 'agachamento': (0.75, 1.1, 1.5, 2.0), 'terra': (0.9, 1.25, 1.75, 2.3),
          'terra_romeno': (0.75, 1.0, 1.4, 1.9), 'desenvolvimento': (0.3, 0.45, 0.6, 0.8),
          'remada': (0.4, 0.6, 0.85, 1.1)},
}
DIAS_FORCA = 180
REPS_MAX_1RM = 12


def _sem_acento(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


def regiao_do_musculo(nome):
    return _MUSCULO_REGIAO.get(_sem_acento(nome))


def _hoje():
    from services.estatistica_service import EstatisticaService
    return EstatisticaService.hoje_brasil()


def _agora():
    return datetime.now(FUSO_BR)


def _genero(user):
    from utils.genero_utils import resolver_genero
    return 'F' if user and resolver_genero(user) == 'F' else 'M'


def _dia(valor):
    return valor.date() if hasattr(valor, 'date') else valor


def _momento_do_treino(data_registro, created_at):
    """Hora (fuso de Brasília) em que a sessão aconteceu: a hora em que foi
    salva, se foi no mesmo dia do treino; senão 18h do dia do treino."""
    dia = _dia(data_registro)
    if created_at is not None:
        c = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        c = c.astimezone(FUSO_BR)
        if c.date() == dia:
            return c
    return datetime(dia.year, dia.month, dia.day, HORA_PADRAO_TREINO, tzinfo=FUSO_BR)


def e1rm(carga, reps):
    """1RM estimado (Epley). Uma repetição = a própria carga."""
    carga, reps = float(carga), int(reps)
    return carga if reps == 1 else carga * (1 + reps / 30)


class MapaMuscularService:

    # ------------------------------------------------------------------
    # Consultas base
    # ------------------------------------------------------------------

    @staticmethod
    def _series_por_registro(user_id, inicio=None, fim=None):
        """Uma linha por registro: ids do exercício, dia, created_at, séries
        de força e volume em kg."""
        q = (db.session.query(RegistroTreino.exercicio_base_id, RegistroTreino.exercicio_usuario_id,
                              RegistroTreino.data_registro, RegistroTreino.created_at,
                              func.count(HistoricoTreino.id),
                              func.coalesce(func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0))
             .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)
             .filter(RegistroTreino.user_id == user_id, HistoricoTreino.duracao_segundos.is_(None)))
        if inicio is not None:
            q = q.filter(RegistroTreino.data_registro >= inicio)
        if fim is not None:
            q = q.filter(RegistroTreino.data_registro <= fim)
        return q.group_by(RegistroTreino.id, RegistroTreino.exercicio_base_id, RegistroTreino.exercicio_usuario_id,
                          RegistroTreino.data_registro, RegistroTreino.created_at).all()

    @staticmethod
    def _musculos_dos_exercicios(pares):
        """{(base_id|None, usuario_id|None)} -> (região principal, [secundárias])."""
        ids_b = {b for b, u in pares if b}
        ids_u = {u for b, u in pares if u}
        mapa = {}
        if ids_b:
            for i, alvo, sec, grupo in db.session.query(ExercicioSistema.id, ExercicioSistema.alvo,
                                                        ExercicioSistema.musculos_secundarios,
                                                        ExercicioSistema.grupo_muscular) \
                    .filter(ExercicioSistema.id.in_(ids_b)):
                principal = regiao_do_musculo(alvo) or (None if alvo else regiao_do_musculo(grupo))
                secundarios = []
                for m in (sec or []):
                    r = regiao_do_musculo(m)
                    if r and r != principal and r not in secundarios:
                        secundarios.append(r)
                mapa[(i, None)] = (principal, secundarios)
        if ids_u:
            for i, nome in db.session.query(ExercicioUsuario.id, Musculo.nome_exibicao) \
                    .outerjoin(Musculo, Musculo.id == ExercicioUsuario.musculo_id) \
                    .filter(ExercicioUsuario.id.in_(ids_u)):
                mapa[(None, i)] = (regiao_do_musculo(nome), [])
        return mapa

    @staticmethod
    def _nomes_dos_exercicios(pares):
        ids_b = {b for b, u in pares if b}
        ids_u = {u for b, u in pares if u}
        nomes = {}
        if ids_b:
            nomes.update({(i, None): n for i, n in db.session.query(ExercicioSistema.id, ExercicioSistema.nome)
                          .filter(ExercicioSistema.id.in_(ids_b))})
        if ids_u:
            nomes.update({(None, i): n for i, n in db.session.query(ExercicioUsuario.id, ExercicioUsuario.nome)
                          .filter(ExercicioUsuario.id.in_(ids_u))})
        return nomes

    @staticmethod
    def _chave(b, u):
        return (b, None) if b else (None, u)

    # ------------------------------------------------------------------
    # Tudo do mapa
    # ------------------------------------------------------------------

    @staticmethod
    def calcular(user_id, periodo=None):
        """Dados do mapa. `periodo` é o dict de _periodo_da_requisicao
        (dia_inicio/dia_fim) ou None para todo o histórico."""
        dia_ini = periodo.get('dia_inicio') if periodo else None
        dia_fim = periodo.get('dia_fim') if periodo else None
        inicio = datetime.combine(dia_ini, datetime.min.time()) if dia_ini else None
        fim = datetime.combine(dia_fim, datetime.min.time()) if dia_fim else None

        regioes = {slug: {'nome': nome, 'series': 0.0, 'volume': 0.0, 'exercicios': {},
                          'faixa': FAIXAS_SEMANAIS.get(slug)}
                   for slug, (nome, _) in REGIOES.items()}
        linhas = MapaMuscularService._series_por_registro(user_id, inicio, fim)
        pares = {(b, u) for b, u, *_ in linhas}
        musculos = MapaMuscularService._musculos_dos_exercicios(pares)
        nomes = MapaMuscularService._nomes_dos_exercicios(pares)
        primeiro_dia = None
        for b, u, dia, _criado, series, volume in linhas:
            k = MapaMuscularService._chave(b, u)
            principal, secundarios = musculos.get(k, (None, []))
            d = _dia(dia)
            primeiro_dia = d if primeiro_dia is None or d < primeiro_dia else primeiro_dia
            if principal:
                r = regioes[principal]
                r['series'] += series
                r['volume'] += float(volume or 0)
                if nomes.get(k):
                    r['exercicios'][nomes[k]] = r['exercicios'].get(nomes[k], 0) + series
            for s in secundarios:
                regioes[s]['series'] += series * 0.5

        # semanas do período (todo o histórico: desde o primeiro treino)
        ini = dia_ini or primeiro_dia
        fim_d = dia_fim or _hoje()
        dias = ((fim_d - ini).days + 1) if ini else 7
        semanas = max(dias, 7) / 7

        recuperacao = MapaMuscularService._recuperacao(user_id)
        planejado = MapaMuscularService.planejado(user_id)
        for slug, r in regioes.items():
            r['series'] = round(r['series'], 1)
            r['series_semana'] = round(r['series'] / semanas, 1)
            r['volume'] = round(r['volume'])
            r['principais'] = [n for n, _ in sorted(r['exercicios'].items(), key=lambda x: -x[1])[:3]]
            del r['exercicios']
            r['planejado_ciclo'] = planejado['por_regiao'].get(slug, 0)
            r.update(recuperacao[slug])

        aluno = db.session.get(User, user_id)
        return {
            'genero': _genero(aluno),
            'semanas': round(semanas, 1),
            'regioes': regioes,
            'max_series': max((r['series'] for r in regioes.values()), default=0),
            'planejado': {k: v for k, v in planejado.items() if k != 'por_regiao'},
        }

    # ------------------------------------------------------------------
    # Planejado
    # ------------------------------------------------------------------

    @staticmethod
    def planejado(user_id):
        """Séries que a ficha ativa prevê por região em um ciclo (cada treino
        uma vez) + treinos da ficha + média real de treinos por semana."""
        vazio = {'por_regiao': {}, 'treinos': 0, 'sessoes_semana': None, 'ficha': None}
        versao = (VersaoGlobal.query.filter_by(user_id=user_id, data_fim=None)
                  .order_by(VersaoGlobal.data_inicio.desc()).first())
        if not versao:
            return vazio
        itens = (db.session.query(VersaoExercicio.exercicio_base_id, VersaoExercicio.exercicio_usuario_id,
                                  VersaoExercicio.meta_series, TreinoVersao.id)
                 .join(TreinoVersao, TreinoVersao.id == VersaoExercicio.treino_versao_id)
                 .filter(TreinoVersao.versao_id == versao.id).all())
        treinos = {t for *_, t in itens}
        pares = {(b, u) for b, u, *_ in itens}
        musculos = MapaMuscularService._musculos_dos_exercicios(pares)
        cardio = set()
        ids_b = {b for b, u in pares if b}
        ids_u = {u for b, u in pares if u}
        if ids_b:
            cardio |= {(i, None) for (i,) in db.session.query(ExercicioSistema.id).filter(
                ExercicioSistema.id.in_(ids_b), ExercicioSistema.modo_registro == 'tempo')}
        if ids_u:
            cardio |= {(None, i) for (i,) in db.session.query(ExercicioUsuario.id).filter(
                ExercicioUsuario.id.in_(ids_u), ExercicioUsuario.modo_registro == 'tempo')}
        por = {}
        for b, u, meta, _t in itens:
            k = MapaMuscularService._chave(b, u)
            if k in cardio:
                continue
            principal, secundarios = musculos.get(k, (None, []))
            n = meta or SERIES_PADRAO_SEM_META
            if principal:
                por[principal] = por.get(principal, 0) + n
            for s in secundarios:
                por[s] = por.get(s, 0) + n * 0.5

        # média real de sessões (treino + dia) por semana nas últimas 4 semanas
        desde = datetime.combine(_hoje() - timedelta(days=27), datetime.min.time())
        sessoes = (db.session.query(RegistroTreino.data_registro, RegistroTreino.treino_versao_id)
                   .filter(RegistroTreino.user_id == user_id, RegistroTreino.data_registro >= desde)
                   .distinct().count())
        return {
            'por_regiao': {k: round(v, 1) for k, v in por.items()},
            'treinos': len(treinos),
            'sessoes_semana': round(sessoes / 4, 1) if sessoes else None,
            'ficha': versao.descricao,
        }

    # ------------------------------------------------------------------
    # Recuperação por hora
    # ------------------------------------------------------------------

    @staticmethod
    def _recuperacao(user_id):
        """Ver RECUPERAÇÃO no docstring do módulo."""
        hoje = _hoje()
        agora = _agora()
        inicio = datetime.combine(hoje - timedelta(days=DIAS_RECUPERACAO_OLHADOS - 1), datetime.min.time())
        fim = datetime.combine(hoje, datetime.min.time())
        linhas = MapaMuscularService._series_por_registro(user_id, inicio, fim)
        musculos = MapaMuscularService._musculos_dos_exercicios({(b, u) for b, u, *_ in linhas})

        # (região, dia do treino) -> [séries efetivas, momento mais tarde]
        por_dia = {}
        for b, u, dia, criado, series, _v in linhas:
            principal, secundarios = musculos.get(MapaMuscularService._chave(b, u), (None, []))
            momento = _momento_do_treino(dia, criado)
            alvos = ([(principal, 1)] if principal else []) + [(s, 0.5) for s in secundarios]
            for regiao, peso in alvos:
                atual = por_dia.setdefault((regiao, _dia(dia)), [0, momento])
                atual[0] += series * peso
                atual[1] = max(atual[1], momento)

        ultimo = {}
        for (regiao, _d), (series, momento) in por_dia.items():
            if series >= SERIES_MINIMAS_RECUPERACAO and (regiao not in ultimo or momento > ultimo[regiao]):
                ultimo[regiao] = momento

        out = {}
        for slug, (_nome, janela) in REGIOES.items():
            m = ultimo.get(slug)
            if m is None:
                out[slug] = {'status': 'sem_treino', 'horas_desde': None, 'horas_restantes': None,
                             'pronto_em': None, 'janela_h': janela}
                continue
            horas = max(0.0, (agora - m).total_seconds() / 3600)
            fracao = horas / janela
            status = 'recuperado' if fracao >= 1 else ('quase' if fracao >= 0.5 else 'cedo')
            out[slug] = {'status': status, 'horas_desde': round(horas, 1),
                         'horas_restantes': round(max(0.0, janela - horas), 1),
                         'pronto_em': (m + timedelta(hours=janela)).strftime('%Y-%m-%dT%H:%M'),
                         'janela_h': janela}
        return out

    # ------------------------------------------------------------------
    # Nível de força
    # ------------------------------------------------------------------

    @staticmethod
    def niveis_forca(user_id):
        """Melhor 1RM estimado de cada levantamento com barra e o nível pelo
        peso corporal. Ver NÍVEL DE FORÇA no docstring do módulo."""
        aluno = db.session.get(User, user_id)
        genero = _genero(aluno)
        peso = float(aluno.peso_kg) if aluno and aluno.peso_kg else None

        nome_para_chave = {n: k for k, (_rot, nomes) in LEVANTAMENTOS.items() for n in nomes}
        ids = {}
        for i, n in db.session.query(ExercicioSistema.id, ExercicioSistema.nome) \
                .filter(func.lower(ExercicioSistema.nome).in_(list(nome_para_chave))):
            chave = nome_para_chave.get((n or '').strip().lower())
            if chave:
                ids[i] = chave
        melhores = {}
        if ids:
            desde = datetime.combine(_hoje() - timedelta(days=DIAS_FORCA), datetime.min.time())
            linhas = (db.session.query(RegistroTreino.exercicio_base_id, RegistroTreino.data_registro,
                                       HistoricoTreino.carga, HistoricoTreino.repeticoes)
                      .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)
                      .filter(RegistroTreino.user_id == user_id,
                              RegistroTreino.exercicio_base_id.in_(list(ids)),
                              RegistroTreino.data_registro >= desde,
                              HistoricoTreino.carga > 0,
                              HistoricoTreino.repeticoes >= 1,
                              HistoricoTreino.repeticoes <= REPS_MAX_1RM))
            for ex_id, dia, carga, reps in linhas:
                chave = ids[ex_id]
                valor = e1rm(carga, reps)
                if chave not in melhores or valor > melhores[chave]['e1rm']:
                    melhores[chave] = {'e1rm': valor, 'carga': float(carga), 'reps': int(reps),
                                       'data': _dia(dia).strftime('%d/%m/%Y')}

        itens = []
        for chave, (rotulo, _n) in LEVANTAMENTOS.items():
            m = melhores.get(chave)
            if not m:
                continue
            item = {'chave': chave, 'nome': rotulo, 'e1rm': round(m['e1rm'], 1), 'carga': m['carga'],
                    'reps': m['reps'], 'data': m['data']}
            if peso:
                razao = m['e1rm'] / peso
                limites = PADROES_FORCA[genero][chave]
                nivel = sum(1 for x in limites if razao >= x)
                item.update(razao=round(razao, 2), nivel=NIVEIS_FORCA[nivel], nivel_idx=nivel)
                if nivel < len(limites):
                    item['proximo'] = NIVEIS_FORCA[nivel + 1]
                    item['faltam_kg'] = round(max(0.5, limites[nivel] * peso - m['e1rm']), 1)
            itens.append(item)
        return {'peso_kg': peso, 'genero': genero, 'levantamentos': itens}
