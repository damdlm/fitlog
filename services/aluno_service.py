"""Serviço para operações com alunos"""

from models import db, User, AlunoProfessor
from . import BaseService
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AlunoService(BaseService):
    """Gerencia operações relacionadas a alunos"""
    
    @staticmethod
    def get_alunos(professor_id=None):
        """
        Retorna lista de alunos (do professor ou todos se admin)
        
        Args:
            professor_id: ID do professor (opcional)
        
        Returns:
            list: Lista de objetos User (alunos)
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return []
            
            # Admin vê todos os alunos
            if current_user.is_admin:
                query = User.query.filter_by(tipo_usuario='aluno', ativo=True)
                return query.order_by(User.nome_completo).all()
            
            # Professor vê seus alunos
            if current_user.is_professor():
                return BaseService.get_alunos_do_professor(professor_id or current_user.id)
            
            # Aluno vê apenas a si mesmo
            if current_user.is_aluno():
                return [current_user] if current_user.ativo else []
            
            return []
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar alunos")
            return []
    
    @staticmethod
    def get_aluno_by_id(aluno_id):
        """
        Retorna um aluno específico (com verificação de permissão)
        
        Args:
            aluno_id: ID do aluno
        
        Returns:
            User: Objeto aluno ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return None
            
            aluno = User.query.get(aluno_id)
            if not aluno or aluno.tipo_usuario != 'aluno' or not aluno.ativo:
                return None
            
            # Verificar permissão
            if current_user.pode_acessar_dados_de(aluno):
                return aluno
            
            logger.warning(f"Usuário {current_user.id} tentou acessar aluno {aluno_id} sem permissão")
            return None
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar aluno {aluno_id}")
            return None
    
    @staticmethod
    def associar_professor(aluno_id, professor_id):
        """
        Associa um aluno a um professor
        
        Args:
            aluno_id: ID do aluno
            professor_id: ID do professor
        
        Returns:
            bool: True se sucesso
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return False
            
            # Apenas admin ou o próprio professor pode fazer associação
            if not (current_user.is_admin or current_user.id == professor_id):
                logger.warning(f"Usuário {current_user.id} tentou associar aluno {aluno_id} ao professor {professor_id} sem permissão")
                return False
            
            # Verificar se aluno e professor existem
            aluno = User.query.get(aluno_id)
            professor = User.query.get(professor_id)
            
            if not aluno or aluno.tipo_usuario != 'aluno':
                logger.warning(f"Aluno {aluno_id} não encontrado ou não é aluno")
                return False
            
            if not professor or professor.tipo_usuario != 'professor':
                logger.warning(f"Professor {professor_id} não encontrado ou não é professor")
                return False
            
            # Verificar se já existe associação ativa
            assoc_existente = AlunoProfessor.query.filter_by(
                aluno_id=aluno_id,
                ativo=True
            ).first()
            
            if assoc_existente:
                if assoc_existente.professor_id == professor_id:
                    logger.info(f"Aluno {aluno_id} já está associado ao professor {professor_id}")
                    return True
                else:
                    # Desativar associação antiga
                    assoc_existente.ativo = False
            
            # Criar nova associação
            nova_assoc = AlunoProfessor(
                aluno_id=aluno_id,
                professor_id=professor_id,
                data_associacao=datetime.now(),
                ativo=True
            )
            db.session.add(nova_assoc)
            db.session.commit()
            
            logger.info(f"Aluno {aluno_id} associado ao professor {professor_id}")
            return True
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao associar aluno a professor")
            return False
    
    @staticmethod
    def desassociar_professor(aluno_id):
        """
        Remove associação de um aluno com seu professor
        
        Args:
            aluno_id: ID do aluno
        
        Returns:
            bool: True se sucesso
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return False
            
            assoc = AlunoProfessor.query.filter_by(
                aluno_id=aluno_id,
                ativo=True
            ).first()
            
            if not assoc:
                logger.warning(f"Aluno {aluno_id} não tem professor associado")
                return False
            
            # Verificar permissão
            if not (current_user.is_admin or current_user.id == assoc.professor_id):
                logger.warning(f"Usuário {current_user.id} tentou desassociar aluno {aluno_id} sem permissão")
                return False
            
            assoc.ativo = False
            db.session.commit()
            
            logger.info(f"Aluno {aluno_id} desassociado do professor {assoc.professor_id}")
            return True
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao desassociar aluno")
            return False
    
    @staticmethod
    def criar_aluno(dados):
        """
        Cria um novo aluno (apenas admin pode)
        
        Args:
            dados: Dicionário com dados do aluno
        
        Returns:
            User: Novo aluno ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user or not current_user.is_admin:
                logger.warning("Tentativa de criar aluno sem permissão de admin")
                return None
            
            from werkzeug.security import generate_password_hash
            
            # Criar usuário
            aluno = User(
                username=dados['username'],
                email=dados['email'],
                tipo_usuario='aluno',
                nome_completo=dados.get('nome_completo'),
                telefone=dados.get('telefone'),
                data_nascimento=dados.get('data_nascimento'),
                ativo=True
            )
            aluno.set_password(dados['password'])
            
            db.session.add(aluno)
            db.session.commit()
            
            logger.info(f"Aluno {aluno.username} criado por admin {current_user.id}")
            return aluno
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao criar aluno")
            return None
    
    @staticmethod
    def atualizar_aluno(aluno_id, dados):
        """
        Atualiza dados de um aluno
        
        Args:
            aluno_id: ID do aluno
            dados: Dicionário com dados a atualizar
        
        Returns:
            User: Aluno atualizado ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return None
            
            aluno = AlunoService.get_aluno_by_id(aluno_id)
            if not aluno:
                return None
            
            # Verificar permissão
            if not (current_user.is_admin or current_user.id == aluno_id):
                logger.warning(f"Usuário {current_user.id} tentou atualizar aluno {aluno_id} sem permissão")
                return None
            
            # Atualizar campos
            if 'nome_completo' in dados:
                aluno.nome_completo = dados['nome_completo']
            if 'telefone' in dados:
                aluno.telefone = dados['telefone']
            if 'email' in dados and dados['email'] != aluno.email:
                # Verificar se email já existe
                if User.query.filter_by(email=dados['email']).first():
                    logger.warning(f"Email {dados['email']} já está em uso")
                    return None
                aluno.email = dados['email']
            
            db.session.commit()
            logger.info(f"Aluno {aluno_id} atualizado")
            return aluno
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar aluno {aluno_id}")
            return None