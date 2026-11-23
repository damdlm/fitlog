"""Mapa muscular da tela Progresso (lote 5): volume e recuperação por região.

VOLUME (segue o período escolhido na tela)
  Séries por região do corpo. Cada série de força conta 1 para o músculo
  principal do exercício e 0,5 para cada músculo secundário (a mesma
  convenção de "séries efetivas" usada em planilhas de volume). O volume
  em kg (carga × repetições) entra só no músculo principal, para não
  contar o mesmo peso duas vezes. Cardio fica de fora.

  De onde vem o músculo:
    - catálogo (ExercicioSistema): principal = `alvo`, secundários =
      `musculos_secundarios`. Atenção: `grupo_muscular` NÃO é o principal
      nesse catálogo (no supino reto é "Tríceps"; o alvo é "Peitorais").
    - exercício personalizado (ExercicioUsuario): o músculo escolhido
      (Musculo.nome_exibicao), sem secundários.
  Nomes de músculo que não têm região no desenho (ex: "Sistema
  cardiovascular") são ignorados.

RECUPERAÇÃO (sempre "agora", não segue o período)
  É uma ESTIMATIVA, e a tela diz isso. Olha os últimos 14 dias: o último
  dia em que a região recebeu pelo menos 2 séries efetivas. Janela de
  recuperação: 3 dias para músculos grandes, 2 para os menores (ordem de
  grandeza comum de 48–72 h; varia com intensidade, sono e alimentação).
    - treinado hoje ou dentro da janela -> "recuperando" (faltam N dias)
    - passou a janela                  -> "recuperado"
    - nada em 14 dias                  -> "sem_treino"
"""
import unicodedata
from datetime import timedelta

from sqlalchemy import func

from models import (db, RegistroTreino, HistoricoTreino, ExercicioSistema, ExercicioUsuario, Musculo, User)

# slug -> (nome na tela, janela de recuperação em dias)
REGIOES = {
    'peito': ('Peito', 3),
    'costas': ('Costas', 3),
    'lombar': ('Lombar', 3),
    'trapezio': ('Trapézio', 2),
    'ombros': ('Ombros', 2),
    'biceps': ('Bíceps', 2),
    'triceps': ('Tríceps', 2),
    'antebracos': ('Antebraços', 2),
    'abdomen': ('Abdômen', 2),
    'obliquos': ('Oblíquos', 2),
    'gluteos': ('Glúteos', 3),
    'quadriceps': ('Quadríceps', 3),
    'isquiotibiais': ('Posterior de coxa', 3),
    'adutores': ('Adutores', 2),
    'panturrilhas': ('Panturrilhas', 2),
    'canelas': ('Canelas', 2),
    'pescoco': ('Pescoço', 2),
}

# Nome de músculo (catálogo e tabela Musculo, sem acento e minúsculo) -> região
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


def _sem_acento(texto):
    texto = unicodedata.normalize('NFKD', (texto or '').strip().lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


def regiao_do_musculo(nome):
    return _MUSCULO_REGIAO.get(_sem_acento(nome))


def _hoje():
    from services.estatistica_service import EstatisticaService
    return EstatisticaService.hoje_brasil()


class MapaMuscularService:

    @staticmethod
    def _series_por_registro(user_id, inicio=None, fim=None):
        """Uma linha por registro (exercício no dia): ids do exercício,
        dia, nº de séries de força e volume em kg."""
        q = (db.session.query(RegistroTreino.exercicio_base_id, RegistroTreino.exercicio_usuario_id,
                              RegistroTreino.data_registro,
                              func.count(HistoricoTreino.id),
                              func.coalesce(func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0))
             .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)
             .filter(RegistroTreino.user_id == user_id, HistoricoTreino.duracao_segundos.is_(None)))
        if inicio is not None:
            q = q.filter(RegistroTreino.data_registro >= inicio)
        if fim is not None:
            q = q.filter(RegistroTreino.data_registro <= fim)
        return q.group_by(RegistroTreino.id, RegistroTreino.exercicio_base_id, RegistroTreino.exercicio_usuario_id,
                          RegistroTreino.data_registro).all()

    @staticmethod
    def _musculos_dos_exercicios(linhas):
        """(base_id|None, usuario_id|None) -> (região principal, [regiões secundárias])."""
        ids_b = {b for b, u, *_ in linhas if b}
        ids_u = {u for b, u, *_ in linhas if u}
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
    def calcular(user_id, periodo=None):
        """Dados do mapa. `periodo` é o dict de _periodo_da_requisicao
        (dia_inicio/dia_fim) ou None para todo o histórico."""
        dia_ini = periodo.get('dia_inicio') if periodo else None
        dia_fim = periodo.get('dia_fim') if periodo else None
        from datetime import datetime
        inicio = datetime.combine(dia_ini, datetime.min.time()) if dia_ini else None
        fim = datetime.combine(dia_fim, datetime.min.time()) if dia_fim else None

        regioes = {slug: {'nome': nome, 'series': 0.0, 'volume': 0.0, 'exercicios': {}}
                   for slug, (nome, _) in REGIOES.items()}
        linhas = MapaMuscularService._series_por_registro(user_id, inicio, fim)
        musculos = MapaMuscularService._musculos_dos_exercicios(linhas)
        nomes = MapaMuscularService._nomes_dos_exercicios(linhas)
        for b, u, _dia, series, volume in linhas:
            principal, secundarios = musculos.get((b, None) if b else (None, u), (None, []))
            nome_ex = nomes.get((b, None) if b else (None, u))
            if principal:
                r = regioes[principal]
                r['series'] += series
                r['volume'] += float(volume or 0)
                if nome_ex:
                    r['exercicios'][nome_ex] = r['exercicios'].get(nome_ex, 0) + series
            for s in secundarios:
                regioes[s]['series'] += series * 0.5

        recuperacao = MapaMuscularService._recuperacao(user_id)
        for slug, r in regioes.items():
            r['series'] = round(r['series'], 1)
            r['volume'] = round(r['volume'])
            r['principais'] = [n for n, _ in sorted(r['exercicios'].items(), key=lambda x: -x[1])[:3]]
            del r['exercicios']
            r.update(recuperacao[slug])

        from utils.genero_utils import resolver_genero
        aluno = db.session.get(User, user_id)
        return {
            'genero': 'F' if aluno and resolver_genero(aluno) == 'F' else 'M',
            'regioes': regioes,
            'max_series': max((r['series'] for r in regioes.values()), default=0),
        }

    @staticmethod
    def _nomes_dos_exercicios(linhas):
        ids_b = {b for b, u, *_ in linhas if b}
        ids_u = {u for b, u, *_ in linhas if u}
        nomes = {}
        if ids_b:
            nomes.update({(i, None): n for i, n in db.session.query(ExercicioSistema.id, ExercicioSistema.nome)
                          .filter(ExercicioSistema.id.in_(ids_b))})
        if ids_u:
            nomes.update({(None, i): n for i, n in db.session.query(ExercicioUsuario.id, ExercicioUsuario.nome)
                          .filter(ExercicioUsuario.id.in_(ids_u))})
        return nomes

    @staticmethod
    def _recuperacao(user_id):
        """Ver RECUPERAÇÃO no docstring do módulo."""
        from datetime import datetime
        hoje = _hoje()
        inicio = datetime.combine(hoje - timedelta(days=DIAS_RECUPERACAO_OLHADOS - 1), datetime.min.time())
        fim = datetime.combine(hoje, datetime.min.time())
        linhas = MapaMuscularService._series_por_registro(user_id, inicio, fim)
        musculos = MapaMuscularService._musculos_dos_exercicios(linhas)

        por_dia = {}  # (região, dia) -> séries efetivas
        for b, u, dia, series, _v in linhas:
            principal, secundarios = musculos.get((b, None) if b else (None, u), (None, []))
            d = dia.date() if hasattr(dia, 'date') else dia
            if principal:
                por_dia[(principal, d)] = por_dia.get((principal, d), 0) + series
            for s in secundarios:
                por_dia[(s, d)] = por_dia.get((s, d), 0) + series * 0.5

        ultimo = {}
        for (regiao, d), series in por_dia.items():
            if series >= SERIES_MINIMAS_RECUPERACAO and (regiao not in ultimo or d > ultimo[regiao]):
                ultimo[regiao] = d

        out = {}
        for slug, (_nome, janela) in REGIOES.items():
            d = ultimo.get(slug)
            if d is None:
                out[slug] = {'status': 'sem_treino', 'dias_desde': None, 'faltam': None, 'janela': janela}
                continue
            dias = (hoje - d).days
            faltam = max(0, janela - dias)
            out[slug] = {'status': 'recuperando' if faltam else 'recuperado', 'dias_desde': dias,
                         'faltam': faltam, 'janela': janela}
        return out
