"""Serviço para consultar treinos (letras A/B/C...) do usuário.

Desde a remoção da tabela `treinos` (o treino deixou de ser uma
entidade compartilhada entre versões -- cada versão tem seus próprios
treinos, identificados pelo campo `codigo` diretamente em
`TreinoVersao`), este serviço apenas oferece consultas de leitura sobre
`TreinoVersao`, mantendo os nomes/assinaturas usados pelo restante do
app (dashboard, calendário, estatísticas), que não precisou mudar.

Criação/edição/exclusão de treino agora acontece exclusivamente através
da tela "Cadastrar Treinos" (ver VersaoService.adicionar_treino_livre /
salvar_treino_livre / remover_treino_livre).
"""
from models import TreinoVersao, VersaoGlobal
from .base_service import BaseService
import logging

logger = logging.getLogger(__name__)


class TreinoService(BaseService):

    @staticmethod
    def get_all(user_id=None):
        """Todos os treinos do usuário, de todas as versões (inclusive encerradas)."""
        try:
            target_user_id = user_id or BaseService.get_current_user_id()
            query = TreinoVersao.query.join(VersaoGlobal, TreinoVersao.versao_id == VersaoGlobal.id)
            if target_user_id:
                query = query.filter(VersaoGlobal.user_id == target_user_id)
            return query.order_by(TreinoVersao.codigo).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treinos")
            return []

    @staticmethod
    def get_by_id(treino_versao_id, user_id=None):
        """Busca um treino (TreinoVersao) pelo seu ID, garantindo que pertence ao usuário."""
        try:
            target_user_id = user_id or BaseService.get_current_user_id()
            query = TreinoVersao.query.join(
                VersaoGlobal, TreinoVersao.versao_id == VersaoGlobal.id
            ).filter(TreinoVersao.id == treino_versao_id)
            if target_user_id:
                query = query.filter(VersaoGlobal.user_id == target_user_id)
            return query.first()
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao buscar treino {treino_versao_id}")
            return None

    @staticmethod
    def get_da_versao_ativa(user_id=None):
        """Treinos da versão ativa (em andamento) do usuário."""
        try:
            from services.versao_service import VersaoService
            target_user_id = user_id or BaseService.get_current_user_id()
            if not target_user_id:
                return []
            versao_ativa = VersaoService.get_ativa(user_id=target_user_id)
            if not versao_ativa:
                return []
            return TreinoVersao.query.filter_by(
                versao_id=versao_ativa.id
            ).order_by(TreinoVersao.codigo).all()
        except Exception as e:
            BaseService.handle_error(e, "Erro ao buscar treinos da versão ativa")
            return []
