"""Serviço de cobrança/assinaturas (Asaas).

Cada usuário (aluno ou professor) tem NO MÁXIMO uma linha em
`assinaturas` -- nunca duas. O mesmo registro que hoje representa "sem
plano pago" pode depois passar a representar Plano Fit, Pró ou Premium,
conforme o que o usuário assina; um professor nunca paga duas cobranças
simultâneas.

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

TRIAL_DIAS = 30
CARENCIA_DIAS_PADRAO = 3
CARENCIA_DIAS_PROFESSOR_GESTAO = 15
LIMITE_ALUNOS_GRATIS = 2
REQUEST_TIMEOUT_SECONDS = 10

PLANOS_GESTAO_PROFESSOR = ('professor_pro', 'professor_premium')
ORDEM_PLANOS_GESTAO = {'professor_pro': 1, 'professor_premium': 2}

ASAAS_BASE_URL_SANDBOX = "https://sandbox.asaas.com/api/v3"
ASAAS_BASE_URL_PRODUCAO = "https://api.asaas.com/v3"

# Eventos do Asaas que realmente importam pro nosso ciclo de vida.
# Lista completa de eventos: https://docs.asaas.com/docs/webhook-events
# -- conferir contra a documentação atual antes de ativar em produção,
# pois nomes de evento podem mudar entre versões da API.
EVENTOS_CONFIRMACAO_PAGAMENTO = ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED')
EVENTOS_ATRASO = ('PAYMENT_OVERDUE',)
EVENTOS_CANCELAMENTO = ('PAYMENT_DELETED', 'PAYMENT_REFUNDED', 'SUBSCRIPTION_DELETED')


class CpfCnpjNecessarioError(Exception):
    """Levantada por criar_assinatura_checkout quando o usuário ainda
    não tem cpf_cnpj cadastrado -- o Asaas exige o dado pra gerar
    qualquer cobrança de verdade. A rota que chama deve pedir o CPF/
    CNPJ antes de tentar de novo, em vez de tratar como falha de rede
    genérica."""
    pass


class BillingService:

    # ================================================================
    # Acesso / tier -- só lê o banco local, sem chamar o gateway
    # ================================================================

    @staticmethod
    def iniciar_trial(usuario: User) -> Assinatura:
        """Cria a Assinatura em estado 'trialing' -- vale pra aluno E
        professor (ambos podem treinar por conta própria e usar
        Estatísticas/FitBot). Chamar uma única vez, no fluxo de
        registro (idealmente na mesma transação que cria o User) --
        idempotente por segurança (se já existir, só retorna a
        existente sem duplicar).

        O trial dá acesso a Estatísticas/FitBot, mas NÃO permite ao
        professor gerenciar mais de 2 alunos -- isso sempre exige
        assinatura ATIVA e paga do Pró/Premium (ver pode_cadastrar_aluno)."""
        if usuario.assinatura is not None:
            return usuario.assinatura

        assinatura = Assinatura(
            usuario_id=usuario.id,
            status='trialing',
            trial_termina_em=datetime.now(timezone.utc) + timedelta(days=TRIAL_DIAS),
        )
        db.session.add(assinatura)
        db.session.commit()
        logger.info('Trial de %s dias iniciado para usuário %s', TRIAL_DIAS, usuario.id)
        return assinatura

    @staticmethod
    def usuario_tem_acesso_premium(usuario: User) -> bool:
        """Único ponto de verdade para gatear Estatísticas/FitBot --
        vale pra aluno e professor por igual, e não importa qual plano
        está associado (Fit, Pró ou Premium todos liberam essas telas
        enquanto a assinatura estiver com status válido). A exceção de
        admin fica a cargo de quem chama, não daqui."""
        assinatura = usuario.assinatura
        if assinatura is None:
            return False
        return assinatura.acesso_premium_ativo()

    @staticmethod
    def contar_alunos_ativos(professor: User) -> int:
        """Quantidade de alunos ativos vinculados ao professor."""
        return AlunoProfessor.query.filter_by(
            professor_id=professor.id, ativo=True
        ).count()

    @staticmethod
    def _plano_gestao_para_total(total_alunos: int) -> Plano | None:
        """Qual Plano de gestão (Pró/Premium) é exigido pra um professor
        com essa quantidade de alunos ativos. None quando a faixa
        gratuita (até 2 alunos) já cobre."""
        if total_alunos <= LIMITE_ALUNOS_GRATIS:
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
    def plano_gestao_necessario(professor: User) -> Plano | None:
        """Plano de gestão (Pró/Premium) exigido pela quantidade ATUAL
        de alunos ativos do professor. None = ainda na faixa gratuita
        (até 2 alunos), sem exigência de plano pago pra continuar
        gerenciando os alunos que já tem."""
        return BillingService._plano_gestao_para_total(BillingService.contar_alunos_ativos(professor))

    @staticmethod
    def plano_recomendado_professor(professor: User) -> Plano | None:
        """O plano que o botão "Assinar" do professor deve oferecer:
        Pró/Premium se a quantidade de alunos já exigir, senão o Plano
        Fit (mesma cobrança do aluno -- só destrava Estatísticas/
        FitBot, não muda nada sobre gestão de alunos)."""
        necessario = BillingService.plano_gestao_necessario(professor)
        if necessario is not None:
            return necessario
        return Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()

    @staticmethod
    def pode_cadastrar_aluno(professor: User) -> tuple[bool, str | None]:
        """Confere ANTES de vincular um novo aluno se o professor pode
        fazer isso agora. Até 2 alunos é sempre livre; passar disso
        exige assinatura ATIVA (paga) do Plano Pró/Premium que já cubra
        o novo total -- trial e Plano Fit NÃO contam pra isso (eles só
        liberam Estatísticas/FitBot, não gestão de mais alunos).

        Retorna (True, None) se pode, ou (False, mensagem) explicando
        pra qual plano o professor precisa fazer upgrade."""
        novo_total = BillingService.contar_alunos_ativos(professor) + 1
        if novo_total <= LIMITE_ALUNOS_GRATIS:
            return True, None

        plano_necessario = BillingService._plano_gestao_para_total(novo_total)
        assinatura = professor.assinatura
        plano_atual_codigo = None
        if assinatura is not None and assinatura.status == 'active' and assinatura.plano is not None:
            plano_atual_codigo = assinatura.plano.codigo

        if plano_atual_codigo and ORDEM_PLANOS_GESTAO.get(plano_atual_codigo, 0) >= ORDEM_PLANOS_GESTAO.get(plano_necessario.codigo, 0):
            return True, None

        return False, f'Para cadastrar mais alunos, faça upgrade para o {plano_necessario.nome}.'

    @staticmethod
    def professor_acesso_alunos_liberado(professor: User) -> bool:
        """True se o professor pode acessar as telas de gerenciamento/
        visualização dos alunos já vinculados. Só fica bloqueado quando
        ele já ultrapassou a faixa gratuita (mais de 2 alunos, exigindo
        Pró/Premium) e a assinatura está com status 'blocked' --
        carência de 15 dias de atraso esgotada (ver
        CARENCIA_DIAS_PROFESSOR_GESTAO e expirar_carencias_vencidas).
        O vínculo com os alunos nunca é apagado por isso, só o acesso
        às telas. Até 2 alunos, nunca é bloqueado por cobrança."""
        if BillingService.contar_alunos_ativos(professor) <= LIMITE_ALUNOS_GRATIS:
            return True
        assinatura = professor.assinatura
        if assinatura is None:
            # Não deveria acontecer (pode_cadastrar_aluno já teria
            # barrado chegar a mais de 2 alunos sem assinatura), mas
            # não é uma checagem de autorização/IDOR -- é só uma regra
            # de cobrança, então falha aberta aqui não é um risco de
            # segurança, só uma inconsistência de dados a investigar.
            return True
        return assinatura.status != 'blocked'

    @staticmethod
    def verificar_mudancas_tier_professores() -> list[dict]:
        """Varre todos os professores e retorna os que estão com um
        plano de gestão diferente do exigido agora pela contagem de
        alunos -- SEM aplicar nada. Pensado para rodar como job
        periódico (ex: diário) cujo resultado alimenta um e-mail de
        aviso ("seu plano vai mudar de X para Y") -- a troca de valor
        cobrado só deve ser aplicada depois dessa notificação e nunca
        no mesmo ciclo em que o professor passou a faixa, para não
        surpreendê-lo com uma cobrança diferente sem aviso prévio (CDC,
        art. 6º -- direito à informação clara sobre o serviço).

        A aplicação em si (trocar assinatura.plano_id e sincronizar o
        valor no Asaas) é um passo separado, deliberadamente não
        automático aqui."""
        mudancas = []
        professores = User.query.filter_by(tipo_usuario='professor', ativo=True).all()
        for professor in professores:
            plano_necessario = BillingService.plano_gestao_necessario(professor)
            if plano_necessario is None:
                continue  # faixa gratuita, sem exigência de plano de gestão

            assinatura = professor.assinatura
            plano_atual = assinatura.plano if assinatura else None
            if plano_atual is not None and plano_atual.id == plano_necessario.id:
                continue

            mudancas.append({
                'professor': professor,
                'tier_atual': plano_atual,
                'tier_novo': plano_necessario,
            })
        return mudancas

    # ================================================================
    # Painel do admin
    # ================================================================

    @staticmethod
    def situacao_conta(usuario: User) -> dict:
        """Resume a situação de cobrança de um usuário pro painel do
        admin: um código estável pra filtrar, um rótulo pra exibir, se
        está inadimplente, qual plano ocupa hoje e (só relevante pra
        professor) se o acesso aos alunos está bloqueado agora."""
        rotulos = {
            'trialing': 'Em teste',
            'active': 'Ativo',
            'past_due': 'Pagamento atrasado',
            'blocked': 'Bloqueado',
            'canceled': 'Cancelado',
        }
        assinatura = usuario.assinatura

        if usuario.is_professor():
            plano_necessario = BillingService.plano_gestao_necessario(usuario)
            acesso_alunos_bloqueado = not BillingService.professor_acesso_alunos_liberado(usuario)

            if plano_necessario is None:
                # Faixa gratuita de gestão -- a situação relevante aqui
                # é só sobre o Plano Fit pessoal (se aderiu) ou trial.
                if assinatura is None:
                    return {'codigo': 'sem_registro', 'rotulo': 'Sem registro', 'inadimplente': False, 'plano_codigo': None, 'acesso_alunos_bloqueado': False}
                return {
                    'codigo': assinatura.status,
                    'rotulo': rotulos.get(assinatura.status, assinatura.status),
                    'inadimplente': assinatura.status in ('past_due', 'blocked'),
                    'plano_codigo': assinatura.plano.codigo if assinatura.plano else None,
                    'acesso_alunos_bloqueado': False,
                }

            plano_codigo = plano_necessario.codigo
            if assinatura is None or assinatura.status == 'canceled':
                return {'codigo': 'pendente', 'rotulo': 'Pendente de pagamento', 'inadimplente': True, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': acesso_alunos_bloqueado}
            if assinatura.status == 'blocked':
                return {'codigo': 'blocked', 'rotulo': 'Bloqueado (alunos)', 'inadimplente': True, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': True}
            if assinatura.status == 'past_due':
                return {'codigo': 'past_due', 'rotulo': 'Pagamento atrasado', 'inadimplente': True, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': False}
            if assinatura.status == 'active' and assinatura.plano_id != plano_necessario.id:
                return {'codigo': 'desatualizado', 'rotulo': 'Tier desatualizado', 'inadimplente': False, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': False}
            if assinatura.status == 'active':
                return {'codigo': 'active', 'rotulo': 'Ativo', 'inadimplente': False, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': False}
            return {'codigo': assinatura.status, 'rotulo': assinatura.status, 'inadimplente': False, 'plano_codigo': plano_codigo, 'acesso_alunos_bloqueado': False}

        # aluno
        if assinatura is None:
            return {'codigo': 'sem_registro', 'rotulo': 'Sem registro', 'inadimplente': False, 'plano_codigo': None, 'acesso_alunos_bloqueado': False}
        return {
            'codigo': assinatura.status,
            'rotulo': rotulos.get(assinatura.status, assinatura.status),
            'inadimplente': assinatura.status in ('past_due', 'blocked'),
            'plano_codigo': 'aluno_fit' if assinatura.status in ('active', 'past_due', 'blocked') else None,
            'acesso_alunos_bloqueado': False,
        }

    @staticmethod
    def listar_contas(tipo_usuario=None, busca=None, situacao_codigo=None, plano_codigo=None):
        """Lista alunos e professores com a situação de cobrança
        calculada, pro painel /admin/contas. Filtros de tipo/busca vão
        pro SQL; situação/plano são calculados (dependem do tier
        dinâmico do professor) e por isso filtrados em Python -- ok
        pro volume de usuários de um app desse porte."""
        query = User.query.filter(User.tipo_usuario.in_(['aluno', 'professor']))
        if tipo_usuario in ('aluno', 'professor'):
            query = query.filter(User.tipo_usuario == tipo_usuario)
        if busca:
            termo = f'%{busca}%'
            query = query.filter(db.or_(
                User.username.ilike(termo),
                User.email.ilike(termo),
                User.nome_completo.ilike(termo),
            ))

        contas = []
        for usuario in query.order_by(User.tipo_usuario, User.username).all():
            situacao = BillingService.situacao_conta(usuario)
            contas.append({'usuario': usuario, **situacao})

        if situacao_codigo == 'inadimplente':
            contas = [c for c in contas if c['inadimplente']]
        elif situacao_codigo:
            contas = [c for c in contas if c['codigo'] == situacao_codigo]
        if plano_codigo:
            contas = [c for c in contas if c['plano_codigo'] == plano_codigo]

        return contas

    # ================================================================
    # Integração com o gateway (Asaas)
    # ================================================================

    @staticmethod
    def garantir_registro_assinatura(usuario: User) -> Assinatura:
        """Garante que o usuário tenha uma linha em `assinaturas` pra
        anexar IDs do gateway. Idempotente: se já existir, só retorna a
        existente. Normalmente desnecessário chamar diretamente -- todo
        aluno/professor já ganha uma via iniciar_trial no cadastro;
        existe pra cobrir o caso raro de checkout sem trial prévio."""
        if usuario.assinatura is not None:
            return usuario.assinatura
        assinatura = Assinatura(usuario_id=usuario.id, status='canceled')
        db.session.add(assinatura)
        db.session.commit()
        return assinatura

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
        """Cria (ou reaproveita/atualiza) o cliente no Asaas e um
        Checkout de assinatura recorrente, retornando o link da página
        de pagamento hospedada pelo Asaas -- o navegador do usuário é
        redirecionado para lá, e o dado de cartão nunca passa pelo
        nosso servidor (mantém o fitlog em PCI SAQ A, o nível mais
        simples de conformidade).

        Usa POST /checkouts (não /subscriptions diretamente) porque é
        o endpoint que devolve uma página hospedada deixando o pagador
        escolher Pix/cartão/boleto -- /subscriptions cria a cobrança
        direto com uma forma de pagamento já definida, sem página de
        escolha. Documentação: https://docs.asaas.com/reference/create-new-checkout

        A assinatura real só é criada pelo Asaas DEPOIS que o pagador
        escolhe a forma de pagamento e confirma -- por isso ainda não
        temos gateway_subscription_id aqui. Mandamos o id da nossa
        própria Assinatura em externalReference pra conseguir casar o
        primeiro webhook que chegar com este registro (ver
        processar_webhook), e só a partir daí gravamos o
        gateway_subscription_id de verdade.

        Levanta CpfCnpjNecessarioError se o usuário ainda não tem
        cpf_cnpj cadastrado -- é campo obrigatório pro Asaas gerar
        qualquer cobrança de verdade (exigência da Receita Federal, não
        só do gateway). Quem chama deve pedir o dado antes de tentar
        de novo (ver routes/billing_routes.py:assinar).
        """
        if not usuario.cpf_cnpj:
            raise CpfCnpjNecessarioError()

        assinatura = BillingService.garantir_registro_assinatura(usuario)

        dados_cliente = {
            'name': usuario.nome_completo or usuario.username,
            'email': usuario.email,
            'cpfCnpj': usuario.cpf_cnpj,
        }
        customer_id = assinatura.gateway_customer_id
        if not customer_id:
            resp = requests.post(
                f'{BillingService._base_url()}/customers',
                json=dados_cliente,
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            BillingService._checar_resposta(resp, 'criar cliente')
            customer_id = resp.json()['id']
            assinatura.gateway_customer_id = customer_id
            db.session.commit()
        else:
            # Atualiza o cadastro existente com o cpfCnpj mais recente
            # -- cobre o caso de um cliente já ter sido criado ANTES do
            # usuário preencher o CPF/CNPJ (ex: tentativas de checkout
            # de antes desta correção), que ficariam pra sempre sem o
            # dado e nunca conseguiriam gerar cobrança nenhuma.
            resp = requests.put(
                f'{BillingService._base_url()}/customers/{customer_id}',
                json=dados_cliente,
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            BillingService._checar_resposta(resp, 'atualizar cliente')

        callback_url = BillingService._url_minha_assinatura()
        resp = requests.post(
            f'{BillingService._base_url()}/checkouts',
            json={
                # Só CREDIT_CARD é aceito quando chargeTypes inclui
                # RECURRENT -- confirmado pela própria API do Asaas:
                # "O método de pagamento CREDIT_CARD é o único método
                # de pagamento permitido para operações RECURRENT".
                # Pix/boleto não têm suporte a cobrança recorrente
                # automática nesse fluxo de Checkout.
                'billingTypes': ['CREDIT_CARD'],
                'chargeTypes': ['RECURRENT'],
                'minutesToExpire': 60,
                'callback': {
                    'successUrl': callback_url,
                    'cancelUrl': callback_url,
                    'expiredUrl': callback_url,
                },
                'customer': customer_id,
                'externalReference': str(assinatura.id),
                'items': [{
                    'name': plano.nome,
                    'description': f'Assinatura mensal -- {plano.nome}',
                    'quantity': 1,
                    'value': plano.preco_centavos / 100,
                }],
                'subscription': {
                    'cycle': 'MONTHLY',
                    'nextDueDate': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'value': plano.preco_centavos / 100,
                    'description': plano.nome,
                },
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        BillingService._checar_resposta(resp, 'criar checkout')
        dados = resp.json()

        assinatura.plano_id = plano.id
        db.session.commit()

        return dados.get('link')

    @staticmethod
    def _checar_resposta(resp: requests.Response, contexto: str):
        """Substitui resp.raise_for_status() puro -- loga o corpo da
        resposta de erro ANTES de levantar a exceção. O
        requests.HTTPError padrão não inclui o corpo, e o corpo é
        exatamente onde o Asaas explica qual campo está inválido/
        faltando (ex: {"errors":[{"description":"..."}]}) -- sem isso
        só sabíamos "400 Client Error", sem motivo nenhum, toda vez que
        algo dava errado."""
        if resp.status_code >= 400:
            logger.error('Asaas respondeu %s ao %s: %s', resp.status_code, contexto, resp.text[:2000])
        resp.raise_for_status()

    @staticmethod
    def _url_minha_assinatura() -> str:
        """Monta a URL absoluta de /billing/minha-assinatura pra usar
        nos callbacks do checkout (successUrl/cancelUrl/expiredUrl).
        Quando APP_BASE_URL está configurada, concatena direto (nem
        chama url_for -- fora de uma requisição real, url_for exige
        SERVER_NAME configurado, o que não é o caso em todo ambiente).
        Sem APP_BASE_URL, cai no url_for padrão (funciona normalmente
        dentro do request real que chama esta função, mas depende do
        Host recebido -- mesmo trade-off de
        routes/auth_routes.py:_build_trusted_url)."""
        base_url = current_app.config.get('APP_BASE_URL')
        if base_url:
            return base_url.rstrip('/') + '/billing/minha-assinatura'
        from flask import url_for
        return url_for('billing.minha_assinatura', _external=True)

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
        external_reference = payment.get('externalReference')

        # Primeira cobrança de uma assinatura criada via /checkouts
        # ainda não tem gateway_subscription_id gravado no nosso banco
        # (só sabemos o ID da nossa própria Assinatura, mandado como
        # externalReference na criação do checkout -- ver
        # criar_assinatura_checkout). Tenta achar por subscription_id
        # primeiro; se não achar, cai pro externalReference e já
        # aproveita pra gravar o subscription_id que faltava.
        assinatura = None
        if subscription_id:
            assinatura = Assinatura.query.filter_by(gateway_subscription_id=subscription_id).first()
        if assinatura is None and external_reference and external_reference.isdigit():
            assinatura = Assinatura.query.get(int(external_reference))
            if assinatura and subscription_id and not assinatura.gateway_subscription_id:
                assinatura.gateway_subscription_id = subscription_id

        if assinatura:
            BillingService._aplicar_evento(assinatura, tipo_evento)
        elif subscription_id or external_reference:
            logger.warning(
                'Webhook Asaas (subscription=%s, externalReference=%s) sem Assinatura correspondente no banco',
                subscription_id, external_reference,
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
            # Professor pagando Pró/Premium tem carência maior (15 dias)
            # antes de perder acesso aos alunos -- o restante (aluno, ou
            # professor no Plano Fit) usa a carência padrão de 3 dias.
            plano_codigo = assinatura.plano.codigo if assinatura.plano else None
            dias_carencia = (
                CARENCIA_DIAS_PROFESSOR_GESTAO if plano_codigo in PLANOS_GESTAO_PROFESSOR
                else CARENCIA_DIAS_PADRAO
            )
            assinatura.carencia_termina_em = agora + timedelta(days=dias_carencia)
        elif tipo_evento in EVENTOS_CANCELAMENTO:
            assinatura.status = 'canceled'
            assinatura.cancelado_em = agora
        else:
            logger.debug('Evento Asaas %s sem tratamento específico, ignorado', tipo_evento)

    @staticmethod
    def expirar_carencias_vencidas():
        """Job periódico (ex: a cada hora): move para 'blocked' quem
        esgotou a carência de pagamento atrasado sem regularizar (3 dias
        pro Plano Fit, 15 dias pro Pró/Premium -- o prazo já foi
        calculado em carencia_termina_em quando o atraso foi registrado,
        então este job só compara contra a data, sem recalcular nada).
        Não é feito dentro de acesso_premium_ativo() -- esse método só
        LÊ o status; quem escreve é sempre um processo explícito
        (webhook ou este job), nunca uma leitura incidental."""
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