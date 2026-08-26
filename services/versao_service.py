"""Serviço para operações com versões de treino"""

from models import db, VersaoGlobal, TreinoVersao, VersaoExercicio, Treino, ExercicioCustomizado, Musculo, RegistroTreino, User
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import set_committed_value
from .base_service import BaseService
from .treino_service import TreinoService
from .exercicio_service import ExercicioService
from utils.date_utils import converter_periodo_para_data
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class VersaoService(BaseService):
    """Gerencia operações relacionadas a versões"""

    # Tela "Cadastrar Treinos" (fluxo unificado, sem divisão fixa ABC/ABCD/ABCDE):
    # limite superior de treinos por versão -- não é uma regra de negócio do
    # usuário, é uma trava de consistência/anti-abuso (evita uma versão com
    # centenas de treinos por engano ou script malicioso). Bem acima de
    # qualquer uso real (a maior divisão fixa que existia era ABCDE = 5).
    MAX_TREINOS_POR_VERSAO = 10

    # Códigos (letras) atribuídos automaticamente aos treinos da versão
    # "livre", na ordem em que são criados -- nunca aceitos do cliente,
    # para não colidir com o unique_treino_por_usuario (user_id, codigo).
    _CODIGOS_AUTO = [chr(c) for c in range(ord('A'), ord('Z') + 1)]
    
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
                ).order_by(
                    VersaoGlobal.data_fim.is_(None).desc(),
                    VersaoGlobal.data_inicio.desc()
                ).first()
            else:
                return VersaoGlobal.query.filter_by(user_id=user_id, data_fim=None)\
                    .order_by(VersaoGlobal.data_inicio.desc()).first()
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
            ).order_by(
                VersaoGlobal.data_fim.is_(None).desc(),
                VersaoGlobal.data_inicio.desc()
            ).first()
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
            # NOTA (bug corrigido): user_id nunca era resolvido via
            # BaseService.get_current_user_id() aqui -- ficava None
            # sempre que o chamador não passasse explicitamente (como é
            # o caso da rota version.clonar_versao_global), e a criação
            # de `nova_versao` mais abaixo usava esse None diretamente,
            # violando a constraint NOT NULL de user_id e sempre
            # revertendo com False.
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return False
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
                usuarios_ids = []
                bases_ids = []
                observacoes = {}
                for ve in tv.exercicios:
                    if ve.exercicio_usuario_id is not None:
                        usuarios_ids.append(ve.exercicio_usuario_id)
                        if ve.observacao:
                            observacoes[f"u_{ve.exercicio_usuario_id}"] = ve.observacao
                    elif ve.exercicio_base_id is not None:
                        bases_ids.append(ve.exercicio_base_id)
                        if ve.observacao:
                            observacoes[f"b_{ve.exercicio_base_id}"] = ve.observacao
                
                VersaoService.adicionar_treino(
                    nova_versao.id,
                    tv.treino_ref.codigo if tv.treino_ref else str(tv.treino_id),
                    tv.nome_treino,
                    tv.descricao_treino,
                    usuarios_ids,
                    bases_ids,
                    user_id,
                    observacoes=observacoes
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
        except Exception:
            logger.exception("Erro ao criar/obter músculo {nome_exibicao}")
            raise

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
        """Retorna treinos de uma versão com prefixo nos IDs"""
        try:
            versao = VersaoService.get_by_id(versao_id, user_id, load_relations=True)
            if not versao:
                return {}
            
            resultado = {}
            for tv in versao.treinos:
                treino = TreinoService.get_by_id(tv.treino_id, user_id)
                if treino:
                    exercicios_com_prefixo = []
                    for ve in tv.exercicios:
                        if ve.exercicio_usuario_id is not None:
                            exercicios_com_prefixo.append(f"u_{ve.exercicio_usuario_id}")
                        elif ve.exercicio_base_id is not None:
                            exercicios_com_prefixo.append(f"b_{ve.exercicio_base_id}")
                    
                    resultado[treino.codigo] = {
                        "id": tv.treino_id,
                        "codigo": treino.codigo,
                        "nome": tv.nome_treino,
                        "descricao": tv.descricao_treino,
                        "exercicios": exercicios_com_prefixo,
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
            from models import ExercicioCustomizado, ExercicioSistema
            from sqlalchemy.orm import joinedload
            
            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return []

            # IDOR: TreinoVersao não tem coluna user_id própria (só
            # versao_id), então sem este check qualquer usuário autenticado
            # podia passar um versao_id de outro usuário e ver a estrutura
            # dessa versão (treinos/exercícios). Confirma que a versão
            # pertence a user_id antes de buscar seus treinos/exercícios.
            versao_pertence_ao_usuario = VersaoGlobal.query.filter_by(
                id=versao_id, user_id=user_id
            ).first()
            if not versao_pertence_ao_usuario:
                return []

            query_tv = TreinoVersao.query.filter_by(versao_id=versao_id)
            if treino_codigo:
                treino = TreinoService.get_by_codigo(treino_codigo, user_id)
                if not treino:
                    # Não silenciar: se o treino não existe pra esse user_id,
                    # o correto é não retornar nada, nunca "todos os treinos".
                    logger.warning(
                        f"Treino '{treino_codigo}' não encontrado para usuário {user_id} "
                        f"ao buscar exercícios da versão {versao_id}"
                    )
                    return []
                query_tv = query_tv.filter_by(treino_id=treino.id)
            
            treinos_versao = query_tv.all()
            if not treinos_versao:
                return []
            
            tv_ids = [tv.id for tv in treinos_versao]
            
            ve_list = VersaoExercicio.query.filter(
                VersaoExercicio.treino_versao_id.in_(tv_ids)
            ).order_by(VersaoExercicio.ordem).all()
            
            if not ve_list:
                return []
            
            usuario_ids = []
            base_ids = []
            ordem_map = {}
            observacao_map = {}
            
            for idx, ve in enumerate(ve_list):
                if ve.exercicio_usuario_id is not None:
                    usuario_ids.append(ve.exercicio_usuario_id)
                    ordem_map[('usuario', ve.exercicio_usuario_id)] = idx
                    observacao_map[('usuario', ve.exercicio_usuario_id)] = ve.observacao
                elif ve.exercicio_base_id is not None:
                    base_ids.append(ve.exercicio_base_id)
                    ordem_map[('base', ve.exercicio_base_id)] = idx
                    observacao_map[('base', ve.exercicio_base_id)] = ve.observacao
            
            exercicios = []

            # "musculo_nome" é property real (baseada em grupo_muscular) — atribuir aqui
            # dentro de uma leitura marca o objeto como sujo e o autoflush da
            # próxima query tenta gravar isso no catálogo global, disputando
            # locks com outras requisições (ver correção equivalente em
            # ExercicioService.get_exercicios_completos). no_autoflush +
            # expunge garantem que essa listagem nunca gera escrita.
            with db.session.no_autoflush:
                if usuario_ids:
                    ex_usuario = ExercicioCustomizado.query.filter(
                        ExercicioCustomizado.id.in_(usuario_ids),
                        ExercicioCustomizado.usuario_id == user_id
                    ).options(joinedload(ExercicioCustomizado.musculo_ref)).all()

                    # Templates (ex: professor/treinos_aluno.html) leem
                    # exercicio.registros|length. É lazy, então o expunge()
                    # abaixo quebraria essa leitura com DetachedInstanceError
                    # (ver mesma correção em ExercicioService.get_exercicios_completos).
                    registros_usuario_map = {}
                    if usuario_ids:
                        regs = RegistroTreino.query.filter(
                            RegistroTreino.user_id == user_id,
                            RegistroTreino.exercicio_usuario_id.in_(usuario_ids)
                        ).all()
                        for r in regs:
                            registros_usuario_map.setdefault(r.exercicio_usuario_id, []).append(r)

                    for ex in ex_usuario:
                        ex.tipo = 'usuario'
                        ex.prefixo = 'u_'
                        ex.musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
                        ex.musculo = ex.musculo_nome
                        ex.observacao_treino = observacao_map.get(('usuario', ex.id))
                        # Normalizado com ex_base abaixo para o tooltip da tela de
                        # registrar treino: descricao_completa junta o texto livre
                        # cadastrado; exercícios de usuário não têm músculos
                        # secundários cadastrados (só o principal, via musculo_id).
                        ex.descricao_completa = (ex.descricao or '').strip()
                        ex.musculos_secundarios_lista = []
                        set_committed_value(ex, 'registros', registros_usuario_map.get(ex.id, []))
                        db.session.expunge(ex)
                        exercicios.append(ex)

                if base_ids:
                    ex_base = ExercicioSistema.query.filter(
                        ExercicioSistema.id.in_(base_ids)
                    ).all()

                    # Idem: filtrado por user_id — exercicios_sistema é
                    # catálogo global, sem o filtro contaria registros de
                    # todos os usuários.
                    registros_base_map = {}
                    if base_ids:
                        regs = RegistroTreino.query.filter(
                            RegistroTreino.user_id == user_id,
                            RegistroTreino.exercicio_base_id.in_(base_ids)
                        ).all()
                        for r in regs:
                            registros_base_map.setdefault(r.exercicio_base_id, []).append(r)

                    for ex in ex_base:
                        ex.tipo = 'base'
                        ex.prefixo = 'b_'
                        # musculo_nome já é property (= grupo_muscular)
                        ex.musculo = ex.grupo_muscular or 'N/A'
                        ex.observacao_treino = observacao_map.get(('base', ex.id))
                        # instrucao_pt é o texto livre de descrição do exercício
                        # (equivalente ao "descricao" de ExercicioUsuario);
                        # musculos_secundarios já vem como lista no JSON.
                        ex.descricao_completa = (ex.instrucao_pt or '').strip()
                        ex.musculos_secundarios_lista = ex.musculos_secundarios or []
                        set_committed_value(ex, 'registros', registros_base_map.get(ex.id, []))
                        db.session.expunge(ex)
                        exercicios.append(ex)

            exercicios.sort(key=lambda x: ordem_map.get((x.tipo, x.id), 999))

            return exercicios
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercícios da versão {versao_id}")
            return []

    @staticmethod
    def get_exercicios_agrupados_por_treino(user_id=None):
        """
        Retorna {treino_id: [exercicios]} para TODOS os treinos da versão
        ativa do usuário, em uma quantidade fixa de queries — independente
        do número de treinos.

        Usada para evitar N+1 nas telas que hoje fazem, para cada treino:
            for treino in treinos:
                exercicios_por_treino[treino.id] = ExercicioService.get_by_treino(treino.id, ...)
        (cada chamada de get_by_treino já dispara ~6-8 queries próprias —
        ver ExercicioService.get_by_treino). Medido na prática: uma tela
        com 5 treinos x 4 exercícios caiu de 82 para 9 queries ao trocar
        o loop por esta função.

        Mantém o mesmo shape de dados que get_by_treino retornava por
        treino (mesmos atributos: tipo, prefixo, musculo, musculo_nome,
        registros), então os templates não precisam mudar.
        """
        try:
            from models import ExercicioCustomizado, ExercicioSistema
            from sqlalchemy.orm import joinedload
            from datetime import datetime as _dt

            user_id = user_id or BaseService.get_current_user_id()
            if not user_id:
                return {}

            versao_ativa = VersaoService.get_ativa_por_data(_dt.now().date(), user_id=user_id)
            if not versao_ativa:
                return {}

            treinos_versao = TreinoVersao.query.filter_by(versao_id=versao_ativa.id).all()
            if not treinos_versao:
                return {}

            tv_id_para_treino_id = {tv.id: tv.treino_id for tv in treinos_versao}
            tv_ids = list(tv_id_para_treino_id.keys())

            ve_list = VersaoExercicio.query.filter(
                VersaoExercicio.treino_versao_id.in_(tv_ids)
            ).order_by(VersaoExercicio.ordem).all()

            resultado = {tv.treino_id: [] for tv in treinos_versao}
            if not ve_list:
                return resultado

            usuario_ids, base_ids = [], []
            treino_id_por_ve = {}  # ('usuario'|'base', exercicio_id) -> treino_id
            ordem_map = {}
            for idx, ve in enumerate(ve_list):
                treino_id = tv_id_para_treino_id.get(ve.treino_versao_id)
                if ve.exercicio_usuario_id is not None:
                    usuario_ids.append(ve.exercicio_usuario_id)
                    treino_id_por_ve[('usuario', ve.exercicio_usuario_id)] = treino_id
                    ordem_map[('usuario', ve.exercicio_usuario_id)] = idx
                elif ve.exercicio_base_id is not None:
                    base_ids.append(ve.exercicio_base_id)
                    treino_id_por_ve[('base', ve.exercicio_base_id)] = treino_id
                    ordem_map[('base', ve.exercicio_base_id)] = idx

            with db.session.no_autoflush:
                if usuario_ids:
                    ex_usuario = ExercicioCustomizado.query.filter(
                        ExercicioCustomizado.id.in_(usuario_ids),
                        ExercicioCustomizado.usuario_id == user_id
                    ).options(joinedload(ExercicioCustomizado.musculo_ref)).all()

                    regs = RegistroTreino.query.filter(
                        RegistroTreino.user_id == user_id,
                        RegistroTreino.exercicio_usuario_id.in_(usuario_ids)
                    ).all()
                    registros_usuario_map = {}
                    for r in regs:
                        registros_usuario_map.setdefault(r.exercicio_usuario_id, []).append(r)

                    for ex in ex_usuario:
                        ex.tipo = 'usuario'
                        ex.prefixo = 'u_'
                        ex.musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
                        ex.musculo = ex.musculo_nome
                        set_committed_value(ex, 'registros', registros_usuario_map.get(ex.id, []))
                        db.session.expunge(ex)
                        t_id = treino_id_por_ve.get(('usuario', ex.id))
                        if t_id in resultado:
                            resultado[t_id].append(ex)

                if base_ids:
                    ex_base = ExercicioSistema.query.filter(
                        ExercicioSistema.id.in_(base_ids)
                    ).all()

                    regs = RegistroTreino.query.filter(
                        RegistroTreino.user_id == user_id,
                        RegistroTreino.exercicio_base_id.in_(base_ids)
                    ).all()
                    registros_base_map = {}
                    for r in regs:
                        registros_base_map.setdefault(r.exercicio_base_id, []).append(r)

                    for ex in ex_base:
                        ex.tipo = 'base'
                        ex.prefixo = 'b_'
                        ex.musculo = ex.grupo_muscular or 'N/A'
                        set_committed_value(ex, 'registros', registros_base_map.get(ex.id, []))
                        db.session.expunge(ex)
                        t_id = treino_id_por_ve.get(('base', ex.id))
                        if t_id in resultado:
                            resultado[t_id].append(ex)

            for t_id, exs in resultado.items():
                exs.sort(key=lambda x: ordem_map.get((x.tipo, x.id), 999))

            return resultado

        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercícios agrupados por treino (usuário {user_id})")
            return {}

    @staticmethod
    def get_exercicios_para_edicao(user_id, treino_versao):
        """Retorna (exercicios_display, exercicios_atuais, observacoes_atuais) para o template de edição."""
        from models import ExercicioCustomizado, ExercicioSistema
        from sqlalchemy.orm import joinedload
        
        exercicios_usuario = ExercicioCustomizado.query\
            .filter_by(usuario_id=user_id)\
            .options(joinedload(ExercicioCustomizado.musculo_ref))\
            .order_by(ExercicioCustomizado.nome).all()
        
        exercicios_base = ExercicioSistema.query\
            .order_by(ExercicioSistema.nome).all()
        
        exercicios_display = []
        
        for ex in exercicios_usuario:
            musculo_nome = ex.musculo_ref.nome_exibicao if ex.musculo_ref else 'N/A'
            exercicios_display.append({
                'id': ex.id,
                'nome': ex.nome,
                'musculo': musculo_nome,
                'musculo_nome': musculo_nome,
                'tipo': 'usuario',
                'prefixo': 'u_',
                'imagem': None,
                'gif_url': None,
                'descricao': (ex.descricao or '').strip()
            })
        
        for ex in exercicios_base:
            musculo_nome = ex.grupo_muscular or 'N/A'
            exercicios_display.append({
                'id': ex.id,
                'nome': ex.nome,
                'musculo': musculo_nome,
                'musculo_nome': musculo_nome,
                'tipo': 'base',
                'prefixo': 'b_',
                'imagem': ex.imagem,
                'gif_url': ex.gif_url,
                'descricao': (ex.instrucao_pt or '').strip()
            })
        
        exercicios_display.sort(key=lambda x: x['nome'].lower())
        
        exercicios_atuais = []
        observacoes_atuais = {}
        for ve in treino_versao.exercicios:
            if ve.exercicio_usuario_id is not None:
                chave = f"u_{ve.exercicio_usuario_id}"
            elif ve.exercicio_base_id is not None:
                chave = f"b_{ve.exercicio_base_id}"
            else:
                continue
            exercicios_atuais.append(chave)
            if ve.observacao:
                observacoes_atuais[chave] = ve.observacao
        
        return exercicios_display, exercicios_atuais, observacoes_atuais

    @staticmethod
    def adicionar_exercicios_a_treino_versao(treino_versao_id, usuarios_ids, bases_ids, observacoes=None):
        """
        Substitui todos os exercícios de um treino na versão.

        observacoes: dict opcional {"u_<id>": "texto", "b_<id>": "texto"}
        com a observação de cada exercício dentro deste treino (até 60
        caracteres -- truncado aqui como segunda garantia, além do
        maxlength no formulário).
        """
        from models import VersaoExercicio, db
        
        usuarios_ids = usuarios_ids or []
        bases_ids = bases_ids or []
        observacoes = observacoes or {}
        
      #  if not usuarios_ids and not bases_ids:
      #      raise ValueError("Pelo menos um exercício é obrigatório")
        
        VersaoExercicio.query.filter_by(treino_versao_id=treino_versao_id).delete()
        db.session.flush()
        
        ordem = 0
        
        for ex_id in usuarios_ids:
            obs = (observacoes.get(f"u_{ex_id}") or '').strip()[:60] or None
            ve = VersaoExercicio()
            ve.treino_versao_id = treino_versao_id
            ve.exercicio_usuario_id = ex_id
            ve.exercicio_base_id = None
            ve.ordem = ordem
            ve.observacao = obs
            db.session.add(ve)
            ordem += 1
        
        for ex_id in bases_ids:
            obs = (observacoes.get(f"b_{ex_id}") or '').strip()[:60] or None
            ve = VersaoExercicio()
            ve.treino_versao_id = treino_versao_id
            ve.exercicio_usuario_id = None
            ve.exercicio_base_id = ex_id
            ve.ordem = ordem
            ve.observacao = obs
            db.session.add(ve)
            ordem += 1
        
        db.session.flush()
        logger.info(f"Adicionados {len(usuarios_ids)} exercícios de usuário e {len(bases_ids)} da base ao treino {treino_versao_id}")

    @staticmethod
    def adicionar_treino(versao_id, treino_codigo, nome_treino, descricao_treino, usuarios_ids, bases_ids, user_id=None, observacoes=None):
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
            VersaoService.adicionar_exercicios_a_treino_versao(treino_versao.id, usuarios_ids, bases_ids, observacoes=observacoes)
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
                TreinoVersao.descricao_treino,
                Treino.descricao
            ).join(
                TreinoVersao, TreinoVersao.treino_id == Treino.id
            ).filter(
                TreinoVersao.versao_id == versao_id,
                Treino.user_id == user_id
            ).order_by(Treino.codigo).all()
            treinos_disponiveis = []
            for treino_id, codigo, nome_treino, descricao_treino, descricao_geral_treino in resultados:
                treinos_disponiveis.append({
                    "id": treino_id,
                    "codigo": codigo,
                    "nome": nome_treino,
                    # Prioriza a descrição específica desta versão
                    # (TreinoVersao.descricao_treino); se o usuário nunca
                    # preencheu essa (é opcional), cai pra descrição geral
                    # do treino (Treino.descricao), cadastrada em "Meus
                    # Treinos" -- assim sempre mostra algo, se existir.
                    "descricao": descricao_treino or descricao_geral_treino
                })
            return treinos_disponiveis
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treinos para registro na versão {versao_id}")
            return []

    @staticmethod
    def _get_exercicio_fk(exercicio_id):
        """Retorna dicionário com a FK apropriada"""
        from models import ExercicioUsuario, ExercicioSistema
        ex_user = ExercicioUsuario.query.get(exercicio_id)
        if ex_user:
            return {'exercicio_usuario_id': exercicio_id}
        ex_base = ExercicioSistema.query.get(exercicio_id)
        if ex_base:
            return {'exercicio_base_id': exercicio_id}
        raise ValueError(f"Exercício com ID {exercicio_id} não encontrado em nenhuma tabela")

    @staticmethod
    def adicionar_exercicio_a_treino_versao(treino_versao_id, exercicio_id, ordem):
        """Adiciona um exercício a um treino_versao"""
        from models import VersaoExercicio, db
        fk = VersaoService._get_exercicio_fk(exercicio_id)
        ve = VersaoExercicio(treino_versao_id=treino_versao_id, ordem=ordem, **fk)
        db.session.add(ve)
        db.session.commit()
        return ve

    @staticmethod
    def processar_exercicios_formulario(exercicios_raw, user_id):
        """Processa a lista de exercícios vindos do formulário"""
        from models import ExercicioCustomizado, ExercicioSistema
        
        usuarios_ids = []
        bases_ids = []
        
        for item in exercicios_raw:
            if not item or not item.strip():
                continue
            item = item.strip()
            
            if item.startswith('u_'):
                try:
                    ex_id = int(item[2:])
                    usuarios_ids.append(ex_id)
                except ValueError:
                    pass
            elif item.startswith('b_'):
                try:
                    ex_id = int(item[2:])
                    bases_ids.append(ex_id)
                except ValueError:
                    pass
        
        usuarios_ids = list(set(usuarios_ids))
        bases_ids = list(set(bases_ids))
        
        usuarios_ids_validos = []
        if usuarios_ids:
            exercicios = ExercicioCustomizado.query.filter(
                ExercicioCustomizado.id.in_(usuarios_ids),
                ExercicioCustomizado.usuario_id == user_id
            ).all()
            usuarios_ids_validos = [ex.id for ex in exercicios]
        
        bases_ids_validos = []
        if bases_ids:
            exercicios = ExercicioSistema.query.filter(
                ExercicioSistema.id.in_(bases_ids)
            ).all()
            bases_ids_validos = [ex.id for ex in exercicios]
        
        return usuarios_ids_validos, bases_ids_validos

    @staticmethod
    def editar_treino_versao(versao_id, treino_codigo, dados, user_id, current_user):
        """Edita um treino dentro de uma versão."""
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
        if 'usuarios_ids' in dados and 'bases_ids' in dados:
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id, dados['usuarios_ids'], dados['bases_ids']
            )
        
        db.session.commit()
        return treino_versao

    @staticmethod
    def excluir_treino_versao(versao_id, treino_codigo, user_id, current_user):
        """Exclui um treino de uma versão."""
        # NOTA (bug corrigido): User.pode_acessar_dados_de(outro_usuario)
        # espera um objeto User (acessa outro_usuario.id internamente),
        # mas aqui recebíamos `user_id` já como int -- sempre lançava
        # AttributeError para professores (não admin, alvo != o próprio
        # usuário). Resolvendo o User alvo antes de checar a permissão.
        usuario_alvo = User.query.get(user_id)
        if not usuario_alvo:
            raise ValueError("Usuário não encontrado")
        if not (current_user.is_admin or current_user.id == user_id or
                (current_user.is_professor() and current_user.pode_acessar_dados_de(usuario_alvo))):
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

    # ==========================================================
    # TELA "CADASTRAR TREINOS" -- fluxo unificado (versão sem
    # divisão fixa + treinos + exercícios em um único lugar).
    #
    # Todos os métodos abaixo levantam ValueError com uma mensagem
    # segura para exibir direto ao usuário (mesmo padrão já usado em
    # editar_treino_versao/excluir_treino_versao acima) -- erros
    # inesperados são logados e relançados como ValueError genérico,
    # nunca com str(exception) original (não vazar detalhes internos).
    # ==========================================================

    @staticmethod
    def create_livre(descricao, user_id=None):
        """
        Cria uma nova versão "livre" (sem campo de divisão, sem data de
        início/fim informados pelo usuário):
        - data_inicio = data atual do SERVIDOR (nunca aceita do cliente,
          pra não permitir versão retroativa/futura forjada);
        - data_fim = None (só é preenchida ao finalizar, com a data real
          de finalização);
        - só é permitida se o usuário não tiver nenhuma versão ativa no
          momento (nunca fecha silenciosamente a versão anterior --
          diferente de create(), que fazia isso; aqui exigimos que o
          usuário finalize explicitamente antes de criar outra).
        """
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        descricao = (descricao or '').strip()
        if not descricao:
            raise ValueError("Descrição da versão é obrigatória.")
        if len(descricao) > 200:
            raise ValueError("Descrição deve ter no máximo 200 caracteres.")

        versao_atual = VersaoService.get_ativa(user_id=user_id)
        if versao_atual:
            raise ValueError(
                f"Já existe uma versão ativa (v{versao_atual.numero_versao} - "
                f"{versao_atual.descricao}). Finalize-a antes de criar outra."
            )

        try:
            data_inicio = datetime.now(timezone.utc).date()
            ultima_versao = db.session.query(func.max(VersaoGlobal.numero_versao)) \
                .filter_by(user_id=user_id).scalar() or 0
            nova_versao = VersaoGlobal(
                numero_versao=ultima_versao + 1,
                descricao=descricao,
                divisao='LIVRE',
                data_inicio=data_inicio,
                data_fim=None,
                user_id=user_id
            )
            db.session.add(nova_versao)
            db.session.commit()
            logger.info(f"Versão livre {nova_versao.numero_versao} criada para usuário {user_id}")
            return nova_versao
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao criar versão livre para usuário {user_id}")
            raise ValueError("Não foi possível criar a versão.")

    @staticmethod
    def _get_versao_editavel(versao_id, user_id):
        """Busca a versão garantindo posse (IDOR) e que ainda não foi
        finalizada. Levanta ValueError com mensagem segura em qualquer
        caso inválido -- usado por todas as mutações da tela "Cadastrar
        Treinos" abaixo."""
        versao = VersaoGlobal.query.filter_by(id=versao_id, user_id=user_id).first()
        if not versao:
            raise ValueError("Versão não encontrada.")
        if versao.data_fim is not None:
            raise ValueError("Esta versão já foi finalizada e não pode mais ser alterada.")
        return versao

    @staticmethod
    def editar_descricao_livre(versao_id, nova_descricao, user_id=None):
        """Atualiza só a descrição de uma versão "livre" ainda em edição.
        Não mexe em numero_versao/data_inicio/divisao -- esses são
        definidos na criação e não fazem sentido editar depois."""
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        versao = VersaoService._get_versao_editavel(versao_id, user_id)

        nova_descricao = (nova_descricao or '').strip()
        if not nova_descricao:
            raise ValueError("Descrição da versão é obrigatória.")
        if len(nova_descricao) > 200:
            raise ValueError("Descrição deve ter no máximo 200 caracteres.")

        try:
            versao.descricao = nova_descricao
            db.session.commit()
            logger.info(f"Descrição da versão {versao_id} editada (cadastro livre) pelo usuário {user_id}")
            return versao
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao editar descrição da versão {versao_id}")
            raise ValueError("Não foi possível salvar a descrição.")

    @staticmethod
    def adicionar_treino_livre(versao_id, nome_treino, descricao_treino, user_id=None):
        """
        Adiciona um novo treino à versão "livre", sem pedir letra/código
        do usuário: o código (A, B, C...) é escolhido automaticamente pelo
        servidor, olhando só os códigos já usados NESTA versão (o mesmo
        código pode ser reaproveitado -- via TreinoService.get_or_create --
        em versões diferentes do mesmo usuário, é assim que o restante do
        sistema já funciona).
        """
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        versao = VersaoService._get_versao_editavel(versao_id, user_id)

        nome_treino = (nome_treino or '').strip()
        descricao_treino = (descricao_treino or '').strip()
        if not nome_treino:
            raise ValueError("Nome do treino é obrigatório.")
        if len(nome_treino) > 100:
            raise ValueError("Nome do treino deve ter no máximo 100 caracteres.")
        if len(descricao_treino) > 200:
            raise ValueError("Descrição do treino deve ter no máximo 200 caracteres.")

        treinos_atuais = TreinoVersao.query.filter_by(versao_id=versao_id).count()
        if treinos_atuais >= VersaoService.MAX_TREINOS_POR_VERSAO:
            raise ValueError(
                f"Limite de {VersaoService.MAX_TREINOS_POR_VERSAO} treinos por versão atingido."
            )

        linhas_codigo = db.session.query(Treino.codigo) \
            .join(TreinoVersao, TreinoVersao.treino_id == Treino.id) \
            .filter(TreinoVersao.versao_id == versao_id, Treino.user_id == user_id) \
            .all()
        codigos_em_uso = {linha[0] for linha in linhas_codigo}

        proximo_codigo = next(
            (c for c in VersaoService._CODIGOS_AUTO if c not in codigos_em_uso), None
        )
        if not proximo_codigo:
            raise ValueError("Não há mais códigos disponíveis para novos treinos.")

        try:
            treino = TreinoService.get_or_create(
                proximo_codigo, nome_treino, descricao_treino, user_id=user_id
            )
            if not treino:
                raise ValueError("Não foi possível criar o treino.")

            treino_versao = TreinoVersao(
                versao_id=versao_id,
                treino_id=treino.id,
                nome_treino=nome_treino,
                descricao_treino=descricao_treino,
                ordem=treinos_atuais
            )
            db.session.add(treino_versao)
            db.session.commit()
            logger.info(
                f"Treino {proximo_codigo} adicionado (cadastro livre) à versão {versao_id} "
                f"do usuário {user_id}"
            )
            return treino_versao
        except ValueError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao adicionar treino livre à versão {versao_id}")
            raise ValueError("Não foi possível adicionar o treino.")

    @staticmethod
    def _get_treino_versao_editavel(versao_id, treino_versao_id, user_id):
        """Garante que o treino_versao_id realmente pertence à versao_id,
        que por sua vez pertence ao user_id, e que a versão não está
        finalizada. Sem este check, um usuário autenticado poderia tentar
        editar/remover um treino_versao_id de OUTRO usuário só adivinhando
        o ID (IDOR)."""
        versao = VersaoService._get_versao_editavel(versao_id, user_id)
        treino_versao = TreinoVersao.query.filter_by(
            id=treino_versao_id, versao_id=versao_id
        ).first()
        if not treino_versao:
            raise ValueError("Treino não encontrado nesta versão.")
        return versao, treino_versao

    @staticmethod
    def salvar_treino_livre(versao_id, treino_versao_id, nome_treino, descricao_treino,
                             exercicios_raw, user_id=None, observacoes=None):
        """Atualiza nome/descrição de um treino da versão e substitui a
        lista de exercícios associados (mesma semântica de
        adicionar_exercicios_a_treino_versao: a lista enviada substitui a
        anterior por completo).

        observacoes: dict opcional {"u_<id>": "texto", "b_<id>": "texto"}
        -- mesma convenção usada em editar_treino_versao (aluno), repassado
        direto pra adicionar_exercicios_a_treino_versao, que já trunca em
        60 caracteres."""
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        _, treino_versao = VersaoService._get_treino_versao_editavel(versao_id, treino_versao_id, user_id)

        nome_treino = (nome_treino or '').strip()
        descricao_treino = (descricao_treino or '').strip()
        if not nome_treino:
            raise ValueError("Nome do treino é obrigatório.")
        if len(nome_treino) > 100:
            raise ValueError("Nome do treino deve ter no máximo 100 caracteres.")
        if len(descricao_treino) > 200:
            raise ValueError("Descrição do treino deve ter no máximo 200 caracteres.")

        usuarios_ids_validos, bases_ids_validos = VersaoService.processar_exercicios_formulario(
            exercicios_raw or [], user_id
        )

        # Trava anti-abuso: número de exercícios por treino também tem um
        # teto (nenhuma regra do usuário pedia isso, mas sem limite um
        # POST malicioso poderia tentar associar milhares de linhas de
        # uma vez só).
        MAX_EXERCICIOS_POR_TREINO = 40
        total_exercicios = len(usuarios_ids_validos) + len(bases_ids_validos)
        if total_exercicios > MAX_EXERCICIOS_POR_TREINO:
            raise ValueError(f"Máximo de {MAX_EXERCICIOS_POR_TREINO} exercícios por treino.")

        try:
            treino_versao.nome_treino = nome_treino
            treino_versao.descricao_treino = descricao_treino
            VersaoService.adicionar_exercicios_a_treino_versao(
                treino_versao.id, usuarios_ids_validos, bases_ids_validos, observacoes=observacoes
            )
            db.session.commit()
            logger.info(f"Treino {treino_versao.id} (versão {versao_id}) salvo via cadastro livre")
            return treino_versao
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao salvar treino {treino_versao_id} da versão {versao_id}")
            raise ValueError("Não foi possível salvar o treino.")

    @staticmethod
    def remover_treino_livre(versao_id, treino_versao_id, user_id=None):
        """Remove um treino (e seus exercícios, via cascade) da versão."""
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        _, treino_versao = VersaoService._get_treino_versao_editavel(versao_id, treino_versao_id, user_id)

        try:
            db.session.delete(treino_versao)
            db.session.commit()
            logger.info(f"Treino {treino_versao_id} removido da versão {versao_id} (cadastro livre)")
            return True
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao remover treino {treino_versao_id} da versão {versao_id}")
            raise ValueError("Não foi possível remover o treino.")

    @staticmethod
    def finalizar_livre(versao_id, user_id=None):
        """
        Finaliza a versão gravando a data de HOJE (servidor) como
        data_fim -- nunca aceita do cliente.

        Regra de consistência: só permite finalizar se houver pelo menos
        1 treino, e cada treino tiver pelo menos 1 exercício -- do
        contrário a versão ficaria "ativa" mas inutilizável na tela de
        registro diário (RegistroTreino), que depende de
        VersaoService.get_treinos_para_registro/get_exercicios.
        """
        user_id = user_id or BaseService.get_current_user_id()
        if not user_id:
            raise ValueError("Usuário não autenticado.")

        versao = VersaoService._get_versao_editavel(versao_id, user_id)

        treinos = TreinoVersao.query.filter_by(versao_id=versao_id).all()
        if not treinos:
            raise ValueError("Adicione pelo menos um treino antes de finalizar a versão.")

        treinos_sem_exercicio = [
            (t.treino_ref.codigo if t.treino_ref else '?') for t in treinos if not t.exercicios
        ]
        if treinos_sem_exercicio:
            raise ValueError(
                "Todos os treinos precisam ter pelo menos um exercício antes de finalizar. "
                f"Faltando em: {', '.join(sorted(treinos_sem_exercicio))}."
            )

        try:
            versao.data_fim = datetime.now(timezone.utc).date()
            db.session.commit()
            logger.info(f"Versão {versao_id} finalizada (cadastro livre) pelo usuário {user_id}")
            return versao
        except Exception:
            db.session.rollback()
            logger.exception(f"Erro ao finalizar versão {versao_id}")
            raise ValueError("Não foi possível finalizar a versão.")