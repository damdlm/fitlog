"""Serviço para operações com exercícios - Versão com tabelas base compartilhadas"""

from models import db, ExercicioBase, ExercicioUsuario, ExercicioCustomizado, Musculo, VersaoExercicio
from sqlalchemy.orm import joinedload
from sqlalchemy import text, func
from . import BaseService
import logging

logger = logging.getLogger(__name__)

class ExercicioService(BaseService):
    """Gerencia operações relacionadas a exercícios com tabelas base compartilhadas"""
    
    # =============================================
    # MÉTODOS PARA EXERCÍCIOS BASE (CATÁLOGO GLOBAL)
    # =============================================
    
    @staticmethod
    def get_all_base(limite=500):
        """Retorna todos os exercícios do catálogo base"""
        try:
            return ExercicioBase.query.options(
                joinedload(ExercicioBase.musculo_ref)
            ).order_by(ExercicioBase.nome).limit(limite).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar exercícios base")
            return []
    
    @staticmethod
    def get_base_by_id(exercicio_base_id):
        """Retorna um exercício base por ID"""
        try:
            return ExercicioBase.query.options(
                joinedload(ExercicioBase.musculo_ref)
            ).get(exercicio_base_id)
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercício base {exercicio_base_id}")
            return None
    
    @staticmethod
    def search_base(termo, musculo=None, limite=50):
        """Busca exercícios no catálogo base"""
        try:
            query = ExercicioBase.query.options(joinedload(ExercicioBase.musculo_ref))
            
            if termo:
                query = query.filter(ExercicioBase.nome.ilike(f'%{termo}%'))
            
            if musculo:
                query = query.join(ExercicioBase.musculo_ref).filter(
                    Musculo.nome_exibicao == musculo
                )
            
            return query.order_by(ExercicioBase.nome).limit(limite).all()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercícios base com termo {termo}")
            return []
    
    # =============================================
    # MÉTODOS PARA EXERCÍCIOS DO USUÁRIO (CATÁLOGO PESSOAL)
    # =============================================
    
    @staticmethod
    def get_exercicios_usuario(user_id=None, load_relations=False):
        """
        Retorna todos os exercícios disponíveis para um usuário
        (inclui exercícios base adicionados e customizados)
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                logger.warning("Tentativa de buscar exercícios sem usuário logado")
                return []
            
            # Usar a view para obter todos os exercícios disponíveis
            result = db.session.execute(text("""
                SELECT 
                    exercicio_id,
                    nome,
                    descricao,
                    musculo,
                    tipo,
                    is_personalizado
                FROM exercicios_disponiveis 
                WHERE usuario_id = :user_id 
                ORDER BY nome
            """), {'user_id': user_id})
            
            return result.fetchall()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar exercícios do usuário")
            return []
    
    @staticmethod
    def get_exercicios_completos(user_id=None):
        """
        Retorna todos os exercícios do usuário com objetos completos
        (para uso em templates que precisam dos objetos)
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return []
            
            # Buscar exercícios base associados ao usuário
            exercicios_usuario = ExercicioUsuario.query.options(
                joinedload(ExercicioUsuario.exercicio_base_ref).joinedload(ExercicioBase.musculo_ref)
            ).filter_by(usuario_id=user_id).all()
            
            # Buscar exercícios customizados
            exercicios_custom = ExercicioCustomizado.query.options(
                joinedload(ExercicioCustomizado.musculo_ref)
            ).filter_by(usuario_id=user_id).all()
            
            # Combinar em uma lista
            resultado = []
            
            for eu in exercicios_usuario:
                ex_base = eu.exercicio_base_ref
                if ex_base:
                    # Criar objeto compatível com o template
                    class ExercicioWrapper:
                        def __init__(self, eu, ex_base):
                            self.id = eu.id
                            self.nome = eu.nome_personalizado or ex_base.nome
                            self.descricao = eu.descricao_personalizada or ex_base.descricao
                            self.musculo_ref = ex_base.musculo_ref
                            self.treino_id = None
                            self.user_id = user_id
                            self.is_custom = False
                            self.exercicio_base_id = ex_base.id
                    
                    resultado.append(ExercicioWrapper(eu, ex_base))
            
            for ec in exercicios_custom:
                ec.is_custom = True
                resultado.append(ec)
            
            # Ordenar por nome
            resultado.sort(key=lambda x: x.nome)
            
            return resultado
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar exercícios completos")
            return []
    
    @staticmethod
    def get_by_id(exercicio_id, user_id=None, load_relations=False):
        """
        Retorna um exercício pelo ID (pode ser da tabela exercicios_usuario ou exercicios_customizados)
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return None
            
            # Verificar se é um exercício da tabela exercicios_usuario
            exercicio_usuario = ExercicioUsuario.query.get(exercicio_id)
            if exercicio_usuario and exercicio_usuario.usuario_id == user_id:
                if load_relations:
                    # Carregar relações
                    exercicio_usuario = ExercicioUsuario.query.options(
                        joinedload(ExercicioUsuario.exercicio_base_ref).joinedload(ExercicioBase.musculo_ref)
                    ).get(exercicio_id)
                
                # Criar wrapper para compatibilidade
                class ExercicioWrapper:
                    def __init__(self, eu):
                        self.id = eu.id
                        self.nome = eu.nome_personalizado or eu.exercicio_base_ref.nome
                        self.descricao = eu.descricao_personalizada or eu.exercicio_base_ref.descricao
                        self.musculo_ref = eu.exercicio_base_ref.musculo_ref
                        if eu.musculo_personalizado_id:
                            self.musculo_ref = Musculo.query.get(eu.musculo_personalizado_id)
                        self.treino_id = None
                        self.user_id = eu.usuario_id
                        self.is_custom = False
                        self.exercicio_base_id = eu.exercicio_base_id
                        self.created_at = eu.created_at
                
                return ExercicioWrapper(exercicio_usuario)
            
            # Verificar se é um exercício customizado
            exercicio_custom = ExercicioCustomizado.query.options(
                joinedload(ExercicioCustomizado.musculo_ref)
            ).get(exercicio_id)
            
            if exercicio_custom and exercicio_custom.usuario_id == user_id:
                exercicio_custom.is_custom = True
                return exercicio_custom
            
            return None
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercício {exercicio_id}")
            return None
    
    @staticmethod
    def get_by_treino(treino_id, user_id=None):
        """Retorna exercícios de um treino específico"""
        try:
            from models import VersaoExercicio, TreinoVersao
            
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return []
            
            # Buscar versões que contêm este treino
            versoes_treino = TreinoVersao.query.filter_by(treino_id=treino_id).all()
            
            exercicios = []
            for tv in versoes_treino:
                for ve in tv.exercicios:
                    exercicio = ExercicioService.get_by_id(ve.exercicio_id, user_id)
                    if exercicio and exercicio not in exercicios:
                        exercicios.append(exercicio)
            
            return exercicios
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar exercícios do treino {treino_id}")
            return []
    
    # =============================================
    # MÉTODOS PARA ADICIONAR/REMOVER EXERCÍCIOS DO USUÁRIO
    # =============================================
    
    @staticmethod
    def adicionar_exercicio_base(user_id, exercicio_base_id, nome_personalizado=None, 
                                  descricao_personalizada=None, musculo_personalizado_id=None):
        """
        Adiciona um exercício da base ao catálogo do usuário
        """
        try:
            # Verificar se já existe
            existente = ExercicioUsuario.query.filter_by(
                usuario_id=user_id,
                exercicio_base_id=exercicio_base_id
            ).first()
            
            if existente:
                logger.info(f"Exercício base {exercicio_base_id} já existe para usuário {user_id}")
                return existente
            
            exercicio = ExercicioUsuario(
                usuario_id=user_id,
                exercicio_base_id=exercicio_base_id,
                nome_personalizado=nome_personalizado,
                descricao_personalizada=descricao_personalizada,
                musculo_personalizado_id=musculo_personalizado_id
            )
            db.session.add(exercicio)
            db.session.commit()
            
            logger.info(f"Exercício base {exercicio_base_id} adicionado ao usuário {user_id}")
            return exercicio
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao adicionar exercício base ao usuário")
            return None
    
    @staticmethod
    def criar_exercicio_customizado(user_id, nome, musculo_nome, descricao='', treino_id=None):
        """
        Cria um novo exercício customizado para o usuário
        """
        try:
            # Buscar ou criar músculo
            musculo = Musculo.query.filter_by(nome_exibicao=musculo_nome).first()
            if not musculo:
                musculo = Musculo(
                    nome=musculo_nome.lower(),
                    nome_exibicao=musculo_nome
                )
                db.session.add(musculo)
                db.session.flush()
            
            exercicio = ExercicioCustomizado(
                usuario_id=user_id,
                nome=nome,
                descricao=descricao,
                musculo_id=musculo.id
            )
            db.session.add(exercicio)
            db.session.flush()
            
            # Se tiver treino_id, associar ao treino (via versão?)
            # Esta parte depende da lógica de negócio
            
            db.session.commit()
            
            logger.info(f"Exercício customizado '{nome}' criado para usuário {user_id}")
            return exercicio
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao criar exercício customizado")
            return None
    
    @staticmethod
    def update_exercicio_usuario(exercicio_usuario_id, user_id=None, **kwargs):
        """
        Atualiza um exercício da tabela exercicios_usuario
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return None
            
            exercicio = ExercicioUsuario.query.filter_by(
                id=exercicio_usuario_id,
                usuario_id=user_id
            ).first()
            
            if not exercicio:
                logger.warning(f"Exercício usuário {exercicio_usuario_id} não encontrado")
                return None
            
            # Atualizar campos
            if 'nome_personalizado' in kwargs:
                exercicio.nome_personalizado = kwargs['nome_personalizado']
            if 'descricao_personalizada' in kwargs:
                exercicio.descricao_personalizada = kwargs['descricao_personalizada']
            if 'musculo_personalizado_id' in kwargs:
                exercicio.musculo_personalizado_id = kwargs['musculo_personalizado_id']
            if 'observacoes' in kwargs:
                exercicio.observacoes = kwargs['observacoes']
            
            db.session.commit()
            logger.info(f"Exercício usuário {exercicio_usuario_id} atualizado")
            return exercicio
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar exercício usuário")
            return None
    
    @staticmethod
    def update_exercicio_customizado(exercicio_custom_id, user_id=None, **kwargs):
        """
        Atualiza um exercício customizado
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return None
            
            exercicio = ExercicioCustomizado.query.filter_by(
                id=exercicio_custom_id,
                usuario_id=user_id
            ).first()
            
            if not exercicio:
                logger.warning(f"Exercício customizado {exercicio_custom_id} não encontrado")
                return None
            
            # Atualizar campos
            if 'nome' in kwargs:
                exercicio.nome = kwargs['nome']
            if 'descricao' in kwargs:
                exercicio.descricao = kwargs['descricao']
            if 'musculo_id' in kwargs:
                exercicio.musculo_id = kwargs['musculo_id']
            
            db.session.commit()
            logger.info(f"Exercício customizado {exercicio_custom_id} atualizado")
            return exercicio
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar exercício customizado")
            return None
    
    @staticmethod
    def delete_exercicio_usuario(exercicio_usuario_id, user_id=None):
        """
        Remove um exercício da tabela exercicios_usuario (não exclui da base)
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return False
            
            exercicio = ExercicioUsuario.query.filter_by(
                id=exercicio_usuario_id,
                usuario_id=user_id
            ).first()
            
            if not exercicio:
                logger.warning(f"Exercício usuário {exercicio_usuario_id} não encontrado")
                return False
            
            # Verificar se está sendo usado em versões
            em_uso = VersaoExercicio.query.filter_by(exercicio_id=exercicio.id).first()
            if em_uso:
                logger.warning(f"Exercício usuário {exercicio_usuario_id} está em uso em versões")
                return False
            
            db.session.delete(exercicio)
            db.session.commit()
            
            logger.info(f"Exercício usuário {exercicio_usuario_id} removido")
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao remover exercício usuário")
            return False
    
    @staticmethod
    def delete_exercicio_customizado(exercicio_custom_id, user_id=None):
        """
        Exclui um exercício customizado
        """
        try:
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return False
            
            exercicio = ExercicioCustomizado.query.filter_by(
                id=exercicio_custom_id,
                usuario_id=user_id
            ).first()
            
            if not exercicio:
                logger.warning(f"Exercício customizado {exercicio_custom_id} não encontrado")
                return False
            
            # Verificar se está sendo usado em versões
            em_uso = VersaoExercicio.query.filter_by(exercicio_id=exercicio.id).first()
            if em_uso:
                logger.warning(f"Exercício customizado {exercicio_custom_id} está em uso em versões")
                return False
            
            db.session.delete(exercicio)
            db.session.commit()
            
            logger.info(f"Exercício customizado {exercicio_custom_id} excluído")
            return True
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao excluir exercício customizado")
            return False
    
    # =============================================
    # MÉTODOS PARA DADOS DE TREINO (ÚLTIMAS CARGAS, ETC)
    # =============================================
    
    @staticmethod
    def get_ultima_carga(exercicio_id, user_id=None):
        """
        Retorna última carga de um exercício
        (funciona com qualquer tipo de exercício)
        """
        try:
            from models import RegistroTreino, HistoricoTreino
            
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return None
            
            registro = RegistroTreino.query.filter_by(
                exercicio_id=exercicio_id,
                user_id=user_id
            ).order_by(RegistroTreino.data_registro.desc()).first()
            
            if registro and registro.series:
                primeira_serie = registro.series[0]
                return float(primeira_serie.carga)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar última carga do exercício {exercicio_id}: {e}")
            return None
    
    @staticmethod
    def get_ultimas_series(exercicio_id, versao_id=None, limite=1, user_id=None):
        """
        Retorna as últimas séries de um exercício
        """
        try:
            from models import HistoricoTreino, RegistroTreino
            
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return []
            
            query = HistoricoTreino.query\
                .join(RegistroTreino)\
                .filter(RegistroTreino.exercicio_id == exercicio_id)\
                .filter(RegistroTreino.user_id == user_id)
            
            if versao_id:
                query = query.filter(RegistroTreino.versao_id == versao_id)
            
            series = query.order_by(RegistroTreino.data_registro.desc())\
                .limit(limite).all()
            
            resultado = []
            for serie in series:
                resultado.append({
                    'carga': float(serie.carga),
                    'repeticoes': serie.repeticoes
                })
            
            return resultado
        except Exception as e:
            logger.error(f"Erro ao buscar últimas séries: {e}")
            return []
    
    # =============================================
    # MÉTODOS DE UTILIDADE
    # =============================================
    
    @staticmethod
    def get_musculo_id(nome_musculo):
        """Retorna ID do músculo base pelo nome"""
        try:
            musculo = Musculo.query.filter_by(nome_exibicao=nome_musculo).first()
            return musculo.id if musculo else None
        except Exception as e:
            logger.error(f"Erro ao buscar ID do músculo {nome_musculo}: {e}")
            return None
    
    @staticmethod
    def get_all_musculos():
        """Retorna todos os músculos base"""
        try:
            return Musculo.query.order_by(Musculo.nome_exibicao).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar músculos")
            return []
    
    @staticmethod
    def get_all_musculos_nomes():
        """Retorna lista com nomes de exibição dos músculos"""
        try:
            musculos = ExercicioService.get_all_musculos()
            return [m.nome_exibicao for m in musculos]
        except Exception as e:
            logger.error(f"Erro ao buscar nomes dos músculos: {e}")
            return []
    
    @staticmethod
    def get_estatisticas_exercicio(exercicio_id, user_id=None):
        """Retorna estatísticas de um exercício"""
        try:
            from models import RegistroTreino, HistoricoTreino
            from sqlalchemy import func
            
            if user_id is None:
                user_id = BaseService.get_current_user_id()
            if not user_id:
                return {}
            
            # Buscar todos os registros do exercício
            registros = RegistroTreino.query.filter_by(
                exercicio_id=exercicio_id,
                user_id=user_id
            ).all()
            
            if not registros:
                return {}
            
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