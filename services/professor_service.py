"""Serviço para operações com professores"""

from models import db, User, AlunoProfessor
from . import BaseService
import logging

logger = logging.getLogger(__name__)

class ProfessorService(BaseService):
    """Gerencia operações relacionadas a professores"""
    
    @staticmethod
    def get_professores():
        """
        Retorna lista de todos os professores (apenas admin)
        
        Returns:
            list: Lista de objetos User (professores)
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user or not current_user.is_admin:
                logger.warning("Tentativa de listar professores sem permissão de admin")
                return []
            
            return User.query.filter_by(tipo_usuario='professor', ativo=True)\
                .order_by(User.nome_completo).all()
                
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar professores")
            return []
    
    @staticmethod
    def get_professor_by_id(professor_id):
        """
        Retorna um professor específico
        
        Args:
            professor_id: ID do professor
        
        Returns:
            User: Objeto professor ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return None
            
            professor = User.query.get(professor_id)
            if not professor or professor.tipo_usuario != 'professor' or not professor.ativo:
                return None
            
            # Qualquer um pode ver dados básicos do professor
            # (para seleção em formulários)
            return professor
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar professor {professor_id}")
            return None
    
    @staticmethod
    def criar_professor(dados):
        """
        Cria um novo professor (apenas admin)
        
        Args:
            dados: Dicionário com dados do professor
        
        Returns:
            User: Novo professor ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user or not current_user.is_admin:
                logger.warning("Tentativa de criar professor sem permissão de admin")
                return None
            
            # Criar usuário
            professor = User(
                username=dados['username'],
                email=dados['email'],
                tipo_usuario='professor',
                nome_completo=dados.get('nome_completo'),
                telefone=dados.get('telefone'),
                ativo=True
            )
            professor.set_password(dados['password'])
            
            db.session.add(professor)
            db.session.commit()
            
            logger.info(f"Professor {professor.username} criado por admin {current_user.id}")
            return professor
            
        except Exception as e:
            BaseService.handle_error(e, "Erro ao criar professor")
            return None
    
    @staticmethod
    def get_alunos_do_professor(professor_id=None):
        """
        Retorna alunos de um professor específico
        
        Args:
            professor_id: ID do professor (usa atual se None)
        
        Returns:
            list: Lista de alunos
        """
        try:
            if not professor_id:
                current_user = BaseService.get_current_user()
                if not current_user or not current_user.is_professor():
                    return []
                professor_id = current_user.id
            else:
                # Verificar permissão para ver alunos de outro professor
                current_user = BaseService.get_current_user()
                if not current_user or not (current_user.is_admin or current_user.id == professor_id):
                    logger.warning(f"Usuário {current_user.id} tentou ver alunos do professor {professor_id} sem permissão")
                    return []
            
            return BaseService.get_alunos_do_professor(professor_id)
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar alunos do professor {professor_id}")
            return []
    
    @staticmethod
    def atualizar_professor(professor_id, dados):
        """
        Atualiza dados de um professor
        
        Args:
            professor_id: ID do professor
            dados: Dicionário com dados a atualizar
        
        Returns:
            User: Professor atualizado ou None
        """
        try:
            current_user = BaseService.get_current_user()
            if not current_user:
                return None
            
            # Apenas admin ou o próprio professor pode atualizar
            if not (current_user.is_admin or current_user.id == professor_id):
                logger.warning(f"Usuário {current_user.id} tentou atualizar professor {professor_id} sem permissão")
                return None
            
            professor = User.query.get(professor_id)
            if not professor or professor.tipo_usuario != 'professor':
                return None
            
            # Atualizar campos
            if 'nome_completo' in dados:
                professor.nome_completo = dados['nome_completo']
            if 'telefone' in dados:
                professor.telefone = dados['telefone']
            if 'email' in dados and dados['email'] != professor.email:
                if User.query.filter_by(email=dados['email']).first():
                    logger.warning(f"Email {dados['email']} já está em uso")
                    return None
                professor.email = dados['email']
            
            db.session.commit()
            logger.info(f"Professor {professor_id} atualizado")
            return professor
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar professor {professor_id}")
            return None