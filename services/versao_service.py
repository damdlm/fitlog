"""Serviço para operações com versões de treino"""

from models import db, VersaoGlobal, TreinoVersao, VersaoExercicio, Treino, ExercicioCustomizado, Musculo
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from .base_service import BaseService
from .treino_service import TreinoService
from .exercicio_service import ExercicioService
from utils.date_utils import converter_periodo_para_data
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class VersaoService(BaseService):
    """Gerencia operações relacionadas a versões"""
    
    @staticmethod
    def get_all(user_id=None):
        """Retorna todas as versões do usuário"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            return VersaoGlobal.query.filter_by(user_id=user_id)\
                .order_by(VersaoGlobal.numero_versao.desc()).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar versões")
            return []
    
    @staticmethod
    def get_by_id(versao_id, user_id=None, load_relations=False):
        """Retorna versão por ID"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            query = VersaoGlobal.query.filter_by(id=versao_id, user_id=user_id)
            if load_relations:
                query = query.options(
                    joinedload(VersaoGlobal.treinos)
                    .joinedload(TreinoVersao.exercicios)
                )
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar versão {versao_id}")
            return None
    
    @staticmethod
    def get_ativa(periodo=None, user_id=None):
        """Retorna versão ativa para um período"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            if periodo:
                data_periodo = converter_periodo_para_data(periodo)
                return VersaoGlobal.query.filter(
                    VersaoGlobal.user_id == user_id,
                    VersaoGlobal.data_inicio <= data_periodo,
                    (VersaoGlobal.data_fim.is_(None) | (VersaoGlobal.data_fim >= data_periodo))
                ).order_by(VersaoGlobal.data_inicio.desc()).first()
            else:
                return VersaoGlobal.query.filter_by(user_id=user_id, data_fim=None).first()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar versão ativa")
            return None
    
    @staticmethod
    def get_ativa_por_data(data, user_id=None):
        """Retorna a versão ativa em uma data específica"""
        try:
            from datetime import datetime
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            if isinstance(data, str):
                data = datetime.strptime(data, '%Y-%m-%d').date()
            return VersaoGlobal.query.filter(
                VersaoGlobal.user_id == user_id,
                VersaoGlobal.data_inicio <= data,
                (VersaoGlobal.data_fim.is_(None) | (VersaoGlobal.data_fim >= data))
            ).order_by(VersaoGlobal.data_inicio.desc()).first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar versão ativa para data {data}")
            return None
    
    @staticmethod
    def create(descricao, data_inicio, divisao='ABC', data_fim=None, user_id=None):
        """Cria nova versão com divisão específica"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            divisoes_validas = ['ABC', 'ABCD', 'ABCDE']
            if divisao not in divisoes_validas:
                divisao = 'ABC'
            versao_atual = VersaoService.get_ativa(user_id=user_id)
            if versao_atual and not data_fim:
                versao_atual.data_fim = data_inicio
            ultima_versao = db.session.query(func.max(VersaoGlobal.numero_versao))\
                .filter_by(user_id=user_id).scalar() or 0
            nova_versao = VersaoGlobal(
                numero_versao=ultima_versao + 1,
                descricao=descricao,
                divisao=divisao,
                data_inicio=data_inicio,
                data_fim=data_fim,
                user_id=user_id
            )
            db.session.add(nova_versao)
            db.session.commit()
            logger.info(f"Versão {nova_versao.numero_versao} criada com divisão {divisao}")
            return nova_versao
        except Exception as e:
            BaseService.handle_error(e, "Erro ao criar versão")
            return None
    
    @staticmethod
    def update(versao_id, descricao=None, divisao=None, data_inicio=None, data_fim=None, user_id=None):
        """Atualiza uma versão existente"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return None
            if descricao is not None:
                versao.descricao = descricao
            if divisao is not None:
                if divisao in ['ABC', 'ABCD', 'ABCDE']:
                    versao.divisao = divisao
            if data_inicio is not None:
                versao.data_inicio = data_inicio
            if data_fim is not None:
                versao.data_fim = data_fim
            db.session.commit()
            return versao
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar versão {versao_id}")
            return None
    
    @staticmethod
    def clone(versao_id, user_id=None):
        """Clona uma versão existente"""
        try:
            versao_origem = VersaoService.get_by_id(versao_id, user_id, load_relations=True)
            if not versao_origem:
                return False
            data_atual = datetime.now().date()
            versao_ativa = VersaoService.get_ativa(user_id=user_id)
            if versao_ativa:
                return False
            ultima_versao = db.session.query(func.max(VersaoGlobal.numero_versao))\
                .filter_by(user_id=user_id).scalar() or 0
            nova_versao = VersaoGlobal(
                numero_versao=ultima_versao + 1,
                descricao=f"Cópia de {versao_origem.descricao}",
                divisao=versao_origem.divisao,
                data_inicio=data_atual,
                data_fim=None,
                user_id=user_id
            )
            db.session.add(nova_versao)
            db.session.flush()
            for tv in versao_origem.treinos:
                exercicios_ids = [ve.exercicio_id for ve in tv.exercicios]
                VersaoService.adicionar_treino(
                    nova_versao.id,
                    tv.treino_ref.codigo if tv.treino_ref else str(tv.treino_id),
                    tv.nome_treino,
                    tv.descricao_treino,
                    exercicios_ids,
                    user_id
                )
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao clonar versão {versao_id}")
            return False

    @staticmethod
    def _get_or_create_musculo(nome_exibicao):
        """Método auxiliar para obter ou criar músculo"""
        try:
            musculo = Musculo.query.filter_by(nome_exibicao=nome_exibicao).first()
            if not musculo:
                musculo = Musculo(
                    nome=nome_exibicao.lower(),
                    nome_exibicao=nome_exibicao
                )
                db.session.add(musculo)
                db.session.flush()
                logger.info(f"Músculo criado: {nome_exibicao}")
            return musculo
        except Exception as e:
            logger.error(f"Erro ao criar/obter músculo {nome_exibicao}: {e}")
            raise

    @staticmethod
    def create_with_split(descricao, data_inicio, split_type, data_fim=None, user_id=None):
        """Cria uma nova versão com todos os treinos de uma divisão pré-definida"""
        try:
            from data.workout_splits import ALL_SPLITS, MUSCLE_MAPPING
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return None
            if split_type not in ALL_SPLITS:
                return None
            split_data = ALL_SPLITS[split_type]
            versao_atual = VersaoService.get_ativa(user_id=user_id)
            if versao_atual and not data_fim:
                versao_atual.data_fim = data_inicio
            ultima_versao = db.session.query(func.max(VersaoGlobal.numero_versao))\
                .filter_by(user_id=user_id).scalar() or 0
            nova_versao = VersaoGlobal(
                numero_versao=ultima_versao + 1,
                descricao=descricao,
                data_inicio=data_inicio,
                data_fim=data_fim,
                user_id=user_id
            )
            db.session.add(nova_versao)
            db.session.flush()
            for codigo, treino_data in split_data["treinos"].items():
                treino_base = Treino.query.filter_by(user_id=user_id, codigo=codigo).first()
                if not treino_base:
                    treino_base = Treino(
                        codigo=codigo,
                        nome=treino_data["nome"],
                        descricao=treino_data.get("descricao", f"Treino {codigo}"),
                        user_id=user_id
                    )
                    db.session.add(treino_base)
                    db.session.flush()
                treino_versao = TreinoVersao(
                    versao_id=nova_versao.id,
                    treino_id=treino_base.id,
                    nome_treino=treino_data["nome"],
                    descricao_treino=treino_data.get("descricao", f"Treino {codigo} na versão"),
                    ordem=len(nova_versao.treinos)
                )
                db.session.add(treino_versao)
                db.session.flush()
                for ordem, ex_data in enumerate(treino_data["exercicios"]):
                    musculo_nome = MUSCLE_MAPPING.get(ex_data["musculo"], ex_data["musculo"])
                    musculo = VersaoService._get_or_create_musculo(musculo_nome)
                    exercicio = ExercicioCustomizado.query.filter_by(
                        usuario_id=user_id,
                        nome=ex_data["nome"]
                    ).first()
                    if not exercicio:
                        exercicio = ExercicioCustomizado(
                            usuario_id=user_id,
                            nome=ex_data["nome"],
                            descricao=f"Exercício para {treino_data['nome']}",
                            musculo_id=musculo.id
                        )
                        db.session.add(exercicio)
                        db.session.flush()
                    VersaoService.adicionar_exercicio_a_treino_versao(treino_versao.id, exercicio.id, ordem)
            db.session.commit()
            return nova_versao
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar versão com divisão {split_type}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def delete(versao_id, user_id=None):
        """Exclui uma versão e todos os seus relacionamentos"""
        try:
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return False
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            from models import RegistroTreino
            registros = RegistroTreino.query.filter_by(versao_id=versao_id, user_id=user_id).first()
            if registros:
                return False
            db.session.delete(versao)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            BaseService.handle_error(e, f"Erro ao excluir versão {versao_id}")
            return False

    @staticmethod
    def finalizar(versao_id, data_fim, user_id=None):
        """Finaliza uma versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            versao.data_fim = data_fim
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao finalizar versão {versao_id}")
            return False

    @staticmethod
    def get_treinos(versao_id, user_id=None):
        """Retorna treinos de uma versão (formato para template) com ordenação"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id, load_relations=True)
            if not versao:
                return {}
            
            resultado = {}
            for tv in versao.treinos:
                treino = TreinoService.get_by_id(tv.treino_id, user_id)
                if treino:
                    # ==========================================================
                    # 🔥 CORREÇÃO: Guardar o tipo junto com o ID
                    # ==========================================================
                    exercicios_com_tipo = []
                    for ve in tv.exercicios:
                        if ve.exercicio_usuario_id:
                            exercicios_com_tipo.append(f"u_{ve.exercicio_usuario_id}")
                        elif ve.exercicio_base_id:
                            exercicios_com_tipo.append(f"b_{ve.exercicio_base_id}")
                    
                    resultado[treino.codigo] = {
                        "id": tv.treino_id,
                        "codigo": treino.codigo,
                        "nome": tv.nome_treino,
                        "descricao": tv.descricao_treino,
                        "exercicios": exercicios_com_tipo,  # ← Agora com prefixo!
                        "ordem": tv.ordem if hasattr(tv, 'ordem') else 0
                    }
            
            resultado = dict(sorted(resultado.items(), key=lambda item: item[1].get('ordem', 0)))
            return resultado
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treinos da versão {versao_id}")
            return {}

    @staticmethod
    def get_exercicios(versao_id, treino_codigo=None, user_id=None):
        """Retorna exercícios de uma versão (para registro de treino) - UNIFICADO"""
        try:
            from models import ExercicioCustomizado, ExercicioBase
            from sqlalchemy.orm import joinedload
            
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            
            # Buscar treino_versao
            query_tv = TreinoVersao.query.filter_by(versao_id=versao_id)
            if treino_codigo:
                treino = TreinoService.get_by_codigo(treino_codigo, user_id)
                if treino:
                    query_tv = query_tv.filter_by(treino_id=treino.id)
            
            treinos_versao = query_tv.all()
            if not treinos_versao:
                return []
            
            tv_ids = [tv.id for tv in treinos_versao]
            
            # Buscar todos os VersaoExercicio
            ve_list = VersaoExercicio.query.filter(
                VersaoExercicio.treino_versao_id.in_(tv_ids)
            ).order_by(VersaoExercicio.ordem).all()
            
            if not ve_list:
                return []
            
            # Separar IDs por tipo
            usuario_ids = [ve.exercicio_usuario_id for ve in ve_list if ve.exercicio_usuario_id]
            base_ids = [ve.exercicio_base_id for ve in ve_list if ve.exercicio_base_id]
            
            exercicios = []
            
            # Buscar exercícios do usuário (customizados)
            if usuario_ids:
                from models import ExercicioCustomizado
                ex_usuario = ExercicioCustomizado.query.filter(
                    ExercicioCustomizado.id.in_(usuario_ids),
                    ExercicioCustomizado.usuario_id == user_id
                ).options(joinedload(ExercicioCustomizado.musculo_ref)).all()
                exercicios.extend(ex_usuario)
            
            # Buscar exercícios da base (catálogo)
            if base_ids:
                from models import ExercicioBase
                ex_base = ExercicioBase.query.filter(
                    ExercicioBase.id.in_(base_ids)
                ).options(joinedload(ExercicioBase.musculo_ref)).all()
                exercicios.extend(ex_base)
            
            # Manter a ordem original (usando a propriedade híbrida exercicio_id)
            ordem_map = {ve.exercicio_id: idx for idx, ve in enumerate(ve_list)}
            exercicios.sort(key=lambda x: ordem_map.get(x.id, 999))
            
            return exercicios
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercícios da versão {versao_id}")
            return []

    @staticmethod
    def adicionar_treino(versao_id, treino_codigo, nome_treino, descricao_treino, exercicios_ids, user_id=None):
        """Adiciona treino a uma versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            treino = TreinoService.get_by_codigo(treino_codigo, user_id)
            if not treino:
                return False
            if any(tv.treino_id == treino.id for tv in versao.treinos):
                return False
            treino_versao = TreinoVersao(
                versao_id=versao_id,
                treino_id=treino.id,
                nome_treino=nome_treino,
                descricao_treino=descricao_treino,
                ordem=len(versao.treinos)
            )
            db.session.add(treino_versao)
            db.session.flush()
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, exercicios_ids)
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao adicionar treino à versão {versao_id}")
            return False

    @staticmethod
    def remover_treino(versao_id, treino_codigo, user_id=None):
        """Remove treino de uma versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            treino = TreinoService.get_by_codigo(treino_codigo, user_id)
            if not treino:
                return False
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                return False
            db.session.delete(treino_versao)
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao remover treino da versão {versao_id}")
            return False

    @staticmethod
    def adicionar_exercicio(versao_id, treino_codigo, exercicio_id, user_id=None):
        """Adiciona exercício a um treino na versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            treino = TreinoService.get_by_codigo(treino_codigo, user_id)
            if not treino:
                return False
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                return False
            for ve in treino_versao.exercicios:
                if ve.exercicio_id == exercicio_id:
                    return True
            nova_ordem = len(treino_versao.exercicios)
            VersaoService.adicionar_exercicio_a_treino_versao(treino_versao.id, exercicio_id, nova_ordem)
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao adicionar exercício à versão")
            return False

    @staticmethod
    def remover_exercicio(versao_id, treino_codigo, exercicio_id, user_id=None):
        """Remove exercício de um treino na versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            treino = TreinoService.get_by_codigo(treino_codigo, user_id)
            if not treino:
                return False
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                return False
            ve_to_delete = None
            for ve in treino_versao.exercicios:
                if ve.exercicio_id == exercicio_id:
                    ve_to_delete = ve
                    break
            if ve_to_delete:
                db.session.delete(ve_to_delete)
                db.session.commit()
                return True
            return False
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao remover exercício da versão")
            return False

    @staticmethod
    def reordenar_exercicios(versao_id, treino_codigo, nova_ordem, user_id=None):
        """Reordena exercícios de um treino na versão"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id)
            if not versao:
                return False
            treino = TreinoService.get_by_codigo(treino_codigo, user_id)
            if not treino:
                return False
            treino_versao = None
            for tv in versao.treinos:
                if tv.treino_id == treino.id:
                    treino_versao = tv
                    break
            if not treino_versao:
                return False
            for ordem, ex_id in enumerate(nova_ordem):
                for ve in treino_versao.exercicios:
                    if ve.exercicio_id == ex_id:
                        ve.ordem = ordem
                        break
            db.session.commit()
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao reordenar exercícios")
            return False

    @staticmethod
    def get_treinos_para_registro(versao_id, user_id=None):
        """Retorna lista de treinos disponíveis em uma versão para o formulário de registro"""
        try:
            from models import TreinoVersao, Treino
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []
            resultados = db.session.query(
                Treino.id,
                Treino.codigo,
                TreinoVersao.nome_treino,
                TreinoVersao.descricao_treino
            ).join(
                TreinoVersao, TreinoVersao.treino_id == Treino.id
            ).filter(
                TreinoVersao.versao_id == versao_id,
                Treino.user_id == user_id
            ).order_by(Treino.codigo).all()
            treinos_disponiveis = []
            for treino_id, codigo, nome_treino, descricao_treino in resultados:
                treinos_disponiveis.append({
                    "id": treino_id,
                    "codigo": codigo,
                    "nome": nome_treino,
                    "descricao": descricao_treino
                })
            return treinos_disponiveis
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treinos para registro na versão {versao_id}")
            return []

    # ==========================================================
    # NOVOS MÉTODOS PARA CORREÇÃO DO VersaoExercicio
    # ==========================================================

    @staticmethod
    def _get_exercicio_fk(exercicio_id):
        """Retorna dicionário com a FK apropriada (exercicio_usuario_id ou exercicio_base_id)"""
        from models import ExercicioUsuario, ExercicioBase
        ex_user = ExercicioUsuario.query.get(exercicio_id)
        if ex_user:
            return {'exercicio_usuario_id': exercicio_id}
        ex_base = ExercicioBase.query.get(exercicio_id)
        if ex_base:
            return {'exercicio_base_id': exercicio_id}
        raise ValueError(f"Exercício com ID {exercicio_id} não encontrado em nenhuma tabela")

    @staticmethod
    def adicionar_exercicio_a_treino_versao(treino_versao_id, exercicio_id, ordem):
        """Adiciona um exercício a um treino_versao, determinando automaticamente a FK correta"""
        from models import VersaoExercicio, db
        fk = VersaoService._get_exercicio_fk(exercicio_id)
        ve = VersaoExercicio(treino_versao_id=treino_versao_id, ordem=ordem, **fk)
        db.session.add(ve)
        db.session.commit()
        return ve

    @staticmethod
    def adicionar_exercicios_a_treino_versao(treino_versao_id, usuarios_ids, bases_ids):
        """Adiciona múltiplos exercícios a um treino_versao, substituindo os existentes"""
        from models import VersaoExercicio, db
        # Remove antigos
        VersaoExercicio.query.filter_by(treino_versao_id=treino_versao_id).delete()
        ordem = 0
        # Adiciona exercícios do usuário (customizados)
        for ex_id in usuarios_ids:
            ve = VersaoExercicio(
                treino_versao_id=treino_versao_id,
                exercicio_usuario_id=ex_id,
                ordem=ordem
            )
            db.session.add(ve)
            ordem += 1
        # Adiciona exercícios da base (catálogo)
        for ex_id in bases_ids:
            ve = VersaoExercicio(
                treino_versao_id=treino_versao_id,
                exercicio_base_id=ex_id,
                ordem=ordem
            )
            db.session.add(ve)
            ordem += 1
        db.session.commit()

    @staticmethod
    def editar_treino_versao(versao_id, treino_codigo, dados, user_id, current_user):
        """
        Edita um treino dentro de uma versão.
        - user_id: dono dos dados (aluno)
        - current_user: usuário logado (para permissão)
        """
        # Permissão
        if not (current_user.is_admin or current_user.id == user_id or
                (current_user.is_professor() and current_user.pode_acessar_dados_de(user_id))):
            raise PermissionError("Sem permissão para editar este treino.")
        
        versao = VersaoGlobal.query.filter_by(id=versao_id, user_id=user_id).first()
        if not versao:
            raise ValueError("Versão não encontrada")
        
        treino = Treino.query.filter_by(codigo=treino_codigo, user_id=user_id).first()
        if not treino:
            raise ValueError("Treino não encontrado")
        
        treino_versao = TreinoVersao.query.filter_by(versao_id=versao.id, treino_id=treino.id).first()
        if not treino_versao:
            raise ValueError("Treino não encontrado nesta versão")
        
        if 'nome_treino' in dados:
            treino_versao.nome_treino = dados['nome_treino']
        if 'descricao_treino' in dados:
            treino_versao.descricao_treino = dados['descricao_treino']
        if 'exercicios_ids' in dados and dados['exercicios_ids'] is not None:
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, dados['exercicios_ids'])
        
        db.session.commit()
        return treino_versao

    @staticmethod
    def excluir_treino_versao(versao_id, treino_codigo, user_id, current_user):
        if not (current_user.is_admin or current_user.id == user_id or
                (current_user.is_professor() and current_user.pode_acessar_dados_de(user_id))):
            raise PermissionError("Sem permissão para excluir este treino.")
        
        versao = VersaoGlobal.query.filter_by(id=versao_id, user_id=user_id).first()
        if not versao:
            raise ValueError("Versão não encontrada")
        
        treino = Treino.query.filter_by(codigo=treino_codigo, user_id=user_id).first()
        if not treino:
            raise ValueError("Treino não encontrado")
        
        treino_versao = TreinoVersao.query.filter_by(versao_id=versao.id, treino_id=treino.id).first()
        if not treino_versao:
            raise ValueError("Treino não encontrado nesta versão")
        
        db.session.delete(treino_versao)
        db.session.commit()
        return True