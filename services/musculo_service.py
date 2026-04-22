"""Serviço para operações com músculos — usa Musculo (tabela unificada)"""

from models import Musculo
from .base_service import BaseService
import logging

logger = logging.getLogger(__name__)

class MusculoService(BaseService):
    """Gerencia operações relacionadas a músculos"""

    @staticmethod
    def get_all():
        """Retorna todos os músculos"""
        try:
            return Musculo.query.order_by(Musculo.nome_exibicao).all()
        except Exception as e:
            logger.error(f"Erro ao buscar músculos: {e}")
            return []

    @staticmethod
    def get_all_nomes():
        """Retorna lista com nomes de exibição dos músculos"""
        try:
            return [m.nome_exibicao for m in MusculoService.get_all()]
        except Exception as e:
            logger.error(f"Erro ao buscar nomes dos músculos: {e}")
            return []

    @staticmethod
    def get_by_id(musculo_id):
        """Retorna músculo por ID"""
        try:
            return db.session.get(Musculo, musculo_id)
        except Exception as e:
            logger.error(f"Erro ao buscar músculo {musculo_id}: {e}")
            return None

    @staticmethod
    def get_by_nome_exibicao(nome_exibicao):
        """Retorna músculo pelo nome de exibição"""
        try:
            return Musculo.query.filter_by(nome_exibicao=nome_exibicao).first()
        except Exception as e:
            logger.error(f"Erro ao buscar músculo {nome_exibicao}: {e}")
            return None

    @staticmethod
    def get_by_nome(nome):
        """Retorna músculo pelo nome (lowercase)"""
        try:
            return Musculo.query.filter_by(nome=nome.lower()).first()
        except Exception as e:
            logger.error(f"Erro ao buscar músculo {nome}: {e}")
            return None

    @staticmethod
    def get_or_create(nome_exibicao):
        """Retorna músculo existente ou cria um novo"""
        try:
            musculo = Musculo.query.filter_by(nome_exibicao=nome_exibicao).first()
            if not musculo:
                from models import db
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
            return None