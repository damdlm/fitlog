"""Serviço para cálculos estatísticos"""

from models import db, Musculo, ExercicioCustomizado, RegistroTreino, HistoricoTreino
from sqlalchemy import func, and_
from .base_service import BaseService
import logging

logger = logging.getLogger(__name__)

class EstatisticaService(BaseService):
    """Gerencia cálculos estatísticos"""
    
    @staticmethod
    def calcular_por_musculo(user_id=None):
        """Calcula estatísticas por músculo"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}
            
            resultado = db.session.query(
                Musculo.nome_exibicao.label('musculo'),
                db.func.count(db.distinct(ExercicioCustomizado.id)).label('qtd_exercicios'),
                db.func.count(db.distinct(RegistroTreino.id)).label('qtd_registros'),
                db.func.count(HistoricoTreino.id).label('total_series'),
                db.func.coalesce(db.func.sum(HistoricoTreino.carga * HistoricoTreino.repeticoes), 0).label('volume_total')
            ).select_from(Musculo)\
             .outerjoin(ExercicioCustomizado, and_(ExercicioCustomizado.musculo_id == Musculo.id, ExercicioCustomizado.usuario_id == user_id))\
             .outerjoin(RegistroTreino, and_(RegistroTreino.exercicio_id == ExercicioCustomizado.id, RegistroTreino.user_id == user_id))\
             .outerjoin(HistoricoTreino, HistoricoTreino.registro_id == RegistroTreino.id)\
             .group_by(Musculo.id, Musculo.nome_exibicao)\
             .all()
            
            stats = {}
            for r in resultado:
                stats[r.musculo] = {
                    'qtd_exercicios': r.qtd_exercicios,
                    'qtd_registros': r.qtd_registros,
                    'total_series': r.total_series,
                    'volume_total': float(r.volume_total)
                }
            return stats
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular estatísticas por músculo")
            return {}
    
    @staticmethod
    def calcular_por_treino(user_id=None):
        """Calcula estatísticas por treino"""
        try:
            from .treino_service import TreinoService
            from .registro_service import RegistroService

            treinos = TreinoService.get_all(user_id)
            registros = RegistroService.get_all(user_id=user_id, load_series=True)

            treino_stats = {}
            for t in treinos:
                registros_treino = [r for r in registros if r.treino_id == t.id]

                volume_total = 0
                total_series = 0
                exercicios_ids = set()
                for r in registros_treino:
                    exercicios_ids.add(r.exercicio_id)
                    for s in r.series:
                        volume_total += float(s.carga) * s.repeticoes
                        total_series += 1

                treino_stats[t.id] = {
                    "codigo": t.codigo,
                    "nome": t.nome,
                    "descricao": t.descricao,
                    "qtd_exercicios": len(exercicios_ids),
                    "qtd_registros": len(registros_treino),
                    "volume_total": volume_total,
                    "total_series": total_series
                }
            
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
            
            return query.order_by(RegistroTreino.periodo, RegistroTreino.semana).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao calcular progresso por semana")
            return []
    
    @staticmethod
    def preparar_dados_tabela(exercicios, registros, semanas_filtro, request_args):
        """Prepara dados para a tabela de visualização"""
        try:
            # Criar dicionário de registros por exercício
            registros_por_exercicio = {}
            for ex in exercicios:
                registros_por_exercicio[ex.id] = {}
            
            for r in registros:
                if r.exercicio_id in registros_por_exercicio:
                    key = f"{r.periodo}_{r.semana}"
                    registros_por_exercicio[r.exercicio_id][key] = {
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
            periodos_disponiveis = []
            periodos_set = set(s[0] for s in semanas_set)
            for periodo in periodos_set:
                semanas_periodo = sorted([s[1] for s in semanas_set if s[0] == periodo])
                registros_por_semana = {}
                for semana in semanas_periodo:
                    count = sum(1 for r in registros if r.periodo == periodo and r.semana == semana)
                    registros_por_semana[semana] = count
                
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