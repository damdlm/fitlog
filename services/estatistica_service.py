"""Serviço para cálculos estatísticos"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from models import db, Musculo, ExercicioCustomizado, ExercicioSistema, RegistroTreino, HistoricoTreino
from sqlalchemy import func, and_
from .base_service import BaseService, CacheService
import logging

logger = logging.getLogger(__name__)

# TTL curto para os agregados desta tela (musculo/treino/progresso) —
# mesma ideia já usada em FitBotContextService._contexto_estatisticas
# (cache_key com user_id embutido, sem invalidação explícita: um treino
# novo só refletir aqui com até 60s de atraso é aceitável para uma tela
# de estatística, e evita recalcular os JOINs/GROUP BY a cada visita).
ESTATISTICA_CACHE_TTL_SEGUNDOS = 60

class EstatisticaService(BaseService):
    """Gerencia cálculos estatísticos"""
    
    @staticmethod
    def calcular_por_musculo(user_id=None):
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
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}

            cache_key = f"estatistica:{user_id}:por_musculo"
            cache_hit = CacheService.get(cache_key)
            if cache_hit is not None:
                return cache_hit

            # --- Exercícios personalizados (via tabela Musculo) ---
            personalizados = db.session.query(
                Musculo.nome_exibicao.label('musculo'),
                db.func.count(db.distinct(ExercicioCustomizado.id)).label('qtd_exercicios'),
                db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                db.func.count(HistoricoTreino.id).label('total_series'),
                db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
            ).select_from(Musculo)\
             .outerjoin(ExercicioCustomizado, and_(ExercicioCustomizado.musculo_id == Musculo.id, ExercicioCustomizado.usuario_id == user_id))\
             .outerjoin(RegistroTreino, and_(RegistroTreino.exercicio_usuario_id == ExercicioCustomizado.id, RegistroTreino.user_id == user_id))\
             .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .group_by(Musculo.id, Musculo.nome_exibicao)\
             .all()

            # --- Exercícios do catálogo do sistema (via grupo_muscular) ---
            do_catalogo = db.session.query(
                ExercicioSistema.grupo_muscular.label('musculo'),
                db.func.count(db.distinct(ExercicioSistema.id)).label('qtd_exercicios'),
                db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                db.func.count(HistoricoTreino.id).label('total_series'),
                db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
            ).select_from(RegistroTreino)\
             .join(ExercicioSistema, ExercicioSistema.id == RegistroTreino.exercicio_base_id)\
             .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .filter(RegistroTreino.user_id == user_id)\
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

            CacheService.set(cache_key, stats, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return stats
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular estatísticas por músculo")
            return {}
    
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
                    RegistroTreino.treino_id.label('treino_id'),
                    db.func.count(db.distinct(RegistroTreino.exercicio_usuario_id)).label('qtd_ex_personalizados'),
                    db.func.count(db.distinct(RegistroTreino.exercicio_base_id)).label('qtd_ex_sistema'),
                    db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                    db.func.count(HistoricoTreino.id).label('total_series'),
                    db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
                ).select_from(RegistroTreino)\
                 .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
                 .filter(RegistroTreino.user_id == user_id_resolvido)\
                 .group_by(RegistroTreino.treino_id)\
                 .all()
                agregados_por_treino = {a.treino_id: a for a in agregados}

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
                query = query.filter(RegistroTreino.treino_id == treino_id)
            
            resultado = query.order_by(RegistroTreino.periodo, RegistroTreino.semana).all()
            CacheService.set(cache_key, resultado, ttl_seconds=ESTATISTICA_CACHE_TTL_SEGUNDOS)
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular progresso por semana")
            return []

    @staticmethod
    def get_progresso_ultimos_30_dias(treino_id=None, user_id=None):
        """
        Retorna volume total agregado por dia, apenas dos últimos 30 dias
        corridos (calendário real, via RegistroTreino.data_registro) —
        usado no gráfico "Evolução do Volume" da tela de estatísticas.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

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
                query = query.filter(RegistroTreino.treino_id == treino_id)

            return query.order_by(func.date(RegistroTreino.data_registro)).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular progresso dos últimos 30 dias")
            return []

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
                        'treino_id': r.treino_id,
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