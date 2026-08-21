"""Serviço para operações com registros de treino"""

from models import db, RegistroTreino, HistoricoTreino
from sqlalchemy.orm import selectinload
from sqlalchemy import or_  # ✅ ADICIONADO
from datetime import datetime, timezone
from .base_service import BaseService
import logging

logger = logging.getLogger(__name__)

class RegistroService(BaseService):
    """Gerencia operações relacionadas a registros de treino"""

    # Faixa de duração plausível pra uma sessão de treino, usada ao
    # decidir se um tempo_treino recém-enviado deve substituir o que já
    # estava salvo (ver _resolver_tempo_treino). Abaixo do mínimo é quase
    # sempre só o tempinho de reabrir/editar um treino já salvo (a tela
    # sempre exige clicar em "Iniciar treino" de novo pra liberar os
    # campos, mesmo em edição -- o que reinicia o cronômetro do zero).
    # Acima do máximo é quase sempre uma aba/PWA esquecida aberta rodando
    # (o cronômetro é só relógio de parede, sem pausa automática por
    # inatividade) -- nenhum dos dois reflete a duração real do treino.
    TEMPO_TREINO_MIN_SEGUNDOS = 60
    TEMPO_TREINO_MAX_SEGUNDOS = 6 * 60 * 60  # 6 horas

    @staticmethod
    def _resolver_tempo_treino(tempo_novo, tempo_anterior):
        """Decide qual tempo_treino gravar ao (re)salvar uma sessão.

        Existe pra cobrir o caso de EDITAR um treino já salvo: como a
        tela de registro sempre exige clicar em "Iniciar treino" pra
        liberar os campos -- mesmo reabrindo um dia já registrado só pra
        corrigir um exercício -- o cronômetro reinicia do zero a cada
        vez. Sem esse tratamento, reabrir e resalvar um treino já feito
        sobrescrevia a duração REAL da sessão original com esse tempinho
        de edição (quase sempre perto de 0, ou às vezes um valor enorme
        se a aba ficou esquecida aberta rodando), fazendo o "tempo do
        último treino" no dashboard mostrar 00:00 ou um número absurdo.

        Um valor novo só "vence" o que já estava salvo se estiver dentro
        de uma faixa plausível pra uma sessão de treino de verdade
        (nem tempo demais de curto -- só o clique de editar -- nem tempo
        demais de longo -- aba esquecida aberta). Fora dessa faixa,
        mantém o valor anterior (se houver).
        """
        if (tempo_novo is not None
                and RegistroService.TEMPO_TREINO_MIN_SEGUNDOS <= tempo_novo <= RegistroService.TEMPO_TREINO_MAX_SEGUNDOS):
            return tempo_novo
        return tempo_anterior
    
    @staticmethod
    def get_all(filtros=None, user_id=None, load_series=False, data_inicio=None, data_fim=None):
        """Retorna registros com filtros opcionais

        data_inicio/data_fim: filtro por intervalo em data_registro, usado
        no banco (aproveita o índice idx_registro_user_data) em vez de
        carregar todo o histórico e filtrar em Python. data_fim é exclusivo
        (data_registro < data_fim), então para "agosto/2026" passe
        data_inicio=2026-08-01 e data_fim=2026-09-01.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            query = RegistroTreino.query.filter_by(user_id=user_id)
            
            if load_series:
                query = query.options(selectinload(RegistroTreino.series))

            if data_inicio is not None:
                query = query.filter(RegistroTreino.data_registro >= data_inicio)
            if data_fim is not None:
                query = query.filter(RegistroTreino.data_registro < data_fim)
            
            if filtros:
                if 'treino_id' in filtros and filtros['treino_id']:
                    query = query.filter_by(treino_id=filtros['treino_id'])
                if 'periodo' in filtros and filtros['periodo']:
                    query = query.filter_by(periodo=filtros['periodo'])
                if 'semana' in filtros and filtros['semana'] is not None:
                    query = query.filter_by(semana=filtros['semana'])
                # ✅ CORRIGIDO: usa or_ com as duas colunas reais
                if 'exercicio_id' in filtros and filtros['exercicio_id']:
                    ex_id = filtros['exercicio_id']
                    query = query.filter(
                        or_(
                            RegistroTreino.exercicio_usuario_id == ex_id,
                            RegistroTreino.exercicio_base_id == ex_id
                        )
                    )
                if 'versao_id' in filtros and filtros['versao_id']:
                    query = query.filter_by(versao_id=filtros['versao_id'])
            
            return query.order_by(RegistroTreino.data_registro.desc()).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar registros")
            return []
    
    @staticmethod
    def get_treino_por_data(data, user_id=None):
        """
        Encontra qual treino foi registrado numa data específica.

        Todos os registros de uma mesma sessão compartilham
        treino_id/versao_id/periodo/semana (são criados juntos por
        salvar_registros), então basta o primeiro registro do dia para
        saber qual treino foi feito.

        Compara contra a meia-noite (datetime), não um date puro: a
        coluna é DateTime e no Postgres (produção) comparar com um date
        já funciona por cast implícito, mas no SQLite (dev/testes, sem
        tipagem real) um date puro vira o literal '2026-06-15' na query
        enquanto o valor gravado é '2026-06-15 00:00:00.000000' -- strings
        diferentes, então a busca não encontra nada. Normalizando aqui
        funciona nos dois bancos.
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None

            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()
            data_meia_noite = datetime(data.year, data.month, data.day)

            return RegistroTreino.query.filter(
                RegistroTreino.user_id == user_id,
                RegistroTreino.data_registro == data_meia_noite
            ).first()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treino por data")
            return None

    @staticmethod
    def excluir_por_treino_data(treino_id, versao_id, data, user_id=None):
        """Exclui todos os registros (e séries, via CASCADE no banco) de
        um treino numa data específica — usado para descartar uma sessão
        já registrada."""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return False

            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()
            data_meia_noite = datetime(data.year, data.month, data.day)

            RegistroTreino.query.filter(
                RegistroTreino.user_id == user_id,
                RegistroTreino.treino_id == treino_id,
                RegistroTreino.versao_id == versao_id,
                RegistroTreino.data_registro == data_meia_noite
            ).delete()
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            BaseService.handle_error(e, "Erro ao excluir registros por treino/data")
            return False

    @staticmethod
    def get_by_data(treino_id, versao_id, data, user_id=None):
        """
        Retorna registros de um treino em uma data específica
        
        Args:
            treino_id: ID do treino
            versao_id: ID da versão
            data: Data do registro (date object ou string YYYY-MM-DD)
            user_id: ID do usuário (opcional)
        
        Returns:
            list: Lista de registros encontrados
        """
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de buscar registros sem usuário logado")
                return []
            
            # Garantir que data é date object
            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()

            # Compara contra a meia-noite (datetime), não um date puro --
            # a coluna é DateTime; no Postgres um date puro já funciona
            # por cast implícito, mas no SQLite (dev/testes) um date puro
            # vira o literal '2026-06-15' na query enquanto o valor
            # gravado é '2026-06-15 00:00:00.000000', então a busca não
            # encontra nada. Normalizando aqui funciona nos dois bancos.
            data_meia_noite = datetime(data.year, data.month, data.day)

            # Buscar registros do dia
            registros = RegistroTreino.query.filter(
                RegistroTreino.user_id == user_id,
                RegistroTreino.treino_id == treino_id,
                RegistroTreino.versao_id == versao_id,
                RegistroTreino.data_registro == data_meia_noite
            ).all()
            
            logger.debug(f"Encontrados {len(registros)} registros para treino {treino_id} em {data}")
            return registros
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros por data")
            return []
    
    @staticmethod
    def salvar_registros(treino_id, versao_id, periodo, semana, dados_exercicios, user_id=None, tempo_treino=None):
        """Salva múltiplos registros de uma sessão de treino

        Args:
            tempo_treino: duração total do treino em segundos (cronômetro do
                topo da página), gravada em cada série de historico_treino
                referente a esta sessão.
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return False

            # Antes de apagar a sessão antiga (se existir), guarda o
            # tempo_treino que já estava salvo -- é o candidato a manter
            # caso o valor recém-enviado não pareça uma medição real de
            # cronômetro (ver _resolver_tempo_treino).
            registro_existente = RegistroTreino.query.filter_by(
                treino_id=treino_id,
                periodo=periodo,
                semana=semana,
                versao_id=versao_id,
                user_id=user_id
            ).options(selectinload(RegistroTreino.series)).first()
            tempo_treino_anterior = None
            if registro_existente and registro_existente.series:
                tempo_treino_anterior = registro_existente.series[0].tempo_treino

            tempo_treino = RegistroService._resolver_tempo_treino(tempo_treino, tempo_treino_anterior)

            if registro_existente:
                # Remove da identity map da sessão -- se não fizer isso,
                # os objetos HistoricoTreino/RegistroTreino antigos (já
                # carregados acima via selectinload) continuam "vivos" na
                # sessão mesmo depois do DELETE em massa logo abaixo
                # (query.delete() não sabe que precisa expirar objetos já
                # carregados). Como o SQLite reaproveita o menor rowid
                # livre, os novos registros/séries criados nesta mesma
                # chamada podem receber os MESMOS IDs dos que acabaram de
                # ser apagados, e o SQLAlchemy emite um SAWarning ao dar
                # flush ("Identity map already had an identity for...").
                # Sem prejuízo funcional aqui (os objetos antigos não são
                # mais referenciados depois deste ponto), mas o aviso é
                # sintoma de estado obsoleto sobrando na sessão -- melhor
                # descartar explicitamente.
                for serie_antiga in registro_existente.series:
                    db.session.expunge(serie_antiga)
                db.session.expunge(registro_existente)

            # Remover registros antigos da mesma sessão
            RegistroTreino.query.filter_by(
                treino_id=treino_id,
                periodo=periodo,
                semana=semana,
                versao_id=versao_id,
                user_id=user_id
            ).delete()
            
            for chave, dados in dados_exercicios.items():
                if dados['carga'] and dados['repeticoes']:
                    # Tipo já vem identificado da rota (ex.tipo), não precisa mais
                    # adivinhar em qual tabela o ID existe — exercicios_usuario e
                    # exercicios_base têm sequências de ID independentes, então o
                    # mesmo número pode existir nas duas ao mesmo tempo.
                    ex_id = dados.get('exercicio_id', chave)
                    is_usuario = dados.get('tipo') == 'usuario'
                    
                    registro = RegistroTreino(
                        treino_id=treino_id,
                        versao_id=versao_id,
                        periodo=periodo,
                        semana=semana,
                        exercicio_usuario_id=ex_id if is_usuario else None,
                        exercicio_base_id=ex_id if not is_usuario else None,
                        data_registro=dados.get('data_registro', datetime.now(timezone.utc)),
                        user_id=user_id
                    )
                    db.session.add(registro)
                    db.session.flush()
                    
                    for i in range(dados['num_series']):
                        serie = HistoricoTreino(
                            registro_id=registro.id,
                            carga=dados['carga'],
                            repeticoes=dados['repeticoes'],
                            ordem=i+1,
                            tempo_treino=tempo_treino
                        )
                        db.session.add(serie)
            
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, "Erro ao salvar registros")
            return False
    
    @staticmethod
    def salvar_registro_unico(treino_id, versao_id, periodo, semana, exercicio_id, 
                              carga, repeticoes, num_series=3, data_registro=None, user_id=None):
        """Salva um único registro de exercício"""
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de salvar registro sem usuário logado")
                return None
            
            if data_registro is None:
                data_registro = datetime.now(timezone.utc)
            
            # Determinar tipo do exercício
            from models import ExercicioUsuario, ExercicioSistema
            is_usuario = db.session.get(ExercicioUsuario, exercicio_id) is not None
            is_base = db.session.get(ExercicioSistema, exercicio_id) is not None if not is_usuario else False
            
            if not is_usuario and not is_base:
                logger.warning(f"Exercício {exercicio_id} não encontrado em nenhuma tabela")
                return None
            
            # Remover registros antigos do mesmo exercício na mesma sessão
            delete_query = RegistroTreino.query.filter(
                RegistroTreino.treino_id == treino_id,
                RegistroTreino.periodo == periodo,
                RegistroTreino.semana == semana,
                RegistroTreino.versao_id == versao_id,
                RegistroTreino.user_id == user_id
            )
            if is_usuario:
                delete_query = delete_query.filter(RegistroTreino.exercicio_usuario_id == exercicio_id)
            else:
                delete_query = delete_query.filter(RegistroTreino.exercicio_base_id == exercicio_id)
            delete_query.delete()
            
            # Criar novo registro
            registro = RegistroTreino(
                treino_id=treino_id,
                versao_id=versao_id,
                periodo=periodo,
                semana=semana,
                exercicio_usuario_id=exercicio_id if is_usuario else None,
                exercicio_base_id=exercicio_id if is_base else None,
                data_registro=data_registro,
                user_id=user_id
            )
            db.session.add(registro)
            db.session.flush()
            
            # Criar séries
            for i in range(num_series):
                serie = HistoricoTreino(
                    registro_id=registro.id,
                    carga=carga,
                    repeticoes=repeticoes,
                    ordem=i+1
                )
                db.session.add(serie)
            
            db.session.commit()
            logger.info(f"Registro salvo para exercício {exercicio_id}")
            return registro
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao salvar registro único")
            return None
    
    @staticmethod
    def get_periodos_existentes(user_id=None):
        """Retorna lista de períodos com registros"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            registros = RegistroTreino.query\
                .filter_by(user_id=user_id)\
                .with_entities(RegistroTreino.periodo)\
                .distinct().all()
            
            return sorted([r[0] for r in registros], reverse=True)
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar períodos")
            return []
    
    @staticmethod
    def get_semanas_por_periodo(user_id=None):
        """Retorna dicionário com semanas agrupadas por período"""
        try:
            registros = RegistroService.get_all(user_id=user_id)
            
            semanas_set = set()
            for r in registros:
                semanas_set.add((r.periodo, r.semana, f"{r.periodo}_{r.semana}"))
            
            periodos_dict = {}
            for periodo, semana, key in semanas_set:
                if periodo not in periodos_dict:
                    periodos_dict[periodo] = []
                periodos_dict[periodo].append({
                    "semana": semana,
                    "key": key
                })
            
            return periodos_dict
        except Exception as e:
            BaseService.handle_error(e, "Erro ao agrupar semanas")
            return {}
    
    @staticmethod
    def get_volume_total_por_semana(registros):
        """Calcula volume total por semana"""
        try:
            volume_por_semana = {}
            for r in registros:
                key = f"{r.periodo}_{r.semana}"
                if key not in volume_por_semana:
                    volume_por_semana[key] = 0
                
                for serie in r.series:
                    volume_por_semana[key] += float(serie.carga) * serie.repeticoes
            
            return volume_por_semana
        except Exception:
            logger.exception("Erro ao calcular volume por semana")
            return {}
    
    @staticmethod
    def get_por_exercicio(exercicio_id, limite=None, user_id=None):
        """Retorna registros de um exercício específico"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            # ✅ CORRIGIDO: usa or_ com as colunas reais
            query = RegistroTreino.query.options(
                selectinload(RegistroTreino.series)
            ).filter(
                RegistroTreino.user_id == user_id,
                or_(
                    RegistroTreino.exercicio_usuario_id == exercicio_id,
                    RegistroTreino.exercicio_base_id == exercicio_id
                )
            ).order_by(RegistroTreino.data_registro.desc())
            
            if limite:
                query = query.limit(limite)
            
            return query.all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros do exercício {exercicio_id}")
            return []
    
    @staticmethod
    def get_por_periodo(periodo, user_id=None):
        """Retorna todos os registros de um período"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            return RegistroTreino.query.options(
                selectinload(RegistroTreino.series)
            ).filter_by(
                periodo=periodo,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro).all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros do período {periodo}")
            return []
    
    @staticmethod
    def get_por_semana(periodo, semana, user_id=None):
        """Retorna todos os registros de uma semana específica"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            return RegistroTreino.query.options(
                selectinload(RegistroTreino.series)
            ).filter_by(
                periodo=periodo,
                semana=semana,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro).all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar registros da semana {semana}")
            return []
    
    @staticmethod
    def get_ultimo_registro_por_exercicio(exercicio_id, user_id=None):
        """Retorna o último registro de um exercício"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            
            # ✅ CORRIGIDO: usa or_ com as colunas reais
            return RegistroTreino.query.options(
                selectinload(RegistroTreino.series)
            ).filter(
                RegistroTreino.user_id == user_id,
                or_(
                    RegistroTreino.exercicio_usuario_id == exercicio_id,
                    RegistroTreino.exercicio_base_id == exercicio_id
                )
            ).order_by(RegistroTreino.data_registro.desc()).first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar último registro do exercício {exercicio_id}")
            return None
    
    @staticmethod
    def get_estatisticas_exercicio(exercicio_id, user_id=None):
        """Retorna estatísticas de um exercício"""
        try:
            from sqlalchemy import func
            
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}
            
            registros = RegistroService.get_por_exercicio(exercicio_id, user_id=user_id)
            
            if not registros:
                return {}
            
            # Calcular estatísticas
            total_registros = len(registros)
            total_series = 0
            soma_cargas = 0
            soma_repeticoes = 0
            maior_carga = 0
            maior_volume = 0
            
            for r in registros:
                for s in r.series:
                    total_series += 1
                    soma_cargas += float(s.carga)
                    soma_repeticoes += s.repeticoes
                    
                    if float(s.carga) > maior_carga:
                        maior_carga = float(s.carga)
                    
                    volume = float(s.carga) * s.repeticoes
                    if volume > maior_volume:
                        maior_volume = volume
            
            return {
                'total_registros': total_registros,
                'total_series': total_series,
                'media_carga': soma_cargas / total_series if total_series > 0 else 0,
                'media_repeticoes': soma_repeticoes / total_series if total_series > 0 else 0,
                'maior_carga': maior_carga,
                'maior_volume': maior_volume
            }
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao calcular estatísticas do exercício {exercicio_id}")
            return {}