"""Serviço de cobrança/assinaturas (Asaas).

Duas responsabilidades bem separadas de propósito:

1. Cálculo de acesso/tier -- sempre lendo o estado JÁ sincronizado no
   banco (tabela assinaturas), nunca chamando a API do Asaas a cada
   requisição. É o que os decorators e as rotas do dia a dia usam
   (rápido, O(1) via FK única em usuario_id, sem I/O externo).

2. Sincronização com o gateway -- criação de cliente/assinatura no
   Asaas e processamento de webhooks. É o único lugar que fala HTTP
   com o Asaas e o único lugar autorizado a escrever status='active'
   no banco -- nunca a partir de uma resposta direta ao navegador do
   usuário (isso seria falsificável por qualquer um que soubesse a URL).
"""

import hmac
import logging
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from models import db, AlunoProfessor, Assinatura, EventoWebhookAsaas, Plano, User

logger = logging.getLogger(__name__)

TRIAL_DIAS_ALUNO = 30
CARENCIA_DIAS_PAGAMENTO_ATRASADO = 3
REQUEST_TIMEOUT_SECONDS = 10

ASAAS_BASE_URL_SANDBOX = "https://sandbox.asaas.com/api/v3"
ASAAS_BASE_URL_PRODUCAO = "https://api.asaas.com/v3"

# Eventos do Asaas que realmente importam pro nosso ciclo de vida.
# Lista completa de eventos: https://docs.asaas.com/docs/webhook-events
# -- conferir contra a documentação atual antes de ativar em produção,
# pois nomes de evento podem mudar entre versões da API.
EVENTOS_CONFIRMACAO_PAGAMENTO = ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED')
EVENTOS_ATRASO = ('PAYMENT_OVERDUE',)
EVENTOS_CANCELAMENTO = ('PAYMENT_DELETED', 'PAYMENT_REFUNDED', 'SUBSCRIPTION_DELETED')


class BillingService:

    # ================================================================
    # Acesso / tier -- só lê o banco local, sem chamar o gateway
    # ================================================================

    @staticmethod
    def iniciar_trial_aluno(usuario: User) -> Assinatura:
        """Cria a assinatura em estado 'trialing' para um aluno recém-
        cadastrado. Chamar uma única vez, no fluxo de registro (idealmente
        na mesma transação que cria o User) -- é idempotente por
        segurança (se já existir, só retorna a existente sem duplicar)."""
        if usuario.assinatura is not None:
            return usuario.assinatura

        assinatura = Assinatura(
            usuario_id=usuario.id,
            status='trialing',
            trial_termina_em=datetime.now(timezone.utc) + timedelta(days=TRIAL_DIAS_ALUNO),
        )
        db.session.add(assinatura)
        db.session.commit()
        logger.info('Trial de %s dias iniciado para aluno %s', TRIAL_DIAS_ALUNO, usuario.id)
        return assinatura

    @staticmethod
    def aluno_tem_acesso_premium(usuario: User) -> bool:
        """Único ponto de verdade para gatear Estatísticas/FitBot.
        Usado pelo decorator aluno_premium_required -- ver
        utils/decorators.py."""
        assinatura = usuario.assinatura
        if assinatura is None:
            return False
        return assinatura.acesso_premium_ativo()

    @staticmethod
    def calcular_tier_professor(professor: User) -> Plano | None:
        """Calcula qual Plano de professor corresponde à contagem ATUAL
        de alunos ativos vinculados. Retorna None para a faixa gratuita
        (0-2 alunos). Isto é o tier "correto" agora -- não confundir com
        o plano efetivamente sendo cobrado hoje (assinatura.plano_id),
        que só muda via aplicar_mudanca_tier_professor após notificação
        (ver verificar_mudancas_tier_professores)."""
        total_alunos = AlunoProfessor.query.filter_by(
            professor_id=professor.id, ativo=True
        ).count()

        if total_alunos <= 2:
            return None

        return (
            Plano.query
            .filter(
                Plano.tipo_usuario == 'professor',
                Plano.ativo.is_(True),
                Plano.min_alunos <= total_alunos,
                db.or_(Plano.max_alunos.is_(None), Plano.max_alunos >= total_alunos),
            )
            .first()
        )

    @staticmethod
    def verificar_mudancas_tier_professores() -> list[dict]:
        """Varre todos os professores com assinatura ativa e retorna os
        que estão num tier diferente do calculado agora pela contagem
        de alunos -- SEM aplicar nada. Pensado para rodar como job
        periódico (ex: diário) cujo resultado alimenta um e-mail de aviso
        ("seu plano vai mudar de X para Y") -- a troca de valor cobrado
        só deve ser aplicada depois dessa notificação e nunca no mesmo
        ciclo em que o aluno passou a faixa, para não surpreender o
        professor com uma cobrança diferente sem aviso prévio (CDC,
        art. 6º -- direito à informação clara sobre o serviço).

        A aplicação em si (trocar assinatura.plano_id e sincronizar o
        valor no Asaas) é um passo separado, deliberadamente não
        automático aqui.
        """
        mudancas = []
        professores = User.query.filter_by(tipo_usuario='professor', ativo=True).all()
        for professor in professores:
            tier_novo = BillingService.calcular_tier_professor(professor)
            assinatura = professor.assinatura
            tier_atual = assinatura.plano if assinatura else None
            if (tier_atual is None and tier_novo is None):
                continue
            if tier_atual is not None and tier_novo is not None and tier_atual.id == tier_novo.id:
                continue
            mudancas.append({
                'professor': professor,
                'tier_atual': tier_atual,
                'tier_novo': tier_novo,
            })
        return mudancas

    # ================================================================
    # Integração com o gateway (Asaas)
    # ================================================================

    @staticmethod
    def _base_url() -> str:
        env = current_app.config.get('ASAAS_ENV', 'sandbox')
        return ASAAS_BASE_URL_PRODUCAO if env == 'production' else ASAAS_BASE_URL_SANDBOX

    @staticmethod
    def _headers() -> dict:
        api_key = current_app.config.get('ASAAS_API_KEY')
        if not api_key:
            raise RuntimeError(
                'ASAAS_API_KEY não configurada -- defina a variável de '
                'ambiente antes de chamar a API do Asaas.'
            )
        return {'access_token': api_key, 'Content-Type': 'application/json'}

    @staticmethod
    def criar_assinatura_checkout(usuario: User, plano: Plano) -> str:
        """Cria (ou reaproveita) o cliente no Asaas e uma assinatura
        recorrente para ele, retornando a URL de checkout hospedado pelo
        Asaas -- o navegador do usuário é redirecionado para lá, e o
        dado de cartão nunca passa pelo nosso servidor (mantém o fitlog
        em PCI SAQ A, o nível mais simples de conformidade).

        ATENÇÃO: nomes de campo/endpoint aqui seguem a documentação da
        API do Asaas no momento em que este serviço foi desenhado --
        conferir contra https://docs.asaas.com/reference antes do
        primeiro teste real em sandbox, e ajustar se necessário.
        """
        assinatura = usuario.assinatura
        if assinatura is None:
            raise ValueError('Usuário sem registro de Assinatura -- chame iniciar_trial_aluno ou crie o registro primeiro.')

        customer_id = assinatura.gateway_customer_id
        if not customer_id:
            resp = requests.post(
                f'{BillingService._base_url()}/customers',
                json={'name': usuario.nome_completo or usuario.username, 'email': usuario.email},
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            customer_id = resp.json()['id']
            assinatura.gateway_customer_id = customer_id
            db.session.commit()

        resp = requests.post(
            f'{BillingService._base_url()}/subscriptions',
            json={
                'customer': customer_id,
                'billingType': 'UNDEFINED',  # deixa o usuário escolher cartão/pix/boleto no checkout
                'value': plano.preco_centavos / 100,
                'cycle': 'MONTHLY',
                'description': plano.nome,
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        dados = resp.json()

        assinatura.gateway_subscription_id = dados['id']
        assinatura.plano_id = plano.id
        db.session.commit()

        return dados.get('invoiceUrl') or dados.get('checkoutUrl')

    @staticmethod
    def _validar_token_webhook(token_recebido: str) -> bool:
        """Asaas envia, em cada webhook, o token configurado no painel
        (Integrações > Webhooks) no header 'asaas-access-token'.
        Comparação em tempo constante (hmac.compare_digest) para não
        vazar o valor esperado por timing attack."""
        token_esperado = current_app.config.get('ASAAS_WEBHOOK_TOKEN')
        if not token_esperado or not token_recebido:
            return False
        return hmac.compare_digest(token_esperado, token_recebido)

    @staticmethod
    def processar_webhook(payload: dict) -> bool:
        """Processa um evento de webhook do Asaas de forma idempotente.
        A validação do token do header é feita ANTES de chamar este
        método (ver routes/billing_routes.py) -- este método assume que
        o payload já é confiável.

        Retorna True se processado (ou já tinha sido processado antes),
        False se o payload não tiver o formato mínimo esperado.
        """
        event_id = payload.get('id')
        tipo_evento = payload.get('event')
        if not event_id or not tipo_evento:
            logger.warning('Webhook Asaas sem id/event no payload, ignorado')
            return False

        # Idempotência: Asaas reenvia o mesmo evento se não recebeu 200
        # a tempo da tentativa anterior -- processar duas vezes pode
        # gerar dupla liberação de acesso ou dupla baixa de pagamento.
        if EventoWebhookAsaas.query.filter_by(event_id=event_id).first():
            logger.info('Webhook Asaas %s já processado antes, ignorando', event_id)
            return True

        payment = payload.get('payment') or {}
        subscription_id = payment.get('subscription')

        if subscription_id:
            assinatura = Assinatura.query.filter_by(gateway_subscription_id=subscription_id).first()
            if assinatura:
                BillingService._aplicar_evento(assinatura, tipo_evento)
            else:
                logger.warning(
                    'Webhook Asaas para subscription %s sem Assinatura correspondente no banco',
                    subscription_id,
                )

        db.session.add(EventoWebhookAsaas(event_id=event_id, tipo_evento=tipo_evento))
        db.session.commit()
        return True

    @staticmethod
    def _aplicar_evento(assinatura: Assinatura, tipo_evento: str):
        agora = datetime.now(timezone.utc)
        if tipo_evento in EVENTOS_CONFIRMACAO_PAGAMENTO:
            assinatura.status = 'active'
            assinatura.carencia_termina_em = None
        elif tipo_evento in EVENTOS_ATRASO:
            assinatura.status = 'past_due'
            assinatura.carencia_termina_em = agora + timedelta(days=CARENCIA_DIAS_PAGAMENTO_ATRASADO)
        elif tipo_evento in EVENTOS_CANCELAMENTO:
            assinatura.status = 'canceled'
            assinatura.cancelado_em = agora
        else:
            logger.debug('Evento Asaas %s sem tratamento específico, ignorado', tipo_evento)

    @staticmethod
    def expirar_carencias_vencidas():
        """Job periódico (ex: a cada hora): move para 'blocked' quem
        esgotou a carência de pagamento atrasado sem regularizar. Não é
        feito dentro de acesso_premium_ativo() -- esse método só LÊ o
        status; quem escreve é sempre um processo explícito (webhook ou
        este job), nunca uma leitura incidental."""
        agora = datetime.now(timezone.utc)
        vencidas = Assinatura.query.filter(
            Assinatura.status == 'past_due',
            Assinatura.carencia_termina_em.isnot(None),
            Assinatura.carencia_termina_em <= agora,
        ).all()
        for assinatura in vencidas:
            assinatura.status = 'blocked'
        if vencidas:
            db.session.commit()
            logger.info('%d assinatura(s) movida(s) para blocked por carência vencida', len(vencidas))
        return len(vencidas)
