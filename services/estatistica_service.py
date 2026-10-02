"""Serviço para cálculos estatísticos"""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from models import db, Musculo, ExercicioCustomizado, ExercicioSistema, RegistroTreino, HistoricoTreino, TreinoVersao
from sqlalchemy import func, and_
from .base_service import BaseService, CacheService
import logging

logger = logging.getLogger(__name__)

_FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


def _hora_local(dt):
    """Hora do dia (0-23) de um datetime, convertido para o fuso de
    Brasília -- data_registro é gravado em UTC (ver
    RegistroService.criar_registro), então usar .hour direto ficaria até
    3h adiantado em relação ao horário real em que a pessoa treinou."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_FUSO_BRASIL).hour


# TTL curto para os agregados desta tela (musculo/treino/progresso) —
# mesma ideia já usada em FitBotContextService._contexto_estatisticas
# (cache_key com user_id embutido, sem invalidação explícita: um treino
# novo só refletir aqui com até 60s de atraso é aceitável para uma tela
# de estatística, e evita recalcular os JOINs/GROUP BY a cada visita).
ESTATISTICA_CACHE_TTL_SEGUNDOS = 60

class EstatisticaService(BaseService):
    """Gerencia cálculos estatísticos"""
    
    @staticmethod
    def calcular_por_musculo(user_id=None, data_inicio=None, data_fim=None):
        """
        Calcula estatísticas por músculo, somando as duas origens possíveis
        de exercício em RegistroTreino:

          - exercicio_usuario_id -> exercícios personalizados, cujo músculo
            vem da tabela Musculo (musculo_id em ExercicioUsuario);
          - exercicio_base_id -> exercícios do catálogo do sistema, cujo
            músculo vem direto de ExercicioSistema.grupo_muscular (essa
            tabela não tem FK para Musculo).

        As duas taxonomias de nome de músculo não são idênticas (a tabela
        Musculo usa grupos amplos em pt-BR; grupo_muscular do catálogo é
        mais granular), então o resultado mescla as duas por nome -- cada
        nome de músculo que aparecer em qualquer uma das origens vira uma
        chave do dicionário retornado.

        `data_inicio`/`data_fim` (datetime, opcionais) restringem os
        registros somados a um período -- usado pelo filtro de período do
        quadro "Volume/Ranking por Músculo" na página do calendário. O
        filtro de data entra na condição do OUTER JOIN (não em .filter()),
        pra continuar trazendo músculos com 0 registros no período em vez
        de sumir da lista. Com filtro de período, o resultado não é
        cacheado (chave variaria por período, e o cálculo já é uma
        agregação SQL única, barata).
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}

            usa_cache = data_inicio is None and data_fim is None
            cache_key = f"estatistica:{user_id}:por_musculo"
            if usa_cache:
                cache_hit = CacheService.get(cache_key)
                if cache_hit is not None:
                    return cache_hit

            condicao_periodo_registro = []
            if data_inicio is not None:
                condicao_periodo_registro.append(RegistroTreino.data_registro >= data_inicio)
            if data_fim is not None:
                condicao_periodo_registro.append(RegistroTreino.data_registro <= data_fim)

            # --- Exercícios personalizados (via tabela Musculo) ---
            personalizados = db.session.query(
                Musculo.nome_exibicao.label('musculo'),
                db.func.count(db.distinct(ExercicioCustomizado.id)).label('qtd_exercicios'),
                db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                db.func.count(HistoricoTreino.id).label('total_series'),
                db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
            ).select_from(Musculo)\
             .outerjoin(ExercicioCustomizado, and_(ExercicioCustomizado.musculo_id == Musculo.id, ExercicioCustomizado.usuario_id == user_id))\
             .outerjoin(RegistroTreino, and_(RegistroTreino.exercicio_usuario_id == ExercicioCustomizado.id, RegistroTreino.user_id == user_id, *condicao_periodo_registro))\
             .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .group_by(Musculo.id, Musculo.nome_exibicao)\
             .all()

            # --- Exercícios do catálogo do sistema (via grupo_muscular) ---
            filtro_catalogo = [RegistroTreino.user_id == user_id] + condicao_periodo_registro
            do_catalogo = db.session.query(
                ExercicioSistema.grupo_muscular.label('musculo'),
                db.func.count(db.distinct(ExercicioSistema.id)).label('qtd_exercicios'),
                db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                db.func.count(HistoricoTreino.id).label('total_series'),
                db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
            ).select_from(RegistroTreino)\
             .join(ExercicioSistema, ExercicioSistema.id == RegistroTreino.exercicio_base_id)\
             .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .filter(*filtro_catalogo)\
             .group_by(ExercicioSistema.grupo_muscular)\
             .all()

            stats = {}
            for r in personalizados:
                stats[r.musculo] = {
                    'qtd_exercicios': r.qtd_exercicios,
                    'qtd_registros': r.qtd_registros,
                    'total_series': r.total_series,
                    'volume_total': float(r.volume_total)
                }

            for r in do_catalogo:
                nome = r.musculo or 'Não especificado'
                atual = stats.get(nome, {
                    'qtd_exercicios': 0, 'qtd_registros': 0,
                    'total_series': 0, 'volume_total': 0.0
                })
                atual['qtd_exercicios'] += r.qtd_exercicios
                atual['qtd_registros'] += r.qtd_registros
                atual['total_series'] += r.total_series
                atual['volume_total'] += float(r.volume_total)
                stats[nome] = atual

            if usa_cache:
                CacheService.set(cache_key, stats, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return stats
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular estatísticas por músculo")
            return {}

    @staticmethod
    def calcular_kpis_periodo(user_id=None, dias=30):
        """
        KPIs do período com comparação ao período imediatamente anterior de
        mesmo tamanho (ex: últimos 30 dias vs. os 30 dias antes deles) --
        o padrão de "trend" usado por dashboards de treino sérios (Strava,
        Hevy Pro) em vez de só mostrar o número absoluto isolado.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None

            agora = datetime.now(timezone.utc)
            inicio_atual = agora - timedelta(days=dias)
            inicio_anterior = agora - timedelta(days=dias * 2)

            def agregados(inicio, fim):
                row = db.session.query(
                    db.func.count(db.distinct(RegistroTreino.id)).label('treinos'),
                    db.func.count(HistoricoTreino.id).label('series'),
                    db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume')
                ).select_from(RegistroTreino)\
                 .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
                 .filter(
                     RegistroTreino.user_id == user_id,
                     RegistroTreino.data_registro >= inicio,
                     RegistroTreino.data_registro < fim
                 ).first()
                return {
                    'treinos': row.treinos or 0,
                    'series': row.series or 0,
                    'volume': float(row.volume or 0)
                }

            atual = agregados(inicio_atual, agora)
            anterior = agregados(inicio_anterior, inicio_atual)

            def variacao_pct(novo, velho):
                if velho == 0:
                    return None if novo == 0 else 100.0
                return round(((novo - velho) / velho) * 100, 1)

            return {
                'dias': dias,
                'volume_total': atual['volume'],
                'volume_variacao': variacao_pct(atual['volume'], anterior['volume']),
                'treinos_realizados': atual['treinos'],
                'treinos_variacao': variacao_pct(atual['treinos'], anterior['treinos']),
                'total_series': atual['series'],
                'series_variacao': variacao_pct(atual['series'], anterior['series']),
            }
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular KPIs do período")
            return None

    @staticmethod
    def progressao_forca_exercicio(exercicio_tipo, exercicio_id, user_id=None):
        """
        Progressão de 1RM estimado (fórmula de Epley: rm = carga * (1 +
        repeticoes/30), a mesma usada por calculadoras de força validadas
        pela NSCA) de um único exercício ao longo do tempo -- um ponto por
        sessão (o maior 1RM estimado entre as séries daquela sessão), não
        por série, pra não distorcer o gráfico com séries de aquecimento.

        `exercicio_tipo` é 'usuario' ou 'base' -- ver comentário em
        preparar_dados_tabela sobre por que a chave precisa do tipo junto
        (IDs de exercício personalizado e de sistema vêm de sequências
        independentes e podem coincidir em número).
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            if exercicio_tipo == 'usuario':
                filtro_exercicio = RegistroTreino.exercicio_usuario_id == exercicio_id
            elif exercicio_tipo == 'base':
                filtro_exercicio = RegistroTreino.exercicio_base_id == exercicio_id
            else:
                return []

            registros = db.session.query(RegistroTreino)\
                .options(joinedload(RegistroTreino.series))\
                .filter(RegistroTreino.user_id == user_id, filtro_exercicio)\
                .order_by(RegistroTreino.data_registro.asc())\
                .all()

            pontos = []
            for r in registros:
                melhor_rm = 0.0
                for s in r.series:
                    if not s.carga or not s.repeticoes:
                        continue
                    rm = float(s.carga) * (1 + s.repeticoes / 30.0)
                    if rm > melhor_rm:
                        melhor_rm = rm
                if melhor_rm > 0:
                    pontos.append({
                        'data': r.data_registro,
                        'rm_estimado': round(melhor_rm, 1)
                    })
            return pontos
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao calcular progressão de força do exercício {exercicio_id}")
            return []

    @staticmethod
    def calcular_recordes_pessoais(user_id=None, dias_recentes=60, limite=6):
        """
        Recordes pessoais (PRs): para cada exercício já registrado pelo
        usuário, o maior 1RM estimado (Epley) de toda a história e a data
        em que foi batido. Retorna só os PRs batidos nos últimos
        `dias_recentes` dias, mais recentes primeiro -- é o "feed de
        conquistas", não a lista completa de melhores marcas.

        Varre o histórico completo em Python (mesmo espírito de
        preparar_dados_tabela): achar o máximo por grupo E a data em que
        ele ocorreu não é uma agregação SQL simples (precisaria de window
        function), e o volume por usuário já foi medido como tratável
        nesse formato (~2.400 registros/9.700 séries, ver comentário em
        calcular_por_treino).
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            registros = db.session.query(RegistroTreino)\
                .options(
                    joinedload(RegistroTreino.series),
                    joinedload(RegistroTreino.exercicio),
                    joinedload(RegistroTreino.exercicio_base)
                )\
                .filter(RegistroTreino.user_id == user_id)\
                .order_by(RegistroTreino.data_registro.asc())\
                .all()

            melhor_por_exercicio = {}
            for r in registros:
                nome = None
                if r.exercicio_usuario_id and r.exercicio:
                    nome = r.exercicio.nome
                elif r.exercicio_base_id and r.exercicio_base:
                    nome = r.exercicio_base.nome
                if not nome:
                    continue

                chave = f"{'usuario' if r.exercicio_usuario_id else 'base'}_{r.exercicio_usuario_id or r.exercicio_base_id}"

                for s in r.series:
                    if not s.carga or not s.repeticoes:
                        continue
                    rm = float(s.carga) * (1 + s.repeticoes / 30.0)
                    atual = melhor_por_exercicio.get(chave)
                    if atual is None or rm > atual['rm']:
                        melhor_por_exercicio[chave] = {
                            'nome': nome,
                            'rm': rm,
                            'data': r.data_registro,
                            'carga': float(s.carga),
                            'reps': s.repeticoes
                        }

            limite_data = datetime.now(timezone.utc) - timedelta(days=dias_recentes)
            recentes = []
            for v in melhor_por_exercicio.values():
                data_registro = v['data']
                if data_registro and data_registro.tzinfo is None:
                    data_registro = data_registro.replace(tzinfo=timezone.utc)
                if data_registro and data_registro >= limite_data:
                    recentes.append(v)

            recentes.sort(key=lambda v: v['data'], reverse=True)
            return recentes[:limite]
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular recordes pessoais")
            return []
    
    @staticmethod
    def calcular_por_treino(user_id=None):
        """
        Calcula estatísticas por treino.

        Agrega em SQL (GROUP BY treino_id) em vez de carregar todos os
        registros do usuário com suas séries via ORM (RegistroService
        .get_all(..., load_series=True)) e somar em Python — mesmo
        espírito da agregação já usada em calcular_por_musculo. Em
        benchmark com ~2.400 registros/9.700 séries essa era a operação
        mais cara da tela de estatísticas (~240ms a frio), bem acima das
        outras duas (~7ms cada), justamente por materializar todo o
        histórico como objetos Python antes de somar.

        exercicio_usuario_id e exercicio_base_id são mutuamente exclusivos
        por constraint de banco (check_registro_exactly_one_exercicio: um
        RegistroTreino nunca tem os dois preenchidos ao mesmo tempo), então
        contar distinct de cada coluna separadamente e somar os totais dá
        o mesmo resultado que o set() de pares (exercicio_usuario_id,
        exercicio_base_id) usado antes — sem risco da colisão que esse par
        evitava (IDs de exercício personalizado e de sistema vêm de
        sequências independentes e podem coincidir em número).
        """
        try:
            from .treino_service import TreinoService

            user_id_resolvido = user_id or BaseService.get_current_user_id()
            cache_key = f"estatistica:{user_id_resolvido}:por_treino"
            if user_id_resolvido:
                cache_hit = CacheService.get(cache_key)
                if cache_hit is not None:
                    return cache_hit

            treinos = TreinoService.get_all(user_id)

            agregados_por_treino = {}
            if user_id_resolvido:
                agregados = db.session.query(
                    RegistroTreino.treino_versao_id.label('treino_versao_id'),
                    db.func.count(db.distinct(RegistroTreino.exercicio_usuario_id)).label('qtd_ex_personalizados'),
                    db.func.count(db.distinct(RegistroTreino.exercicio_base_id)).label('qtd_ex_sistema'),
                    db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                    db.func.count(HistoricoTreino.id).label('total_series'),
                    db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
                ).select_from(RegistroTreino)\
                 .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
                 .filter(RegistroTreino.user_id == user_id_resolvido)\
                 .group_by(RegistroTreino.treino_versao_id)\
                 .all()
                agregados_por_treino = {a.treino_versao_id: a for a in agregados}

            treino_stats = {}
            for t in treinos:
                a = agregados_por_treino.get(t.id)
                treino_stats[t.id] = {
                    "codigo": t.codigo,
                    "nome": t.nome,
                    "descricao": t.descricao,
                    "qtd_exercicios": (a.qtd_ex_personalizados + a.qtd_ex_sistema) if a else 0,
                    "qtd_registros": a.qtd_registros if a else 0,
                    "volume_total": float(a.volume_total) if a else 0.0,
                    "total_series": a.total_series if a else 0
                }
            
            if user_id_resolvido:
                CacheService.set(cache_key, treino_stats, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return treino_stats
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular estatísticas por treino")
            return {}
    
    @staticmethod
    def get_progresso_por_semana(treino_id=None, user_id=None):
        """Retorna dados de progresso agregados por semana"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            cache_key = f"estatistica:{user_id}:progresso_semana:{treino_id or 'todos'}"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            query = db.session.query(
                RegistroTreino.periodo,
                RegistroTreino.semana,
                db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes).label('volume_total'),
                db.func.avg(HistoricoTreino.carga).label('carga_media')
            ).join(HistoricoTreino)\
             .filter(RegistroTreino.user_id == user_id)\
             .group_by(RegistroTreino.periodo, RegistroTreino.semana)
            
            if treino_id:
                query = query.filter(RegistroTreino.treino_versao_id == treino_id)
            
            resultado = query.order_by(RegistroTreino.periodo, RegistroTreino.semana).all()
            CacheService.set(cache_key, resultado, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular progresso por semana")
            return []

    @staticmethod
    def get_progresso_ultimos_30_dias(treino_id=None, user_id=None, versao_id=None):
        """
        Retorna volume total agregado por dia, apenas dos últimos 30 dias
        corridos (calendário real, via RegistroTreino.data_registro) —
        usado no gráfico "Evolução do Volume" da tela de estatísticas.

        versao_id (opcional): restringe o cálculo aos registros de uma
        versão específica. Ignorado se treino_id for informado (um
        treino_versao_id já pertence a uma única versão). Usado pelo
        dashboard (routes/api_routes.py) para o filtro "Todos" mostrar
        só a versão corrente -- sem isso, "Todos" somava o histórico
        inteiro do usuário, de todas as versões já encerradas também.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            cache_key = f"estatistica:{user_id}:progresso_30d:{treino_id or 'todos'}:{versao_id or '-'}"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            limite = datetime.now(timezone.utc) - timedelta(days=30)

            query = db.session.query(
                func.date(RegistroTreino.data_registro).label('dia'),
                func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes).label('volume_total'),
                func.avg(HistoricoTreino.carga).label('carga_media')
            ).join(HistoricoTreino)\
             .filter(RegistroTreino.user_id == user_id)\
             .filter(RegistroTreino.data_registro >= limite)\
             .group_by(func.date(RegistroTreino.data_registro))

            if treino_id:
                query = query.filter(RegistroTreino.treino_versao_id == treino_id)
            elif versao_id:
                query = query.filter(RegistroTreino.versao_id == versao_id)

            resultado = query.order_by(func.date(RegistroTreino.data_registro)).all()
            CacheService.set(cache_key, resultado, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular progresso dos últimos 30 dias")
            return []

    @staticmethod
    def get_sessoes_ultimos_30_dias(versao_id=None, user_id=None):
        """
        Sessões de treino dos últimos 30 dias corridos, uma linha por
        (dia, treino): volume (carga x repetições somado em todas as
        séries), soma das cargas e nº de séries. Base do gráfico
        agregado "por semana" / "por treino" do dashboard.

        Junta TODAS as versões que tiveram treino na janela e identifica
        o treino pela letra (A, B, C...), não pelo id: quando a versão
        troca ou expira no meio dos 30 dias, os treinos da versão
        anterior continuam contando -- o A da versão 1 e o A da versão 2
        são o mesmo "A" do ponto de vista de quem treina.

        Devolve {'sessoes': [...], 'treinos': [...]}, onde 'treinos' são
        as letras da versão ativa (versao_id, se informado) mais qualquer
        letra treinada na janela, em ordem -- necessário pra mostrar o
        treino que não foi feito como 0, em vez de sumir.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {'sessoes': [], 'treinos': []}

            hoje = EstatisticaService.hoje_brasil()
            cache_key = f"estatistica:{user_id}:sessoes_30d:{versao_id or 0}:{hoje.isoformat()}"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            inicio_janela = datetime.combine(hoje - timedelta(days=29), time.min)

            dia = func.date(RegistroTreino.data_registro)
            linhas = db.session.query(
                dia.label('dia'),
                TreinoVersao.codigo.label('codigo'),
                func.min(RegistroTreino.data_registro).label('inicio'),
                func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes).label('volume'),
                func.sum(HistoricoTreino.carga).label('soma_carga'),
                func.count(HistoricoTreino.id).label('n_series'),
            ).select_from(RegistroTreino)\
             .join(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .join(TreinoVersao, TreinoVersao.id == RegistroTreino.treino_versao_id)\
             .filter(RegistroTreino.user_id == user_id)\
             .filter(RegistroTreino.data_registro >= inicio_janela)\
             .group_by(dia, TreinoVersao.codigo).all()

            sessoes = []
            for l in linhas:
                d = l.dia if isinstance(l.dia, date) else datetime.strptime(str(l.dia)[:10], "%Y-%m-%d").date()
                inicio = l.inicio if isinstance(l.inicio, datetime) else datetime.combine(d, time.min)
                sessoes.append({
                    'dia': d,
                    'inicio': inicio,
                    'treino': l.codigo,
                    'volume': float(l.volume or 0),
                    'soma_carga': float(l.soma_carga or 0),
                    'n_series': int(l.n_series or 0),
                })

            codigos = []
            if versao_id:
                codigos = [
                    t.codigo for t in TreinoVersao.query.filter_by(versao_id=versao_id)
                    .order_by(TreinoVersao.ordem, TreinoVersao.codigo).all()
                ]
            for c in sorted({s['treino'] for s in sessoes}):
                if c not in codigos:
                    codigos.append(c)

            resultado = {'sessoes': sessoes, 'treinos': [{'codigo': c} for c in codigos]}
            CacheService.set(cache_key, resultado, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular sessões dos últimos 30 dias")
            return {'sessoes': [], 'treinos': []}

    @staticmethod
    def hoje_brasil():
        """Data de hoje no fuso do Brasil (os treinos são lançados com a
        data local do aluno; usar UTC adianta o "hoje" em 1 dia à noite)."""
        return datetime.now(_FUSO_BRASIL).date()

    @staticmethod
    def agregar_progresso(sessoes, treinos, modo, treino=None, hoje=None):
        """
        Agrega as sessões (ver get_sessoes_ultimos_30_dias) num gráfico de
        volume total (peso x repetições x séries) por:

        - modo='semana': semana do calendário (segunda a domingo) dentro
          dos últimos 30 dias. Semana sem treino aparece com 0 (exceto pedaço de semana
          nas pontas da janela, se vazio). Soma só
          os treinos feitos naquela semana (ex: A, B e D numa semana; A,
          C e D na seguinte).
        - modo='treino': "rodada" completa do treino (A+B+C+D). Uma nova
          rodada começa quando um treino já feito na rodada atual é
          repetido (fez A, B, D e voltou pro A -> o 2º A abre a rodada
          seguinte). Treino não feito na rodada entra como 0.

        treino (opcional, letra: 'A', 'B'...): só o volume daquele treino
        em cada ponto (a divisão em rodadas continua sendo por todos os
        treinos).
        Função pura (sem banco) -- fácil de testar.
        """
        hoje = hoje or EstatisticaService.hoje_brasil()
        inicio = hoje - timedelta(days=29)

        def fmt(d):
            return d.strftime("%d/%m")

        def faixa(a, b):
            return fmt(a) if a == b else f"{fmt(a)}–{fmt(b)}"

        def somar(grupo):
            """(volume, carga_media, detalhes, sessoes_por_treino) de uma
            lista de sessões. sessoes_por_treino traz, pra CADA treino que
            apareceu no grupo (independente do filtro `treino`), o
            suficiente pro modal de detalhe abrir ao clicar numa barra:
            volume, carga média, nº de séries e os dias em que foi feito."""
            por_treino = {}
            for s in grupo:
                por_treino[s['treino']] = por_treino.get(s['treino'], 0.0) + s['volume']
            alvo = [s for s in grupo if treino is None or s['treino'] == treino]
            volume = sum(s['volume'] for s in alvo)
            n = sum(s['n_series'] for s in alvo)
            carga_media = (sum(s['soma_carga'] for s in alvo) / n) if n else 0.0
            detalhes = []
            if treino is None:
                detalhes = [
                    {'codigo': t['codigo'], 'volume': round(por_treino.get(t['codigo'], 0.0), 2)}
                    for t in treinos
                ]

            sessoes_por_treino = {}
            for codigo in {s['treino'] for s in grupo}:
                do_treino = [s for s in grupo if s['treino'] == codigo]
                n_t = sum(s['n_series'] for s in do_treino)
                sessoes_por_treino[codigo] = {
                    'volume': round(sum(s['volume'] for s in do_treino), 2),
                    'carga_media': round((sum(s['soma_carga'] for s in do_treino) / n_t) if n_t else 0.0, 2),
                    'n_series': n_t,
                    'dias': sorted({s['dia'].isoformat() for s in do_treino}),
                }

            return round(volume, 2), round(carga_media, 2), detalhes, sessoes_por_treino

        pontos = []  # (rotulo, grupo de sessões)
        sessoes = [s for s in sessoes if inicio <= s['dia'] <= hoje]

        if modo == 'semana':
            seg = inicio - timedelta(days=inicio.weekday())
            while seg <= hoje:
                fim = seg + timedelta(days=6)
                grupo = [s for s in sessoes if seg <= s['dia'] <= fim]
                de, ate = max(seg, inicio), min(fim, hoje)
                # Semana das pontas cortada pela janela (menos de 7 dias) e
                # sem nenhum treino: não é uma semana "sem treinar", é só
                # um pedaço -- entra como ponto zerado e derruba a linha.
                parcial_vazia = (ate - de).days < 6 and not grupo
                if not parcial_vazia:
                    pontos.append((faixa(de, ate), grupo))
                seg += timedelta(days=7)
        else:  # 'treino'
            rodadas, atual, feitos = [], [], set()
            for s in sorted(sessoes, key=lambda x: (x['inicio'], x['treino'])):
                if s['treino'] in feitos:
                    rodadas.append(atual)
                    atual, feitos = [], set()
                atual.append(s)
                feitos.add(s['treino'])
            if atual:
                rodadas.append(atual)
            for r in rodadas:
                dias = [s['dia'] for s in r]
                pontos.append((faixa(min(dias), max(dias)), r))

        if not sessoes:
            return {'semanas': [], 'volumes': [], 'cargas_medias': [], 'detalhes': [], 'sessoes_por_treino': []}

        rotulos, volumes, cargas, detalhes, sessoes_por_treino = [], [], [], [], []
        for rotulo, grupo in pontos:
            v, c, d, spt = somar(grupo)
            rotulos.append(rotulo)
            volumes.append(v)
            cargas.append(c)
            detalhes.append(d)
            sessoes_por_treino.append(spt)
        return {
            'semanas': rotulos, 'volumes': volumes, 'cargas_medias': cargas,
            'detalhes': detalhes, 'sessoes_por_treino': sessoes_por_treino,
        }

    @staticmethod
    def get_atividade_geral(user_id=None, dias=30):
        """
        Números concretos de atividade nos últimos `dias` dias: quantos
        treinos foram realizados, quantas séries, quantas repetições no
        total, e a duração/horário das sessões.

        A duração vem do cronômetro real do topo da tela de registro
        (HistoricoTreino.tempo_treino, salvo na 1ª série de cada
        RegistroTreino) -- o mesmo dado já usado no dashboard (ver
        routes/aluno/main.py). Antes esta função estimava a duração
        pelo intervalo entre o primeiro e o último exercício registrado
        no dia; com o cronômetro real disponível, isso não é mais
        necessário nem tão preciso.

        Usado no card "Atividade" da tela de estatísticas.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None

            cache_key = f"estatistica:{user_id}:atividade_geral:{dias}"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            limite = datetime.now(timezone.utc) - timedelta(days=dias)

            registros = RegistroTreino.query.filter(
                RegistroTreino.user_id == user_id,
                RegistroTreino.data_registro >= limite
            ).options(joinedload(RegistroTreino.series)).all()

            sessoes = set()
            tempo_por_sessao = {}
            hora_por_sessao = {}
            total_series = 0
            total_repeticoes = 0

            for r in registros:
                chave_sessao = (r.data_registro.date(), r.treino_versao_id)
                sessoes.add(chave_sessao)

                for serie in r.series:
                    total_series += 1
                    total_repeticoes += serie.repeticoes or 0
                    # tempo_treino é gravado igual em todas as séries da
                    # mesma sessão (é o cronômetro do topo, não por
                    # série) -- o max() aqui é só defensivo.
                    if serie.tempo_treino and serie.tempo_treino > tempo_por_sessao.get(chave_sessao, 0):
                        tempo_por_sessao[chave_sessao] = serie.tempo_treino
                        hora_por_sessao[chave_sessao] = _hora_local(r.data_registro)

            buckets = {'Manhã': 0, 'Tarde': 0, 'Noite': 0}
            for hora in hora_por_sessao.values():
                if 5 <= hora < 12:
                    buckets['Manhã'] += 1
                elif 12 <= hora < 18:
                    buckets['Tarde'] += 1
                else:
                    buckets['Noite'] += 1

            duracoes_min = [t / 60 for t in tempo_por_sessao.values()]

            resultado = {
                'treinos_realizados': len(sessoes),
                'total_series': total_series,
                'total_repeticoes': total_repeticoes,
                'duracao_media_min': round(sum(duracoes_min) / len(duracoes_min)) if duracoes_min else None,
                'tempo_total_min': round(sum(duracoes_min)) if duracoes_min else None,
                'sessoes_com_duracao': len(duracoes_min),
                'horario_mais_comum': max(buckets, key=buckets.get) if any(buckets.values()) else None,
                'distribuicao_horario': buckets,
            }

            CacheService.set(cache_key, resultado, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular atividade geral")
            return None

    @staticmethod
    def preparar_dados_tabela(exercicios, registros, semanas_filtro, request_args):
        """Prepara dados para a tabela de visualização"""
        try:
            # Criar dicionário de registros por exercício
            # Não usar só ex.id como chave: um ExercicioUsuario e um
            # ExercicioSistema podem ter o mesmo id numérico (tabelas
            # diferentes, sequências independentes) -- ex.tipo ('usuario'
            # ou 'base', setado em ExercicioService.get_exercicios_completos)
            # desambigua, no mesmo espírito da correção já feita em
            # calcular_por_treino/aluno/stats.py/professor_routes.py.
            # Chave em string (não tupla) para o template conseguir montar
            # a mesma chave com `exercicio.tipo ~ '_' ~ exercicio.id`.
            registros_por_exercicio = {}
            for ex in exercicios:
                registros_por_exercicio[f"{ex.tipo}_{ex.id}"] = {}

            for r in registros:
                tipo_registro = 'base' if r.exercicio_base_id else 'usuario'
                id_registro = r.exercicio_base_id or r.exercicio_usuario_id
                chave_exercicio = f"{tipo_registro}_{id_registro}"
                if chave_exercicio in registros_por_exercicio:
                    key = f"{r.periodo}_{r.semana}"
                    registros_por_exercicio[chave_exercicio][key] = {
                        'id': r.id,
                        'series': [{'carga': float(s.carga), 'repeticoes': s.repeticoes} for s in r.series],
                        'periodo': r.periodo,
                        'semana': r.semana,
                        'treino_id': r.treino_versao_id,
                        'versao_id': r.versao_id,
                        'data_registro': r.data_registro.isoformat() if r.data_registro else None
                    }
            
            # Coletar todas as semanas
            semanas_set = set()
            for r in registros:
                semanas_set.add((r.periodo, r.semana, f"{r.periodo}_{r.semana}"))
            
            semanas = []
            for periodo, semana, key in semanas_set:
                semanas.append({
                    "periodo": periodo,
                    "semana": semana,
                    "key": key
                })
            
            # Ordenar semanas
            ordem_periodos = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            
            semanas.sort(key=lambda x: (ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999, x["semana"]))
            
            # Filtrar semanas conforme parâmetro
            semanas_filtradas = []
            semanas_selecionadas_lista = []
            
            if semanas_filtro == "ultimas3":
                semanas_filtradas = semanas[-3:]
            elif semanas_filtro == "ultimas5":
                semanas_filtradas = semanas[-5:]
            elif semanas_filtro == "personalizado":
                for periodo, semana, key in semanas_set:
                    if request_args.get(f"semana_{periodo}_{semana}"):
                        semanas_filtradas.append({
                            "periodo": periodo,
                            "semana": semana,
                            "key": key
                        })
                        semanas_selecionadas_lista.append(key)
                if not semanas_filtradas:
                    semanas_filtradas = semanas
            else:
                semanas_filtradas = semanas
            
            semanas_filtradas.sort(key=lambda x: (ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999, x["semana"]))
            
            # Preparar períodos disponíveis para o modal
            #
            # Antes, para cada (período, semana) fazia-se um sum(1 for r in
            # registros if ...) -- ou seja, uma varredura completa da lista
            # de registros por combinação. Com P períodos e S semanas por
            # período, isso é O(P * S * len(registros)); com um Counter
            # feito uma única vez sobre `registros`, cai para O(len(registros)
            # + P * S), sem mudar nenhum resultado.
            contagem_por_periodo_semana = Counter((r.periodo, r.semana) for r in registros)

            periodos_disponiveis = []
            periodos_set = set(s[0] for s in semanas_set)
            for periodo in periodos_set:
                semanas_periodo = sorted([s[1] for s in semanas_set if s[0] == periodo])
                registros_por_semana = {
                    semana: contagem_por_periodo_semana.get((periodo, semana), 0)
                    for semana in semanas_periodo
                }

                periodos_disponiveis.append({
                    "periodo": periodo,
                    "semanas": semanas_periodo,
                    "registros_por_semana": registros_por_semana
                })
            
            periodos_disponiveis.sort(key=lambda x: ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999)
            
            return {
                'semanas': semanas_filtradas,
                'registros_por_exercicio': registros_por_exercicio,
                'semanas_selecionadas_lista': semanas_selecionadas_lista,
                'periodos_disponiveis': periodos_disponiveis
            }
        except Exception as e:
            BaseService.handle_error(e, "Erro ao preparar dados da tabela")
            return {
                'semanas': [],
                'registros_por_exercicio': {},
                'semanas_selecionadas_lista': [],
                'periodos_disponiveis': []
            }