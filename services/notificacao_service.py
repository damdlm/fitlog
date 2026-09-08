"""Serviço de notificações in-app entre aluno e professor vinculados.

Sem infraestrutura de push (ver static/sw.js, que só existe pra permitir
"Instalar app") -- as notificações aqui vivem só no banco e são lidas
via polling pela tela/menu de notificações (ver static/js/modules/
notificacoes.js).

Toda criação de notificação é "best effort": uma falha aqui nunca deve
quebrar a ação principal do usuário (salvar um treino, editar uma
versão etc) -- por isso _criar()/criar_ou_agrupar() engolem e logam
qualquer exceção em vez de propagar.
"""

import logging
import random
from datetime import datetime, timedelta, timezone

from models import db, Notificacao, User
from services.base_service import BaseService

logger = logging.getLogger(__name__)


class NotificacaoService(BaseService):

    LIMITE_PADRAO = 20

    # Duas categorias usadas nos filtros/abas da tela de notificações
    # (ver routes/notificacao_routes.py e templates/notificacoes/lista.html).
    TIPOS_TREINO = {'treino_finalizado', 'treino_editado', 'treino_excluido', 'treino_adicionado'}
    TIPOS_VERSAO = {'versao_editada', 'versao_finalizada', 'versao_excluida'}

    # Eventos do mesmo tipo/alvo dentro dessa janela viram UMA notificação
    # com contador (ver criar_ou_agrupar), em vez de uma linha por evento --
    # evita que 3 salvamentos seguidos do mesmo treino virem spam.
    JANELA_AGRUPAMENTO_MINUTOS = 10

    # Notificações já lidas mais antigas que isso são candidatas a limpeza
    # (ver limpar_antigas). Não lidas nunca são apagadas automaticamente.
    RETENCAO_LIDAS_DIAS = 90

    # Chance (1 em N) de disparar a limpeza automática a cada notificação
    # nova criada -- gambiarra deliberada: o projeto não tem um
    # scheduler/cron rodando (ver Procfile), então em vez de exigir essa
    # infraestrutura só pra isso, a limpeza "pega carona" no tráfego
    # normal do app. Barato o suficiente (é 1 DELETE indexado) pra não
    # importar rodar de vez em quando sem necessidade.
    CHANCE_LIMPEZA_AUTOMATICA = 500

    @staticmethod
    def _nome(usuario):
        if not usuario:
            return 'Alguém'
        return usuario.nome_completo or usuario.username

    @staticmethod
    def montar_diff_exercicios(nomes_antes, nomes_depois):
        """Compara a lista de nomes de exercícios antes/depois de um
        salvamento de treino e monta uma frase curta descrevendo o que
        mudou de fato -- em vez do genérico "atualizou os exercícios".

        Retorna None se a lista de exercícios não mudou (o usuário só
        reordenou, editou uma observação, ou o nome/descrição do
        treino) -- quem chama decide o texto genérico nesse caso.
        """
        antes_set, depois_set = set(nomes_antes), set(nomes_depois)
        removidos = [n for n in nomes_antes if n not in depois_set]
        adicionados = [n for n in nomes_depois if n not in antes_set]

        if not removidos and not adicionados:
            return None

        # Caso mais comum na prática: substituiu 1 exercício por outro.
        if len(removidos) == 1 and len(adicionados) == 1:
            return f'trocou "{removidos[0]}" por "{adicionados[0]}"'

        def _lista(nomes, limite=3):
            texto = ', '.join(f'"{n}"' for n in nomes[:limite])
            if len(nomes) > limite:
                texto += f' e mais {len(nomes) - limite}'
            return texto

        partes = []
        if adicionados:
            partes.append(f'adicionou {_lista(adicionados)}')
        if removidos:
            partes.append(f'removeu {_lista(removidos)}')
        return '; '.join(partes)

    @staticmethod
    def _criar(destinatario_id, remetente_id, tipo, titulo, mensagem, url=None):
        """Cria e persiste uma notificação nova (sem tentar agrupar).
        Nunca levanta exceção -- retorna None em caso de falha."""
        if not destinatario_id:
            return None
        try:
            notificacao = Notificacao(
                destinatario_id=destinatario_id,
                remetente_id=remetente_id,
                tipo=tipo,
                titulo=titulo[:150],
                mensagem=mensagem[:300],
                url=url,
            )
            db.session.add(notificacao)
            db.session.commit()
            return notificacao
        except Exception:
            db.session.rollback()
            logger.exception(
                "Falha ao criar notificação (tipo=%s, destinatario=%s)",
                tipo, destinatario_id
            )
            return None

    @staticmethod
    def criar_ou_agrupar(destinatario_id, remetente_id, tipo, titulo, mensagem,
                          url=None, chave_agrupamento=None):
        """Como _criar, mas com agrupamento em rajada: se já existe uma
        notificação NÃO LIDA do mesmo destinatário com a mesma
        chave_agrupamento criada há menos de JANELA_AGRUPAMENTO_MINUTOS,
        atualiza ela (mensagem mais recente + contador) em vez de criar
        uma nova. Sem chave_agrupamento, sempre cria nova (mesmo
        comportamento de _criar).

        "Sobe" a notificação agrupada pro topo da lista (created_at =
        agora) -- faz sentido pro usuário: o que importa é a última
        alteração, não quando a rajada começou.
        """
        if not destinatario_id:
            return None
        try:
            existente = None
            if chave_agrupamento:
                limite = datetime.now(timezone.utc) - timedelta(minutes=NotificacaoService.JANELA_AGRUPAMENTO_MINUTOS)
                existente = Notificacao.query.filter_by(
                    destinatario_id=destinatario_id,
                    chave_agrupamento=chave_agrupamento,
                    lida=False,
                ).filter(Notificacao.created_at >= limite) \
                 .order_by(Notificacao.created_at.desc()) \
                 .first()

            if existente:
                existente.titulo = titulo[:150]
                existente.mensagem = mensagem[:300]
                if url:
                    existente.url = url
                existente.remetente_id = remetente_id
                existente.ocorrencias = (existente.ocorrencias or 1) + 1
                existente.created_at = datetime.now(timezone.utc)
                db.session.commit()
                return existente

            notificacao = Notificacao(
                destinatario_id=destinatario_id,
                remetente_id=remetente_id,
                tipo=tipo,
                titulo=titulo[:150],
                mensagem=mensagem[:300],
                url=url,
                chave_agrupamento=chave_agrupamento,
            )
            db.session.add(notificacao)
            db.session.commit()

            # Limpeza preguiçosa -- ver CHANCE_LIMPEZA_AUTOMATICA. Depois do
            # commit acima, pra não misturar as duas transações.
            if random.randint(1, NotificacaoService.CHANCE_LIMPEZA_AUTOMATICA) == 1:
                NotificacaoService.limpar_antigas()

            return notificacao
        except Exception:
            db.session.rollback()
            logger.exception(
                "Falha ao criar/agrupar notificação (tipo=%s, destinatario=%s, chave=%s)",
                tipo, destinatario_id, chave_agrupamento
            )
            return None

    @staticmethod
    def notificar_professor(aluno, tipo, titulo, mensagem, url=None, chave_agrupamento=None):
        """Notifica o professor vinculado ao aluno, se houver vínculo
        ativo. Sem professor vinculado, não faz nada (aluno sem
        professor é um caso normal do app -- ver AlunoProfessor)."""
        professor = BaseService.get_professor_do_aluno(aluno.id)
        if not professor:
            return None
        return NotificacaoService.criar_ou_agrupar(
            destinatario_id=professor.id,
            remetente_id=aluno.id,
            tipo=tipo,
            titulo=titulo,
            mensagem=mensagem,
            url=url,
            chave_agrupamento=chave_agrupamento,
        )

    @staticmethod
    def notificar_aluno(aluno_id, professor, tipo, titulo, mensagem, url=None, chave_agrupamento=None):
        """Notifica o aluno sobre uma ação feita pelo professor no
        treino dele."""
        return NotificacaoService.criar_ou_agrupar(
            destinatario_id=aluno_id,
            remetente_id=professor.id if professor else None,
            tipo=tipo,
            titulo=titulo,
            mensagem=mensagem,
            url=url,
            chave_agrupamento=chave_agrupamento,
        )

    @staticmethod
    def listar(user_id, apenas_nao_lidas=False, categoria=None, remetente_id=None, limit=None):
        """categoria: None (todas), 'treinos' ou 'versoes' -- ver
        TIPOS_TREINO/TIPOS_VERSAO. remetente_id filtra por quem causou o
        evento (ex: professor filtrando notificações de um aluno
        específico na visão dele)."""
        query = Notificacao.query.filter_by(destinatario_id=user_id)
        if apenas_nao_lidas:
            query = query.filter_by(lida=False)
        if categoria == 'treinos':
            query = query.filter(Notificacao.tipo.in_(NotificacaoService.TIPOS_TREINO))
        elif categoria == 'versoes':
            query = query.filter(Notificacao.tipo.in_(NotificacaoService.TIPOS_VERSAO))
        if remetente_id:
            query = query.filter_by(remetente_id=remetente_id)
        query = query.order_by(Notificacao.created_at.desc())
        return query.limit(limit or NotificacaoService.LIMITE_PADRAO).all()

    @staticmethod
    def remetentes_disponiveis(user_id):
        """Lista (id, nome) de quem já mandou notificação pra esse
        usuário -- usada pra popular o filtro "por aluno" na tela do
        professor (cada aluno só tem um professor, então pro aluno essa
        lista teria no máximo 1 item -- o filtro só aparece na prática
        quando faz sentido, ver template)."""
        ids = [
            row[0] for row in
            db.session.query(Notificacao.remetente_id)
            .filter_by(destinatario_id=user_id)
            .filter(Notificacao.remetente_id.isnot(None))
            .distinct()
            .all()
        ]
        if not ids:
            return []
        usuarios = User.query.filter(User.id.in_(ids)).all()
        return sorted(
            ((u.id, u.nome_completo or u.username) for u in usuarios),
            key=lambda item: item[1].lower()
        )

    @staticmethod
    def contar_nao_lidas(user_id):
        return Notificacao.query.filter_by(destinatario_id=user_id, lida=False).count()

    @staticmethod
    def marcar_como_lida(notificacao_id, user_id):
        """Marca uma notificação como lida -- só se ela pertencer ao
        usuário (evita que um ID adivinhado marque notificação de
        outra pessoa)."""
        notificacao = Notificacao.query.filter_by(
            id=notificacao_id, destinatario_id=user_id
        ).first()
        if not notificacao:
            return False
        try:
            notificacao.lida = True
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Falha ao marcar notificação %s como lida", notificacao_id)
            return False

    @staticmethod
    def marcar_todas_como_lidas(user_id):
        try:
            Notificacao.query.filter_by(destinatario_id=user_id, lida=False) \
                .update({'lida': True})
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Falha ao marcar todas as notificações do usuário %s como lidas", user_id)
            return False

    @staticmethod
    def limpar_antigas(dias=None):
        """Apaga notificações já lidas mais antigas que `dias` dias
        (RETENCAO_LIDAS_DIAS por padrão). Não lidas nunca são tocadas,
        mesmo que antigas -- o usuário ainda não viu.

        Chamado tanto pela "limpeza preguiçosa" (ver
        CHANCE_LIMPEZA_AUTOMATICA) quanto manualmente via
        `flask limpar-notificacoes` (ver app.py) ou
        scripts/limpar_notificacoes_antigas.py, pra quem preferir um
        cron externo de verdade em vez de depender do tráfego do app.

        Retorna o número de linhas apagadas, ou None em caso de falha.
        """
        dias = dias or NotificacaoService.RETENCAO_LIDAS_DIAS
        cutoff = datetime.now(timezone.utc) - timedelta(days=dias)
        try:
            apagadas = Notificacao.query.filter(
                Notificacao.lida.is_(True),
                Notificacao.created_at < cutoff,
            ).delete(synchronize_session=False)
            db.session.commit()
            if apagadas:
                logger.info("Limpeza de notificações: %s notificação(ões) lida(s) com mais de %s dias removida(s).", apagadas, dias)
            return apagadas
        except Exception:
            db.session.rollback()
            logger.exception("Falha na limpeza automática de notificações antigas")
            return None
