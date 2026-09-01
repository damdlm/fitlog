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

import calendar
import hmac
import logging
import re
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

# Pix não gera cobrança recorrente automática (ver
# criar_pagamento_pix_ativacao) -- cada pagamento confirmado ativa o
# plano por ~1 mês. DIAS_ATIVACAO_PIX existe só como valor de
# fallback; o padrão é usar _proximo_vencimento_mensal (mesmo dia do
# mês seguinte, com fallback pro último dia quando o mês seguinte for
# mais curto), não um número fixo de dias -- ver essa função.
DIAS_ATIVACAO_PIX_FALLBACK = 30

ASAAS_BASE_URL_SANDBOX = "https://sandbox.asaas.com/api/v3"
ASAAS_BASE_URL_PRODUCAO = "https://api.asaas.com/v3"


def _proximo_vencimento_mensal(referencia: datetime) -> datetime:
    """"Mesmo dia do mês seguinte" -- usado pra calcular até quando um
    pagamento Pix confirmado mantém o plano ativo (ver
    criar_pagamento_pix_ativacao e _aplicar_evento). Quando o mês
    seguinte é mais curto e não tem esse dia (ex: dia 31 -> não existe
    31 de fevereiro), cai pro último dia daquele mês -- nunca estoura
    pro mês depois disso."""
    ano = referencia.year + (referencia.month // 12)
    mes = referencia.month % 12 + 1
    ultimo_dia_mes_seguinte = calendar.monthrange(ano, mes)[1]
    dia = min(referencia.day, ultimo_dia_mes_seguinte)
    return referencia.replace(year=ano, month=mes, day=dia)


# Eventos do Asaas que realmente importam pro nosso ciclo de vida.
# Lista completa de eventos: https://docs.asaas.com/docs/webhook-events
# -- conferir contra a documentação atual antes de ativar em produção,
# pois nomes de evento podem mudar entre versões da API.
EVENTOS_CONFIRMACAO_PAGAMENTO = ('PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED')
EVENTOS_ATRASO = ('PAYMENT_OVERDUE',)
EVENTOS_CANCELAMENTO = ('PAYMENT_DELETED', 'PAYMENT_REFUNDED', 'SUBSCRIPTION_DELETED')


class DadosCobrancaIncompletosError(Exception):
    """Levantada por criar_assinatura_checkout quando falta algum dado
    obrigatório pro Asaas gerar a cobrança -- CPF/CNPJ, telefone, CEP
    ou número do endereço. `campos` traz os nomes que faltam (mesmos
    nomes dos campos do User: cpf_cnpj, telefone, endereco_cep,
    endereco_numero), pra rota que chama pedir só o que falta em vez
    de tratar como falha de rede genérica."""
    def __init__(self, campos):
        self.campos = campos
        super().__init__(f'Dados de cobrança incompletos: {", ".join(campos)}')


# Nome antigo mantido como alias -- CpfCnpjNecessarioError virou um
# caso específico de DadosCobrancaIncompletosError quando descobrimos
# que CPF/CNPJ sozinho não bastava (telefone/CEP/número também são
# exigidos pelo Asaas pra checkout de cartão recorrente).
CpfCnpjNecessarioError = DadosCobrancaIncompletosError


class AssinaturaJaAtivaError(Exception):
    """Levantada por criar_assinatura_checkout quando o usuário já tem
    uma assinatura ATIVA para o mesmo plano que está tentando assinar
    de novo -- evita criar uma segunda cobrança recorrente pro mesmo
    cliente por duplo clique, aba duplicada, ou clicar em "Assinar"
    sem perceber que já está em dia."""
    def __init__(self, plano):
        self.plano = plano
        super().__init__(f'Já existe assinatura ativa do plano {plano.codigo}')


class NadaParaCancelarError(Exception):
    """Levantada por cancelar_assinatura quando o usuário não tem
    nenhuma assinatura com gateway_subscription_id pra cancelar (nunca
    assinou, ou já está cancelada)."""
    pass


class AssinaturaAtualizadaError(Exception):
    """Não é um erro de verdade -- sinaliza que criar_assinatura_checkout
    atualizou o VALOR de uma assinatura já ativa em vez de criar um
    checkout novo (usuário mudou de plano, ex: professor que cresceu de
    Pró pra Premium). Quem chama deve tratar como sucesso e mostrar uma
    mensagem de confirmação, não redirecionar pra um link de checkout."""
    def __init__(self, plano):
        self.plano = plano
        super().__init__(f'Assinatura atualizada para o plano {plano.codigo}, sem checkout novo')


class BillingService:

    @staticmethod
    def campos_cobranca_faltando(usuario: User) -> list[str]:
        """Lista os campos ainda não preenchidos que o Asaas exige pra
        gerar uma cobrança de cartão recorrente: cpf_cnpj, telefone,
        endereco_cep, endereco_numero. Lista vazia = pode prosseguir
        pro checkout."""
        campos = []
        if not usuario.cpf_cnpj:
            campos.append('cpf_cnpj')
        if not usuario.telefone:
            campos.append('telefone')
        if not usuario.endereco_cep:
            campos.append('endereco_cep')
        if not usuario.endereco_numero:
            campos.append('endereco_numero')
        return campos

    # ================================================================
    # Acesso / tier -- só lê o banco local, sem chamar o gateway
    # ================================================================

    @staticmethod
    def iniciar_trial(usuario: User, commit: bool = True) -> Assinatura:
        """Cria a Assinatura em estado 'trialing' -- vale pra aluno E
        professor (ambos podem treinar por conta própria e usar
        Estatísticas/FitBot). Chamar uma única vez, no fluxo de
        registro (idealmente na mesma transação que cria o User) --
        idempotente por segurança (se já existir, só retorna a
        existente sem duplicar).

        O trial dá acesso a Estatísticas/FitBot, mas NÃO permite ao
        professor gerenciar mais de 2 alunos -- isso sempre exige
        assinatura ATIVA e paga do Pró/Premium (ver pode_cadastrar_aluno).

        commit=False apenas adiciona a Assinatura à sessão sem
        confirmar a transação -- usado pelo cadastro (routes/
        auth_routes.py:register), que precisa que User + Assinatura +
        aceite LGPD sejam confirmados juntos, num commit único."""
        if usuario.assinatura is not None:
            return usuario.assinatura

        assinatura = Assinatura(
            usuario_id=usuario.id,
            status='trialing',
            trial_termina_em=datetime.now(timezone.utc) + timedelta(days=TRIAL_DIAS),
        )
        db.session.add(assinatura)
        if commit:
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
    def planos_disponiveis_professor(professor: User) -> list[Plano]:
        """Planos que o professor pode ESCOLHER assinar (upgrade
        voluntário incluído, não só o mínimo automático). O piso é
        sempre plano_gestao_necessario -- nunca oferece um plano
        abaixo do que a quantidade atual de alunos já exige, pra não
        deixar o professor se auto-rebaixar pra um plano que não cobre
        os alunos que já tem. Acima do piso, todas as faixas de
        professor (Pró/Premium) entram, na ordem Fit -> Pró -> Premium
        -- ex: um professor com 1 aluno (piso = nenhum) pode escolher
        adiantar pro Pró ou Premium se quiser margem de crescimento;
        um professor com 5 alunos (piso = Pró) só pode escolher entre
        Pró e Premium, nunca Fit."""
        necessario = BillingService.plano_gestao_necessario(professor)
        piso = ORDEM_PLANOS_GESTAO.get(necessario.codigo, 0) if necessario else 0

        planos = []
        if piso == 0:
            fit = Plano.query.filter_by(codigo='aluno_fit', ativo=True).first()
            if fit is not None:
                planos.append(fit)
        for codigo in PLANOS_GESTAO_PROFESSOR:
            if ORDEM_PLANOS_GESTAO.get(codigo, 0) >= piso:
                plano = Plano.query.filter_by(codigo=codigo, ativo=True).first()
                if plano is not None:
                    planos.append(plano)
        return planos

    @staticmethod
    def proxima_faixa_professor(professor: User) -> tuple[Plano | None, int]:
        """Pra alimentar o indicador "faltam N alunos pra próxima
        faixa" na tela de assinatura. Retorna (None, 0) quando o
        professor já está na faixa mais alta (Premium) -- não há
        próxima faixa a mostrar. Baseado na faixa ATUAL pela contagem
        de alunos (não pelo plano contratado), então funciona mesmo
        pra quem ainda não assinou nada."""
        total = BillingService.contar_alunos_ativos(professor)
        atual = BillingService._plano_gestao_para_total(total)
        ordem_atual = ORDEM_PLANOS_GESTAO.get(atual.codigo, 0) if atual else 0

        proximo = (
            Plano.query
            .filter(
                Plano.tipo_usuario == 'professor',
                Plano.ativo.is_(True),
                Plano.codigo.in_(PLANOS_GESTAO_PROFESSOR),
                Plano.min_alunos > total,
            )
            .order_by(Plano.min_alunos.asc())
            .first()
        )
        if proximo is None or ORDEM_PLANOS_GESTAO.get(proximo.codigo, 0) <= ordem_atual:
            # Não deveria filtrar nada aqui de fato (min_alunos > total
            # já garante que é uma faixa acima), a checagem de ordem é
            # só uma trava extra contra inconsistência de dados na
            # tabela planos (ex: min_alunos cadastrado fora de ordem).
            if proximo is None:
                return None, 0
        faltam = proximo.min_alunos - total
        return proximo, max(faltam, 0)

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
    def _obter_ou_criar_cliente_asaas(usuario: User, assinatura: Assinatura) -> str:
        """Garante o cliente correspondente no Asaas e devolve seu id,
        criando ou atualizando o cadastro conforme necessário. Extraído
        de criar_assinatura_checkout pra ser reaproveitado também pelo
        fluxo de ativação via Pix (criar_pagamento_pix_ativacao), que
        precisa do mesmo cliente mas não passa pelo /checkouts
        hospedado."""
        dados_cliente = {
            'name': usuario.nome_completo or usuario.username,
            'email': usuario.email,
            'cpfCnpj': usuario.cpf_cnpj,
            'phone': re.sub(r'\D', '', usuario.telefone),
            'postalCode': usuario.endereco_cep,
            'addressNumber': usuario.endereco_numero,
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
            resp = requests.put(
                f'{BillingService._base_url()}/customers/{customer_id}',
                json=dados_cliente,
                headers=BillingService._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            BillingService._checar_resposta(resp, 'atualizar cliente')
        return customer_id

    @staticmethod
    def criar_pagamento_pix_ativacao(usuario: User, plano: Plano) -> str:
        """Alternativa ao cartão: gera uma cobrança Pix AVULSA (POST
        /payments -- não é uma assinatura recorrente no Asaas, ao
        contrário do fluxo de cartão em criar_assinatura_checkout) que,
        quando confirmada, ativa o plano por ~1 mês (até o mesmo dia do
        mês seguinte -- ver _proximo_vencimento_mensal e o tratamento
        em _aplicar_evento). Não existe débito automático via Pix:
        passado esse período, o acesso cai pra 'past_due' (mesma
        carência de sempre) e a pessoa precisa gerar e pagar um novo
        Pix aqui de novo pra renovar -- ver expirar_pix_vencidos.

        Diferente do cartão, aqui não existe "assinatura ativa no
        gateway" pra atualizar de valor quando o professor troca de
        plano no meio do período -- o plano só muda de fato no próximo
        Pix pago. Por isso: se já tem um período Pix vigente pro MESMO
        plano, recusa com AssinaturaJaAtivaError; se é plano diferente
        (upgrade/downgrade) ou o período já venceu, gera uma cobrança
        nova normalmente -- ao confirmar, ela substitui o plano atual.

        IMPORTANTE -- não testado contra o Asaas (sandbox nem
        produção): implementado seguindo https://docs.asaas.com/reference/criar-nova-cobranca,
        mas o próprio código deste arquivo registra que já foram
        necessárias 3 rodadas de erro 400 pra acertar o fluxo de
        cartão. Testar no sandbox antes de liberar, conferindo
        principalmente o nome do campo com o link/QR Code do Pix na
        resposta (usei 'invoiceUrl', mesmo campo já usado no restante
        do código pro link de checkout de cartão)."""
        faltando = BillingService.campos_cobranca_faltando(usuario)
        if faltando:
            raise DadosCobrancaIncompletosError(faltando)

        assinatura = (
            Assinatura.query
            .filter_by(usuario_id=usuario.id)
            .with_for_update()
            .first()
        )
        if assinatura is None:
            assinatura = BillingService.garantir_registro_assinatura(usuario)

        agora = datetime.now(timezone.utc)
        periodo_vigente = assinatura.periodo_atual_fim and assinatura.periodo_atual_fim > agora
        if (assinatura.status == 'active' and assinatura.forma_pagamento == 'pix'
                and assinatura.plano_id == plano.id and periodo_vigente):
            raise AssinaturaJaAtivaError(plano)

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)
        valor = plano.preco_centavos / 100

        resp = requests.post(
            f'{BillingService._base_url()}/payments',
            json={
                'customer': customer_id,
                'billingType': 'PIX',
                'value': valor,
                'dueDate': agora.strftime('%Y-%m-%d'),
                'description': f'{plano.nome} -- ativação de ~1 mês',
                'externalReference': str(assinatura.id),
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        BillingService._checar_resposta(resp, 'criar cobrança pix avulsa')
        dados = resp.json()

        # Otimista, igual ao fluxo de cartão em criar_assinatura_checkout:
        # o plano só passa a valer de verdade (status='active' +
        # periodo_atual_fim) quando o webhook confirmar o pagamento --
        # ver _aplicar_evento. Isso aqui só marca a INTENÇÃO.
        assinatura.plano_id = plano.id
        assinatura.forma_pagamento = 'pix'
        assinatura.cartao_ultimos_digitos = None
        assinatura.cartao_bandeira = None
        db.session.commit()

        return dados.get('invoiceUrl')

    @staticmethod
    def listar_faturas(usuario: User, limite: int = 24) -> list[dict]:
        """Histórico de cobranças (pagas, pendentes ou vencidas) do
        usuário, mais recentes primeiro -- pra tela de "Minhas
        Faturas". GET /payments?customer={id} é o endpoint documentado
        em https://docs.asaas.com/reference/listar-cobrancas ; conferir
        contra o sandbox antes de subir (nomes de campo podem variar
        por versão da API). Devolve lista vazia se o usuário nunca
        chegou a ter cliente criado no Asaas (nunca tentou assinar)."""
        assinatura = usuario.assinatura
        if assinatura is None or not assinatura.gateway_customer_id:
            return []
        resp = requests.get(
            f'{BillingService._base_url()}/payments',
            params={
                'customer': assinatura.gateway_customer_id,
                'limit': limite,
                'order': 'desc',
                'sort': 'dueDate',
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        BillingService._checar_resposta(resp, 'listar faturas')
        faturas = []
        for item in resp.json().get('data', []):
            faturas.append({
                'id': item.get('id'),
                'valor_centavos': round(item.get('value', 0) * 100),
                'status': item.get('status'),
                'vencimento': item.get('dueDate'),
                'pago_em': item.get('paymentDate') or item.get('clientPaymentDate'),
                'forma_pagamento': item.get('billingType'),
                'link': item.get('invoiceUrl'),
            })
        return faturas

    @staticmethod
    def criar_assinatura_checkout(usuario: User, plano: Plano) -> str:
        """Cria (ou reaproveita/atualiza) o cliente no Asaas e um
        Checkout de assinatura recorrente por cartão de crédito,
        retornando o link da página de pagamento hospedada pelo Asaas
        -- o navegador do usuário é redirecionado para lá, e o dado de
        cartão nunca passa pelo nosso servidor (mantém o fitlog em PCI
        SAQ A, o nível mais simples de conformidade).

        Usa POST /checkouts (não /subscriptions diretamente) porque é
        o endpoint que devolve uma página hospedada de pagamento --
        /subscriptions cria a cobrança direto, sem página. Documentação
        de referência (lida por completo antes desta versão, depois de
        3 rodadas de erro 400 corrigindo campo por campo -- não repetir
        esse padrão): https://docs.asaas.com/reference/create-new-checkout
        e https://docs.asaas.com/reference/criar-novo-cliente

        billingTypes é só ['CREDIT_CARD']: a própria API confirmou que
        é o único método aceito quando chargeTypes inclui RECURRENT --
        Pix/boleto não têm suporte a cobrança recorrente automática
        nesse fluxo.

        Exige cpf_cnpj, telefone, endereco_cep e endereco_numero
        preenchidos no usuário -- a API também confirmou (erro
        explícito) que phone/address/addressNumber/postalCode/
        province/city precisam existir no cliente pra criar um
        checkout RECURRENT+CREDIT_CARD. Mandando só o CEP, o próprio
        Asaas preenche address/province/city automaticamente; só
        addressNumber e phone precisam ser enviados à parte. Levanta
        DadosCobrancaIncompletosError se faltar algum -- quem chama
        deve pedir os dados antes de tentar de novo (ver
        routes/billing_routes.py:assinar).

        A assinatura real só é criada pelo Asaas DEPOIS que o pagador
        confirma o pagamento -- por isso ainda não temos
        gateway_subscription_id aqui. Mandamos externalReference, mas
        na prática o Asaas NÃO o propaga pro payment/subscription
        gerados a partir do checkout (confirmado com pagamento real) --
        quem realmente casa o primeiro webhook com este registro é o
        gateway_customer_id (ver processar_webhook), que já sabemos
        certo desde a criação do cliente aqui embaixo.

        Nunca cria um checkout novo pra quem já tem assinatura ATIVA:
        se o plano pedido é o mesmo que já está ativo, levanta
        AssinaturaJaAtivaError (nada a fazer). Se é diferente (ex:
        professor que cresceu de Pró pra Premium), chama
        atualizar_valor_assinatura() -- PUT na assinatura já existente
        no Asaas, nunca cria uma segunda cobrança recorrente pro mesmo
        cliente. Ver https://docs.asaas.com/reference/atualizar-assinatura-existente
        """
        faltando = BillingService.campos_cobranca_faltando(usuario)
        if faltando:
            raise DadosCobrancaIncompletosError(faltando)

        # Trava a linha da Assinatura pra essa checagem + eventual
        # criação serem atômicas -- sem isso, duas requisições quase
        # simultâneas (duplo clique, aba duplicada) poderiam passar as
        # duas pela checagem "não está ativa ainda" antes de qualquer
        # uma commitar, e cada uma criar seu próprio checkout/assinatura
        # no Asaas. SQLite (usado nos testes) ignora o FOR UPDATE sem
        # erro; em produção (Postgres) o lock é real.
        assinatura = (
            Assinatura.query
            .filter_by(usuario_id=usuario.id)
            .with_for_update()
            .first()
        )
        if assinatura is None:
            assinatura = BillingService.garantir_registro_assinatura(usuario)

        if assinatura.status == 'active' and assinatura.gateway_subscription_id:
            if assinatura.plano_id == plano.id and assinatura.forma_pagamento == 'cartao':
                raise AssinaturaJaAtivaError(plano)
            BillingService.atualizar_valor_assinatura(assinatura, plano)
            raise AssinaturaAtualizadaError(plano)

        customer_id = BillingService._obter_ou_criar_cliente_asaas(usuario, assinatura)
        valor = plano.preco_centavos / 100

        callback_url = BillingService._url_minha_assinatura()
        resp = requests.post(
            f'{BillingService._base_url()}/checkouts',
            json={
                # Só CREDIT_CARD é aceito quando chargeTypes inclui
                # RECURRENT -- confirmado pela própria API do Asaas:
                # "O método de pagamento CREDIT_CARD é o único método
                # de pagamento permitido para operações RECURRENT".
                # Pix/boleto não têm suporte a cobrança recorrente
                # automática nesse fluxo de Checkout -- ver
                # criar_pagamento_pix_ativacao pra essa alternativa.
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
                    'value': valor,
                }],
                'subscription': {
                    'cycle': 'MONTHLY',
                    'nextDueDate': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'value': valor,
                    'description': plano.nome,
                },
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        BillingService._checar_resposta(resp, 'criar checkout')
        dados = resp.json()

        assinatura.plano_id = plano.id
        assinatura.forma_pagamento = 'cartao'
        db.session.commit()

        return dados.get('link')

    @staticmethod
    def atualizar_valor_assinatura(assinatura: Assinatura, plano: Plano):
        """Atualiza o VALOR (e plano local) de uma assinatura já ativa
        no Asaas -- usado quando o usuário precisa mudar de plano (ex:
        professor que passou a ter mais alunos) enquanto já está em
        dia. Nunca cria uma assinatura nova nesse caso -- é assim que
        se evita cobrar duas vezes o mesmo cliente. Ver
        https://docs.asaas.com/reference/atualizar-assinatura-existente

        updatePendingPayments=False (padrão da API se omitido) -- só
        cobranças futuras usam o valor novo; qualquer cobrança pendente
        já gerada com o valor antigo não é mexida, pra não surpreender
        o pagador com uma cobrança diferente do que ele já esperava.

        Só é chamado no fluxo de cartão -- Pix agora é pagamento
        avulso (sem assinatura recorrente no Asaas, ver
        criar_pagamento_pix_ativacao), então não há "assinatura no
        gateway" pra atualizar de valor nesse caso; a troca de plano
        via Pix só passa a valer no próximo pagamento confirmado."""
        resp = requests.put(
            f'{BillingService._base_url()}/subscriptions/{assinatura.gateway_subscription_id}',
            json={
                'billingType': 'CREDIT_CARD',
                'cycle': 'MONTHLY',
                'value': plano.preco_centavos / 100,
                'description': plano.nome,
            },
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        BillingService._checar_resposta(resp, 'atualizar valor da assinatura')

        assinatura.plano_id = plano.id
        db.session.commit()
        logger.info(
            'Assinatura %s (usuario=%s) atualizada pro plano %s sem criar cobrança nova',
            assinatura.id, assinatura.usuario_id, plano.codigo,
        )

    @staticmethod
    def cancelar_assinatura(usuario: User):
        """Cancela definitivamente a assinatura do usuário no Asaas --
        DELETE /subscriptions/{id}, que encerra a recorrência e remove
        cobranças pendentes/vencidas (as já pagas ficam no histórico,
        sem estorno automático). Ver
        https://docs.asaas.com/reference/remover-assinatura

        Revoga o acesso premium IMEDIATAMENTE (status='canceled' já
        bloqueia Estatísticas/FitBot na próxima checagem) -- não guarda
        acesso até o fim do período já pago. Levanta
        NadaParaCancelarError se não houver nada pra cancelar."""
        assinatura = usuario.assinatura
        if assinatura is None or not assinatura.gateway_subscription_id:
            raise NadaParaCancelarError()

        resp = requests.delete(
            f'{BillingService._base_url()}/subscriptions/{assinatura.gateway_subscription_id}',
            headers=BillingService._headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        # 404 significa que a assinatura já não existe mais no Asaas
        # (ex: já foi removida numa tentativa anterior que falhou antes
        # de atualizarmos o banco local) -- trata como sucesso, já que
        # o resultado desejado (nenhuma cobrança futura) já é realidade.
        if resp.status_code != 404:
            BillingService._checar_resposta(resp, 'cancelar assinatura')

        assinatura.status = 'canceled'
        assinatura.cancelado_em = datetime.now(timezone.utc)
        db.session.commit()
        logger.info('Assinatura %s (usuario=%s) cancelada pelo usuário', assinatura.id, usuario.id)

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
            logger.warning('Webhook Asaas sem id/event no payload, ignorado. Payload: %s', payload)
            return False

        # Eventos PAYMENT_* trazem os dados em payload['payment'].
        # Eventos SUBSCRIPTION_* (ex: SUBSCRIPTION_DELETED, tratado
        # abaixo em EVENTOS_CANCELAMENTO) trazem em payload['subscription']
        # -- é o próprio 'id' do objeto subscription que identifica a
        # assinatura (não existe um campo 'subscription' aninhado nele,
        # diferente do objeto payment). Sem separar os dois, todo evento
        # de assinatura chegava com os três identificadores vazios e
        # nunca casava com nada no banco.
        payment = payload.get('payment') or {}
        subscription_obj = payload.get('subscription') or {}

        subscription_id = payment.get('subscription') or subscription_obj.get('id')
        external_reference = payment.get('externalReference') or subscription_obj.get('externalReference')
        customer_id = payment.get('customer') or subscription_obj.get('customer')

        # Sempre em INFO (não DEBUG) -- app.logger está configurado pra
        # INFO em produção (ver app.py), então isso é o que garante dar
        # pra ver no log do Railway exatamente o que o Asaas mandou,
        # mesmo quando o evento não bate com nada que esperávamos.
        logger.info(
            'Webhook Asaas recebido: event=%s id=%s subscription=%s externalReference=%s customer=%s payment.status=%s subscription.status=%s',
            tipo_evento, event_id, subscription_id, external_reference, customer_id,
            payment.get('status'), subscription_obj.get('status'),
        )

        # Idempotência: Asaas reenvia o mesmo evento se não recebeu 200
        # a tempo da tentativa anterior -- processar duas vezes pode
        # gerar dupla liberação de acesso ou dupla baixa de pagamento.
        if EventoWebhookAsaas.query.filter_by(event_id=event_id).first():
            logger.info('Webhook Asaas %s já processado antes, ignorando', event_id)
            return True

        # Primeira cobrança de uma assinatura criada via /checkouts
        # ainda não tem gateway_subscription_id gravado no nosso banco.
        # Tenta achar por subscription_id primeiro; se não achar, cai
        # pro externalReference -- só que na prática o Asaas NÃO
        # propaga o externalReference mandado na criação do checkout
        # pro payment/subscription gerados a partir dele (confirmado
        # com um pagamento real: chegou com externalReference=None).
        # Por isso o fallback que realmente funciona é achar pelo
        # gateway_customer_id -- esse sim sempre vem preenchido em
        # payment.customer, e nós já sabemos o customer_id certo desde
        # a criação do cliente (ver criar_assinatura_checkout).
        assinatura = None
        if subscription_id:
            assinatura = Assinatura.query.filter_by(gateway_subscription_id=subscription_id).first()
        if assinatura is None and external_reference and external_reference.isdigit():
            assinatura = Assinatura.query.get(int(external_reference))
        if assinatura is None and customer_id:
            assinatura = Assinatura.query.filter_by(gateway_customer_id=customer_id).first()
        if assinatura and subscription_id and not assinatura.gateway_subscription_id:
            assinatura.gateway_subscription_id = subscription_id

        # Quando o payment confirmado veio de cartão, o Asaas costuma
        # incluir um objeto 'creditCard' com os últimos dígitos e a
        # bandeira -- guardamos só isso (nunca o número completo, que
        # nem é enviado) pra poder mostrar "Cartão final 4242" na tela
        # de assinatura. NÃO CONFIRMADO contra um payload real (ver
        # aviso em criar_pagamento_pix_ativacao sobre testar contra o
        # sandbox); se o nome do campo vier diferente, isto
        # simplesmente não preenche nada -- não quebra o resto do
        # processamento do webhook.
        credit_card = payment.get('creditCard') or {}
        if assinatura and credit_card.get('creditCardNumber'):
            assinatura.cartao_ultimos_digitos = credit_card.get('creditCardNumber')
            assinatura.cartao_bandeira = credit_card.get('creditCardBrand')

        if assinatura:
            status_antes = assinatura.status
            BillingService._aplicar_evento(assinatura, tipo_evento)
            logger.info(
                'Assinatura %s (usuario=%s): status %s -> %s (evento %s)',
                assinatura.id, assinatura.usuario_id, status_antes, assinatura.status, tipo_evento,
            )
        else:
            # Antes só logava quando subscription_id OU external_reference
            # vinham preenchidos -- se os dois viessem vazios (payload
            # de formato diferente do esperado), passava batido em
            # silêncio total, sem tocar em nenhuma Assinatura e sem
            # deixar rastro nenhum no log pra investigar depois.
            logger.warning(
                'Webhook Asaas (subscription=%s, externalReference=%s, customer=%s) sem Assinatura correspondente no banco',
                subscription_id, external_reference, customer_id,
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
            # Pix é pagamento avulso (sem assinatura recorrente no
            # Asaas) -- cada confirmação vale por ~1 mês a partir de
            # AGORA, não a partir de um "próximo vencimento" que o
            # gateway já saberia (isso só existe pra cartão, via
            # subscription). Cartão não usa periodo_atual_fim -- quem
            # garante a renovação dele é o próprio Asaas.
            if assinatura.forma_pagamento == 'pix':
                assinatura.periodo_atual_fim = _proximo_vencimento_mensal(agora)
        elif tipo_evento in EVENTOS_ATRASO:
            BillingService._iniciar_atraso(assinatura, agora)
        elif tipo_evento in EVENTOS_CANCELAMENTO:
            assinatura.status = 'canceled'
            assinatura.cancelado_em = agora
        else:
            # Antes era logger.debug -- INVISÍVEL em produção, já que
            # app.logger está configurado pra nível INFO (ver app.py).
            # Foi exatamente isso que impediu diagnosticar o webhook
            # que chegou (200 OK) mas não ativou a assinatura: o tipo
            # de evento provavelmente caiu aqui sem deixar rastro nenhum.
            logger.info('Evento Asaas %s sem tratamento específico (assinatura %s inalterada)', tipo_evento, assinatura.id)

    @staticmethod
    def _iniciar_atraso(assinatura: Assinatura, agora: datetime):
        """Move a assinatura pra 'past_due' e calcula até quando a
        carência aguenta antes de bloquear de vez -- extraído de
        _aplicar_evento (webhook de atraso de cartão) pra ser
        reaproveitado também por expirar_pix_vencidos (fim do período
        de um pagamento Pix avulso, sem nenhum webhook envolvido)."""
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

    @staticmethod
    def expirar_pix_vencidos():
        """Job periódico (ex: a cada hora, junto com
        expirar_carencias_vencidas): Pix não tem débito automático, só
        webhook quando alguém PAGA -- nada avisa quando um período
        Pix simplesmente TERMINA sem ninguém pagar de novo. Por isso
        este job precisa varrer ativamente as assinaturas via Pix cujo
        periodo_atual_fim já passou e iniciar a carência de atraso
        (mesma lógica/prazos de sempre -- ver _iniciar_atraso), como se
        fosse um evento de atraso vindo do gateway."""
        agora = datetime.now(timezone.utc)
        vencidas = Assinatura.query.filter(
            Assinatura.status == 'active',
            Assinatura.forma_pagamento == 'pix',
            Assinatura.periodo_atual_fim.isnot(None),
            Assinatura.periodo_atual_fim <= agora,
        ).all()
        for assinatura in vencidas:
            BillingService._iniciar_atraso(assinatura, agora)
        if vencidas:
            db.session.commit()
            logger.info('%d assinatura(s) Pix movida(s) para past_due por período vencido', len(vencidas))
        return len(vencidas)