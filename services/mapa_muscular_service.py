"""Mapa muscular da tela Progresso: Séries, Fadiga e Força (modelo do openGym,
com implementação própria -- o código do openGym é AGPL e não foi copiado).

SÉRIES (por semana, segunda a domingo no fuso de Brasília; ?semana=0 é a
atual, -1 a anterior...)
  Cada série de força conta 1 para o músculo principal e 0,5 para cada
  secundário ("séries efetivas"); kg só no principal; cardio fora. Comparado
  com uma FAIXA DE REFERÊNCIA semanal por região (FAIXAS_SEMANAIS).
  Músculo do catálogo: principal = alvo, secundários = musculos_secundarios
  (grupo_muscular NÃO é o principal no dataset).

PLANEJADO (ficha ativa)
  Séries que a ficha prevê por região em UM ciclo (meta de séries, 3 sem
  meta); a tela converte para semana com "treinos por semana".

FADIGA (agora; ESTIMATIVA)
  Cada sessão gera um estímulo por região = séries efetivas do dia ÷ 8 (uma
  sessão cheia ~ 8 séries = 1,0), limitado a 12 séries. O estímulo decai pela
  meia-vida da região (MEIA_VIDA_H: 24 h músculos pequenos/core, 30 h tronco,
  48 h pernas e lombar) e a fadiga é a soma do que sobrou das sessões dos
  últimos 21 dias. Estados: > 0,5 fatigado; 0,25-0,5 recuperando; < 0,25
  pronto. "Pronto de novo" = quando a soma cai para 0,25.
  Hora da sessão: quando o treino foi salvo (created_at); lançado em outro
  dia, 18h do dia do treino.

FORÇA RETIDA (agora; ESTIMATIVA)
  1,0 até 14 dias depois do último treino da região; depois cai pela metade
  a cada 28 dias, até o piso de 0,5. Nunca treinada nos últimos 6 meses:
  "não treinado" (piso). Por região, os exercícios que a treinam (principal
  ou secundário) com o melhor 1RM estimado (Epley, 1-12 reps, 6 meses), a
  data do último treino e a força retida daquele exercício.

NÍVEL DE FORÇA (precisa do peso corporal, User.peso_kg)
  Melhor 1RM estimado dos levantamentos com barra de LEVANTAMENTOS ÷ peso
  corporal, comparado com PADROES_FORCA (referência aproximada por sexo).
"""
import math
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from models import (db, RegistroTreino, HistoricoTreino, ExercicioSistema, ExercicioUsuario, Musculo, User,
                    VersaoGlobal, TreinoVersao, VersaoExercicio)

FUSO_BR = ZoneInfo('America/Sao_Paulo')

# slug -> (nome na tela, meia-vida da fadiga em horas)
REGIOES = {
    'peito': ('Peito', 30),
    'costas': ('Costas', 30),
    'lombar': ('Lombar', 48),
    'trapezio': ('Trapézio', 30),
    'ombros': ('Ombros', 24),
    'biceps': ('Bíceps', 24),
    'triceps': ('Tríceps', 24),
    'antebracos': ('Antebraços', 24),
    'abdomen': ('Abdômen', 24),
    'obliquos': ('Oblíquos', 24),
    'gluteos': ('Glúteos', 48),
    'quadriceps': ('Quadríceps', 48),
    'isquiotibiais': ('Posterior de coxa', 48),
    'adutores': ('Adutores', 48),
    'panturrilhas': ('Panturrilhas', 48),
    'canelas': ('Canelas', 24),
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
    # nomes antigos/amplos da tabela Musculo
    'braco': 'biceps', 'bracos': 'biceps', 'perna': 'quadriceps', 'pernas': 'quadriceps', 'abdominal': 'abdomen',
}

SERIES_PADRAO_SEM_META = 3
HORA_PADRAO_TREINO = 18  # treino lançado em outro dia: considera 18h do dia do treino

# Fadiga (ver FADIGA no docstring)
DIAS_FADIGA = 21
SERIES_SESSAO_CHEIA = 8
SERIES_SESSAO_MAX = 12
FADIGA_FATIGADO = 0.5
FADIGA_PRONTO = 0.25

# Força retida (ver FORÇA RETIDA no docstring)
DIAS_FORCA_CHEIA = 14
DIAS_MEIA_VIDA_FORCA = 28
PISO_FORCA = 0.5
DIAS_HISTORICO = 180

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


def forca_retida(dias):
    """Ver FORÇA RETIDA no docstring do módulo."""
    if dias <= DIAS_FORCA_CHEIA:
        return 1.0
    return max(PISO_FORCA, 0.5 ** ((dias - DIAS_FORCA_CHEIA) / DIAS_MEIA_VIDA_FORCA))


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
    def semana(offset=0):
        """(segunda, domingo) da semana `offset` (0 = atual, -1 = anterior)."""
        hoje = _hoje()
        seg = hoje - timedelta(days=hoje.weekday()) + timedelta(weeks=offset)
        return seg, seg + timedelta(days=6)

    @staticmethod
    def calcular(user_id, semana=0):
        """Dados das três abas para a semana `semana` (0 = atual)."""
        seg, dom = MapaMuscularService.semana(semana)
        hoje = _hoje()
        inicio_hist = hoje - timedelta(days=DIAS_HISTORICO - 1)
        linhas = MapaMuscularService._series_por_registro(
            user_id, datetime.combine(min(seg, inicio_hist), datetime.min.time()),
            datetime.combine(max(dom, hoje), datetime.min.time()))
        pares = {(b, u) for b, u, *_ in linhas}
        musculos = MapaMuscularService._musculos_dos_exercicios(pares)
        nomes = MapaMuscularService._nomes_dos_exercicios(pares)

        regioes = {slug: {'nome': nome, 'faixa': FAIXAS_SEMANAIS.get(slug), 'series': 0.0, 'volume': 0.0,
                          'exercicios_semana': {}}
                   for slug, (nome, _) in REGIOES.items()}
        sessoes = {}   # (região, dia) -> [séries efetivas, momento mais tarde]
        ultimo = {}    # região -> momento do último treino (6 meses)
        for b, u, dia, criado, series, volume in linhas:
            k = MapaMuscularService._chave(b, u)
            principal, secundarios = musculos.get(k, (None, []))
            d = _dia(dia)
            alvos = ([(principal, 1.0)] if principal else []) + [(r, 0.5) for r in secundarios]
            if not alvos:
                continue
            if seg <= d <= dom and d <= hoje:  # treino com data futura não conta
                for regiao, peso in alvos:
                    regioes[regiao]['series'] += series * peso
                if principal:
                    regioes[principal]['volume'] += float(volume or 0)
                    if nomes.get(k):
                        ex = regioes[principal]['exercicios_semana']
                        ex[nomes[k]] = ex.get(nomes[k], 0) + series
            if d > hoje or d < inicio_hist:
                continue
            momento = _momento_do_treino(dia, criado)
            for regiao, peso in alvos:
                atual = sessoes.setdefault((regiao, d), [0.0, momento])
                atual[0] += series * peso
                atual[1] = max(atual[1], momento)
                if regiao not in ultimo or momento > ultimo[regiao]:
                    ultimo[regiao] = momento

        fadiga = MapaMuscularService._fadiga(sessoes)
        exercicios = MapaMuscularService._exercicios_por_regiao(user_id, musculos, nomes, inicio_hist)
        planejado = MapaMuscularService.planejado(user_id)
        agora = _agora()
        for slug, r in regioes.items():
            r['series'] = round(r['series'], 1)
            r['volume'] = round(r['volume'])
            r['principais'] = [n for n, _ in sorted(r['exercicios_semana'].items(), key=lambda x: -x[1])[:3]]
            del r['exercicios_semana']
            r['planejado_ciclo'] = planejado['por_regiao'].get(slug, 0)
            r.update(fadiga[slug])
            m = ultimo.get(slug)
            r['ultimo_treino'] = m.strftime('%Y-%m-%dT%H:%M') if m else None
            r['retida'] = round(forca_retida((agora - m).total_seconds() / 86400) if m else PISO_FORCA, 3)
            r['exercicios'] = exercicios.get(slug, [])

        aluno = db.session.get(User, user_id)
        return {
            'genero': _genero(aluno),
            'semana': {'offset': semana, 'inicio': seg.isoformat(), 'fim': dom.isoformat()},
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
    # Fadiga e força retida
    # ------------------------------------------------------------------

    @staticmethod
    def _fadiga(sessoes):
        """Ver FADIGA no docstring do módulo. `sessoes`: (região, dia) ->
        [séries efetivas, momento]."""
        agora = _agora()
        limite = agora - timedelta(days=DIAS_FADIGA)
        por_regiao = {}
        for (regiao, _d), (series, momento) in sessoes.items():
            if momento < limite:
                continue
            horas = max(0.0, (agora - momento).total_seconds() / 3600)
            estimulo = min(series, SERIES_SESSAO_MAX) / SERIES_SESSAO_CHEIA
            meia_vida = REGIOES[regiao][1]
            por_regiao[regiao] = por_regiao.get(regiao, 0.0) + estimulo * 0.5 ** (horas / meia_vida)
        out = {}
        for slug, (_nome, meia_vida) in REGIOES.items():
            f = por_regiao.get(slug)
            if f is None:
                out[slug] = {'fadiga': 0, 'estado': 'sem_treino', 'horas_restantes': 0, 'pronto_em': None}
                continue
            estado = 'fatigado' if f > FADIGA_FATIGADO else ('recuperando' if f >= FADIGA_PRONTO else 'pronto')
            horas = meia_vida * math.log2(f / FADIGA_PRONTO) if f > FADIGA_PRONTO else 0.0
            out[slug] = {'fadiga': round(f, 3), 'estado': estado, 'horas_restantes': round(horas, 1),
                         'pronto_em': (agora + timedelta(hours=horas)).strftime('%Y-%m-%dT%H:%M') if horas else None}
        return out

    @staticmethod
    def _exercicios_por_regiao(user_id, musculos, nomes, desde):
        """Região -> exercícios que a treinam nos últimos 6 meses, com melhor
        1RM estimado, último treino e força retida do exercício."""
        linhas = (db.session.query(RegistroTreino.exercicio_base_id, RegistroTreino.exercicio_usuario_id,
                                   RegistroTreino.data_registro, RegistroTreino.created_at,
                                   HistoricoTreino.carga, HistoricoTreino.repeticoes)
                  .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)
                  .filter(RegistroTreino.user_id == user_id,
                          RegistroTreino.data_registro >= datetime.combine(desde, datetime.min.time()),
                          RegistroTreino.data_registro <= datetime.combine(_hoje(), datetime.min.time()),
                          HistoricoTreino.duracao_segundos.is_(None)))
        por_ex = {}
        for b, u, dia, criado, carga, reps in linhas:
            k = MapaMuscularService._chave(b, u)
            e = por_ex.setdefault(k, {'e1rm': None, 'momento': None})
            momento = _momento_do_treino(dia, criado)
            if e['momento'] is None or momento > e['momento']:
                e['momento'] = momento
            if carga and reps and 1 <= int(reps) <= REPS_MAX_1RM and float(carga) > 0:
                v = e1rm(carga, reps)
                if e['e1rm'] is None or v > e['e1rm']:
                    e['e1rm'] = v
        agora = _agora()
        out = {}
        for k, e in por_ex.items():
            principal, secundarios = musculos.get(k, (None, []))
            nome = nomes.get(k)
            if not nome:
                continue
            dias = (agora - e['momento']).total_seconds() / 86400
            base = {'nome': nome, 'e1rm': round(e['e1rm'], 1) if e['e1rm'] else None,
                    'data': e['momento'].strftime('%Y-%m-%d'), 'retida': round(forca_retida(dias), 3)}
            for regiao, papel in ([(principal, 'principal')] if principal else []) + \
                    [(r, 'secundario') for r in secundarios]:
                out.setdefault(regiao, []).append({**base, 'papel': papel})
        for lista in out.values():
            lista.sort(key=lambda x: (x['papel'] != 'principal', -(x['e1rm'] or 0), x['nome']))
            del lista[8:]
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
