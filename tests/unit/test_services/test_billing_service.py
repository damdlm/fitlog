"""Testes para BillingService -- regras de cobrança/assinatura.

Cobrem: trial de 30 dias (aluno e professor), gating de acesso premium
(trial ativo/expirado, assinatura ativa, carência de pagamento
atrasado, cancelada), plano de gestão do professor pela contagem de
alunos (3-9 = Pró, 10+ = Premium), bloqueio de cadastro de novo aluno
sem upgrade, carência diferenciada (3 dias padrão / 15 dias pro
Pró-Premium) e bloqueio de acesso aos alunos após a carência, e
processamento idempotente de webhook do Asaas.
"""
from datetime import datetime, timedelta, timezone

from models import db, User, AlunoProfessor, Assinatura, EventoWebhookAsaas, Plano
from services.billing_service import BillingService, DadosCobrancaIncompletosError, TRIAL_DIAS


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo_usuario)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _preencher_dados_cobranca(usuario, cpf_cnpj='12345678900'):
    """Preenche os 4 campos que o Asaas exige pra checkout de cartão
    recorrente (cpf_cnpj, telefone, endereco_cep, endereco_numero) --
    usado nos testes que precisam passar de campos_cobranca_faltando()
    e chegar de fato na chamada HTTP."""
    usuario.cpf_cnpj = cpf_cnpj
    usuario.telefone = '11987654321'
    usuario.endereco_cep = '01310100'
    usuario.endereco_numero = '100'
    return usuario


def _criar_planos_professor():
    pro = Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
                 preco_centavos=2990, min_alunos=3, max_alunos=9, ativo=True)
    premium = Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor',
                     preco_centavos=9990, min_alunos=10, max_alunos=None, ativo=True)
    fit = Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno',
                preco_centavos=599, ativo=True)
    db.session.add_all([pro, premium, fit])
    db.session.flush()
    return pro, premium, fit


def _vincular_alunos(professor, quantidade):
    for i in range(quantidade):
        aluno = _criar_usuario(f'{professor.username}_aluno_{i}')
        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
    db.session.flush()


# ---------------------------------------------------------------------
# Trial (aluno e professor)
# ---------------------------------------------------------------------

class TestIniciarTrial:
    def test_cria_assinatura_em_trialing(self, app):
        with app.app_context():
            aluno = _criar_usuario('aluno1')
            assinatura = BillingService.iniciar_trial(aluno)

            assert assinatura.status == 'trialing'
            assert assinatura.usuario_id == aluno.id
            assert assinatura.trial_termina_em is not None

    def test_trial_termina_em_30_dias(self, app):
        with app.app_context():
            aluno = _criar_usuario('aluno2')
            antes = datetime.now(timezone.utc)
            assinatura = BillingService.iniciar_trial(aluno)
            depois = datetime.now(timezone.utc)

            esperado_min = antes + timedelta(days=TRIAL_DIAS)
            esperado_max = depois + timedelta(days=TRIAL_DIAS)
            trial_termina_em = assinatura.trial_termina_em.replace(tzinfo=timezone.utc) \
                if assinatura.trial_termina_em.tzinfo is None else assinatura.trial_termina_em
            assert esperado_min <= trial_termina_em <= esperado_max

    def test_e_idempotente_nao_duplica(self, app):
        with app.app_context():
            aluno = _criar_usuario('aluno3')
            primeira = BillingService.iniciar_trial(aluno)
            segunda = BillingService.iniciar_trial(aluno)

            assert primeira.id == segunda.id
            assert Assinatura.query.filter_by(usuario_id=aluno.id).count() == 1

    def test_professor_tambem_ganha_trial(self, app):
        """Regra nova: professor também precisa do Plano Fit (ou
        trial) pra acessar Estatísticas/FitBot -- antes ele era isento."""
        with app.app_context():
            professor = _criar_usuario('prof_trial', tipo_usuario='professor')
            assinatura = BillingService.iniciar_trial(professor)

            assert assinatura.status == 'trialing'
            assert BillingService.usuario_tem_acesso_premium(professor) is True

    def test_usuario_so_pode_ter_uma_assinatura(self, app):
        """Um professor nunca tem duas cobranças -- é sempre a MESMA
        linha, mesmo depois de precisar upgrade pra Pró/Premium."""
        with app.app_context():
            professor = _criar_usuario('prof_uma_so', tipo_usuario='professor')
            BillingService.iniciar_trial(professor)
            BillingService.garantir_registro_assinatura(professor)

            assert Assinatura.query.filter_by(usuario_id=professor.id).count() == 1


# ---------------------------------------------------------------------
# Gating de acesso premium (Estatísticas/FitBot) -- aluno e professor
# ---------------------------------------------------------------------

class TestUsuarioTemAcessoPremium:
    def test_sem_assinatura_nao_tem_acesso(self, app):
        with app.app_context():
            aluno = _criar_usuario('sem_assinatura')
            assert BillingService.usuario_tem_acesso_premium(aluno) is False

    def test_trial_valido_tem_acesso(self, app):
        with app.app_context():
            aluno = _criar_usuario('trial_valido')
            BillingService.iniciar_trial(aluno)
            assert BillingService.usuario_tem_acesso_premium(aluno) is True

    def test_trial_expirado_bloqueia(self, app):
        with app.app_context():
            aluno = _criar_usuario('trial_expirado')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.trial_termina_em = datetime.now(timezone.utc) - timedelta(days=1)
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is False

    def test_assinatura_ativa_tem_acesso_mesmo_apos_trial(self, app):
        with app.app_context():
            aluno = _criar_usuario('assinante_ativo')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'active'
            assinatura.trial_termina_em = datetime.now(timezone.utc) - timedelta(days=1)
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is True

    def test_professor_com_pro_ativo_tambem_tem_acesso(self, app):
        """'os planos pró e premium já liberam essas telas também' --
        não precisa de nenhum plano separado."""
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_pro_stats', tipo_usuario='professor')
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = pro.id
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(professor) is True

    def test_past_due_dentro_da_carencia_mantem_acesso(self, app):
        with app.app_context():
            aluno = _criar_usuario('atrasado_carencia')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'past_due'
            assinatura.carencia_termina_em = datetime.now(timezone.utc) + timedelta(days=1)
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is True

    def test_past_due_apos_carencia_bloqueia(self, app):
        with app.app_context():
            aluno = _criar_usuario('atrasado_sem_carencia')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'past_due'
            assinatura.carencia_termina_em = datetime.now(timezone.utc) - timedelta(hours=1)
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is False

    def test_cancelada_bloqueia(self, app):
        with app.app_context():
            aluno = _criar_usuario('cancelado')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'canceled'
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is False

    def test_blocked_bloqueia(self, app):
        with app.app_context():
            aluno = _criar_usuario('bloqueado')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'blocked'
            db.session.commit()

            assert BillingService.usuario_tem_acesso_premium(aluno) is False


# ---------------------------------------------------------------------
# Plano de gestão do professor pela contagem de alunos
# ---------------------------------------------------------------------

class TestPlanoGestaoNecessario:
    def test_ate_2_alunos_fica_na_faixa_gratuita(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_gratis', tipo_usuario='professor')
            _vincular_alunos(professor, 2)

            assert BillingService.plano_gestao_necessario(professor) is None

    def test_3_alunos_entra_no_pro(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_pro_min', tipo_usuario='professor')
            _vincular_alunos(professor, 3)

            plano = BillingService.plano_gestao_necessario(professor)
            assert plano is not None
            assert plano.codigo == 'professor_pro'

    def test_9_alunos_ainda_no_pro(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_pro_max', tipo_usuario='professor')
            _vincular_alunos(professor, 9)

            plano = BillingService.plano_gestao_necessario(professor)
            assert plano.codigo == 'professor_pro'

    def test_10_alunos_vira_premium(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_premium_min', tipo_usuario='professor')
            _vincular_alunos(professor, 10)

            plano = BillingService.plano_gestao_necessario(professor)
            assert plano.codigo == 'professor_premium'

    def test_alunos_inativos_nao_contam(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_inativos', tipo_usuario='professor')
            _vincular_alunos(professor, 2)
            aluno_extra = _criar_usuario('prof_inativos_aluno_extra')
            db.session.add(AlunoProfessor(aluno_id=aluno_extra.id, professor_id=professor.id, ativo=False))
            db.session.commit()

            assert BillingService.plano_gestao_necessario(professor) is None


class TestPlanoRecomendadoProfessor:
    def test_ate_2_alunos_oferece_plano_fit(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_recomenda_fit', tipo_usuario='professor')
            _vincular_alunos(professor, 1)

            plano = BillingService.plano_recomendado_professor(professor)
            assert plano.codigo == 'aluno_fit'

    def test_5_alunos_oferece_pro(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_recomenda_pro', tipo_usuario='professor')
            _vincular_alunos(professor, 5)

            plano = BillingService.plano_recomendado_professor(professor)
            assert plano.codigo == 'professor_pro'


# ---------------------------------------------------------------------
# Bloqueio de cadastro de novo aluno sem upgrade
# ---------------------------------------------------------------------

class TestPodeCadastrarAluno:
    def test_ate_2_alunos_sempre_pode(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_pode_ate2', tipo_usuario='professor')
            _vincular_alunos(professor, 1)

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is True
            assert mensagem is None

    def test_terceiro_aluno_sem_assinatura_e_bloqueado(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_bloqueia_3', tipo_usuario='professor')
            _vincular_alunos(professor, 2)

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is False
            assert 'Pró' in mensagem

    def test_trial_nao_libera_cadastro_alem_de_2(self, app):
        """Trial só dá acesso a Estatísticas/FitBot -- não libera
        gerenciar mais de 2 alunos."""
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_trial_nao_libera', tipo_usuario='professor')
            BillingService.iniciar_trial(professor)
            _vincular_alunos(professor, 2)

            pode, _ = BillingService.pode_cadastrar_aluno(professor)
            assert pode is False

    def test_terceiro_aluno_com_pro_ativo_e_permitido(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_com_pro', tipo_usuario='professor')
            _vincular_alunos(professor, 2)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = pro.id
            db.session.commit()

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is True
            assert mensagem is None

    def test_decimo_aluno_com_pro_ativo_e_bloqueado_pede_premium(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_pro_no_limite', tipo_usuario='professor')
            _vincular_alunos(professor, 9)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = pro.id
            db.session.commit()

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is False
            assert 'Premium' in mensagem

    def test_decimo_aluno_com_premium_ativo_e_permitido(self, app):
        with app.app_context():
            _, premium, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_com_premium', tipo_usuario='professor')
            _vincular_alunos(professor, 9)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = premium.id
            db.session.commit()

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is True
            assert mensagem is None

    def test_pro_com_pagamento_atrasado_nao_permite_novo_aluno(self, app):
        """Só assinatura com status 'active' conta -- past_due (mesmo
        dentro da carência de acesso) não libera cadastrar mais gente."""
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_pro_atrasado', tipo_usuario='professor')
            _vincular_alunos(professor, 2)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'past_due'
            assinatura.plano_id = pro.id
            assinatura.carencia_termina_em = datetime.now(timezone.utc) + timedelta(days=10)
            db.session.commit()

            pode, mensagem = BillingService.pode_cadastrar_aluno(professor)
            assert pode is False


# ---------------------------------------------------------------------
# Bloqueio de acesso aos alunos após 15 dias de inadimplência
# ---------------------------------------------------------------------

class TestProfessorAcessoAlunosLiberado:
    def test_ate_2_alunos_nunca_bloqueia(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_acesso_ate2', tipo_usuario='professor')
            _vincular_alunos(professor, 2)
            # nem precisa de assinatura pra continuar liberado

            assert BillingService.professor_acesso_alunos_liberado(professor) is True

    def test_pro_ativo_libera_acesso(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_acesso_pro_ativo', tipo_usuario='professor')
            _vincular_alunos(professor, 5)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = pro.id
            db.session.commit()

            assert BillingService.professor_acesso_alunos_liberado(professor) is True

    def test_pro_blocked_bloqueia_acesso_aos_alunos(self, app):
        """Regra pedida: 15 dias de inadimplência -> perde acesso aos
        alunos (vínculo continua existindo, só a tela é bloqueada)."""
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_acesso_bloqueado', tipo_usuario='professor')
            _vincular_alunos(professor, 5)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'blocked'
            assinatura.plano_id = pro.id
            db.session.commit()

            assert BillingService.professor_acesso_alunos_liberado(professor) is False
            # o vínculo em si nunca é removido por isso
            assert BillingService.contar_alunos_ativos(professor) == 5

    def test_pro_past_due_dentro_da_carencia_ainda_libera(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_acesso_carencia', tipo_usuario='professor')
            _vincular_alunos(professor, 5)
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'past_due'
            assinatura.plano_id = pro.id
            assinatura.carencia_termina_em = datetime.now(timezone.utc) + timedelta(days=10)
            db.session.commit()

            assert BillingService.professor_acesso_alunos_liberado(professor) is True


class TestCarenciaDiferenciadaPorPlano:
    def test_atraso_no_plano_pro_da_15_dias_de_carencia(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_carencia_15', tipo_usuario='professor')
            assinatura = BillingService.iniciar_trial(professor)
            assinatura.status = 'active'
            assinatura.plano_id = pro.id
            assinatura.gateway_subscription_id = 'sub_pro_carencia'
            db.session.commit()

            BillingService.processar_webhook({
                'id': 'evt_carencia_pro', 'event': 'PAYMENT_OVERDUE',
                'payment': {'subscription': 'sub_pro_carencia'},
            })

            db.session.refresh(assinatura)
            agora = datetime.now(timezone.utc)
            carencia = assinatura.carencia_termina_em.replace(tzinfo=timezone.utc) \
                if assinatura.carencia_termina_em.tzinfo is None else assinatura.carencia_termina_em
            dias_restantes = (carencia - agora).days
            assert 14 <= dias_restantes <= 15

    def test_atraso_no_plano_fit_da_3_dias_de_carencia(self, app):
        with app.app_context():
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('aluno_carencia_3')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'active'
            assinatura.plano_id = fit.id
            assinatura.gateway_subscription_id = 'sub_fit_carencia'
            db.session.commit()

            BillingService.processar_webhook({
                'id': 'evt_carencia_fit', 'event': 'PAYMENT_OVERDUE',
                'payment': {'subscription': 'sub_fit_carencia'},
            })

            db.session.refresh(assinatura)
            agora = datetime.now(timezone.utc)
            carencia = assinatura.carencia_termina_em.replace(tzinfo=timezone.utc) \
                if assinatura.carencia_termina_em.tzinfo is None else assinatura.carencia_termina_em
            dias_restantes = (carencia - agora).days
            assert 2 <= dias_restantes <= 3


class TestVerificarMudancasTierProfessores:
    def test_detecta_professor_que_mudou_de_faixa(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_mudou', tipo_usuario='professor')
            _vincular_alunos(professor, 3)

            # Estado atual gravado ainda reflete a faixa gratuita (nenhum
            # plano associado) -- simula o professor tendo acabado de
            # passar de 2 para 3 alunos, sem a mudança ainda aplicada.
            assinatura = Assinatura(usuario_id=professor.id, status='active', plano_id=None)
            db.session.add(assinatura)
            db.session.commit()

            mudancas = BillingService.verificar_mudancas_tier_professores()
            professores_com_mudanca = [m['professor'].id for m in mudancas]
            assert professor.id in professores_com_mudanca

    def test_nao_reporta_professor_sem_mudanca(self, app):
        with app.app_context():
            pro, _, _ = _criar_planos_professor()
            professor = _criar_usuario('prof_estavel', tipo_usuario='professor')
            _vincular_alunos(professor, 3)

            assinatura = Assinatura(usuario_id=professor.id, status='active', plano_id=pro.id)
            db.session.add(assinatura)
            db.session.commit()

            mudancas = BillingService.verificar_mudancas_tier_professores()
            professores_com_mudanca = [m['professor'].id for m in mudancas]
            assert professor.id not in professores_com_mudanca

    def test_nao_reporta_professor_na_faixa_gratuita(self, app):
        with app.app_context():
            _criar_planos_professor()
            professor = _criar_usuario('prof_gratis_sem_mudanca', tipo_usuario='professor')
            _vincular_alunos(professor, 1)

            mudancas = BillingService.verificar_mudancas_tier_professores()
            professores_com_mudanca = [m['professor'].id for m in mudancas]
            assert professor.id not in professores_com_mudanca


# ---------------------------------------------------------------------
# Webhook: idempotência e transições de status
# ---------------------------------------------------------------------

class TestProcessarWebhook:
    def _criar_assinatura_com_subscription(self, status='trialing'):
        aluno = _criar_usuario(f'webhook_{status}_{id(object())}')
        assinatura = Assinatura(
            usuario_id=aluno.id, status=status,
            gateway_subscription_id='sub_123',
        )
        db.session.add(assinatura)
        db.session.commit()
        return assinatura

    def test_payload_sem_id_ou_event_e_rejeitado(self, app):
        with app.app_context():
            ok = BillingService.processar_webhook({'payment': {}})
            assert ok is False
            assert EventoWebhookAsaas.query.count() == 0

    def test_payment_confirmed_ativa_assinatura(self, app):
        with app.app_context():
            assinatura = self._criar_assinatura_com_subscription(status='trialing')
            payload = {
                'id': 'evt_1', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'subscription': 'sub_123'},
            }
            ok = BillingService.processar_webhook(payload)

            assert ok is True
            db.session.refresh(assinatura)
            assert assinatura.status == 'active'

    def test_payment_overdue_marca_past_due_com_carencia(self, app):
        with app.app_context():
            assinatura = self._criar_assinatura_com_subscription(status='active')
            payload = {
                'id': 'evt_2', 'event': 'PAYMENT_OVERDUE',
                'payment': {'subscription': 'sub_123'},
            }
            BillingService.processar_webhook(payload)

            db.session.refresh(assinatura)
            assert assinatura.status == 'past_due'
            assert assinatura.carencia_termina_em is not None

    def test_subscription_deleted_cancela(self, app):
        with app.app_context():
            assinatura = self._criar_assinatura_com_subscription(status='active')
            payload = {
                'id': 'evt_3', 'event': 'SUBSCRIPTION_DELETED',
                'payment': {'subscription': 'sub_123'},
            }
            BillingService.processar_webhook(payload)

            db.session.refresh(assinatura)
            assert assinatura.status == 'canceled'
            assert assinatura.cancelado_em is not None

    def test_evento_repetido_e_ignorado_na_segunda_vez(self, app):
        with app.app_context():
            assinatura = self._criar_assinatura_com_subscription(status='trialing')
            payload = {
                'id': 'evt_4', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'subscription': 'sub_123'},
            }
            BillingService.processar_webhook(payload)

            # Muda o status manualmente pra provar que o reprocessamento
            # do MESMO event_id não mexe em nada de novo.
            assinatura.status = 'canceled'
            db.session.commit()

            BillingService.processar_webhook(payload)
            db.session.refresh(assinatura)
            assert assinatura.status == 'canceled'
            assert EventoWebhookAsaas.query.filter_by(event_id='evt_4').count() == 1

    def test_evento_para_subscription_desconhecida_nao_quebra(self, app):
        with app.app_context():
            payload = {
                'id': 'evt_5', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'subscription': 'sub_nunca_existiu'},
            }
            ok = BillingService.processar_webhook(payload)
            assert ok is True

    def test_payload_sem_subscription_nem_external_reference_e_registrado_mas_nao_quebra(self, app, caplog):
        """Regressão: se o payment não tem 'subscription' NEM
        'externalReference' (payload de formato inesperado, diferente
        do que documentamos), o código antes passava em silêncio total
        -- nenhuma Assinatura tocada e nenhum log gerado. Agora precisa
        pelo menos avisar (nível WARNING, visível em produção)."""
        import logging
        with app.app_context():
            with caplog.at_level(logging.WARNING, logger='services.billing_service'):
                payload = {
                    'id': 'evt_sem_identificadores', 'event': 'PAYMENT_CONFIRMED',
                    'payment': {'status': 'CONFIRMED'},  # sem subscription, sem externalReference
                }
                ok = BillingService.processar_webhook(payload)

            assert ok is True
            assert any('sem Assinatura correspondente' in r.message for r in caplog.records)
            # Mesmo sem achar a Assinatura, o evento fica registrado
            # pra idempotência (não reprocessa se o Asaas reenviar).
            assert EventoWebhookAsaas.query.filter_by(event_id='evt_sem_identificadores').count() == 1

    def test_evento_recebido_e_sempre_logado_em_info(self, app, caplog):
        """Regressão: o webhook precisa deixar rastro do que recebeu
        (tipo de evento, subscription, externalReference) em nível
        INFO -- é isso que torna possível diagnosticar quando um evento
        chega com 200 OK mas não muda nada (ex: tipo de evento que
        ainda não tratamos)."""
        import logging
        with app.app_context():
            with caplog.at_level(logging.INFO, logger='services.billing_service'):
                payload = {
                    'id': 'evt_tipo_desconhecido', 'event': 'CHECKOUT_PAID',
                    'payment': {'subscription': 'sub_nao_importa'},
                }
                BillingService.processar_webhook(payload)

            mensagens = [r.message for r in caplog.records]
            assert any('Webhook Asaas recebido' in m and 'CHECKOUT_PAID' in m for m in mensagens)


# ---------------------------------------------------------------------
# Expiração de carência (job periódico)
# ---------------------------------------------------------------------

class TestExpirarCarenciasVencidas:
    def test_move_para_blocked_apos_carencia_vencida(self, app):
        with app.app_context():
            aluno = _criar_usuario('carencia_vencida')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'past_due'
            assinatura.carencia_termina_em = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.session.commit()

            total = BillingService.expirar_carencias_vencidas()

            db.session.refresh(assinatura)
            assert total == 1
            assert assinatura.status == 'blocked'

    def test_nao_mexe_em_carencia_ainda_valida(self, app):
        with app.app_context():
            aluno = _criar_usuario('carencia_valida')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.status = 'past_due'
            assinatura.carencia_termina_em = datetime.now(timezone.utc) + timedelta(hours=1)
            db.session.commit()

            total = BillingService.expirar_carencias_vencidas()

            db.session.refresh(assinatura)
            assert total == 0
            assert assinatura.status == 'past_due'


# ---------------------------------------------------------------------
# criar_assinatura_checkout -- chamada HTTP real (mockada) pro Asaas
# ---------------------------------------------------------------------

class _RespostaFake:
    """Substitui requests.Response nos testes -- só o que
    criar_assinatura_checkout usa (raise_for_status/json/text)."""
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
        self.text = str(json_data)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f'{self.status_code} erro simulado')

    def json(self):
        return self._json


class TestCriarAssinaturaCheckout:
    def test_usa_endpoint_checkouts_com_next_due_date_e_external_reference(self, app, monkeypatch):
        """Regressão: a versão antiga chamava /subscriptions sem
        nextDueDate (campo obrigatório) e com billingType='UNDEFINED'
        (valor inválido pra esse endpoint) -- o Asaas respondia 400 e
        o botão "Assinar" nunca funcionava de verdade."""
        chamadas = []

        def _fake_post(url, json=None, headers=None, timeout=None):
            chamadas.append({'url': url, 'json': json})
            if url.endswith('/customers'):
                return _RespostaFake({'id': 'cus_fake123'})
            if url.endswith('/checkouts'):
                return _RespostaFake({
                    'id': 'chk_fake123',
                    'link': 'https://sandbox.asaas.com/checkoutSession/show/chk_fake123',
                    'status': 'ACTIVE',
                })
            raise AssertionError(f'URL inesperada: {url}')

        monkeypatch.setattr('services.billing_service.requests.post', _fake_post)

        with app.app_context():
            app.config['ASAAS_API_KEY'] = 'chave-de-teste'
            app.config['APP_BASE_URL'] = 'https://fitlog.up.railway.app'
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('checkout_fields')
            _preencher_dados_cobranca(aluno)
            assinatura = BillingService.iniciar_trial(aluno)
            db.session.commit()

            link = BillingService.criar_assinatura_checkout(aluno, fit)

            assert link == 'https://sandbox.asaas.com/checkoutSession/show/chk_fake123'

            chamada_cliente = next(c for c in chamadas if c['url'].endswith('/customers'))
            assert chamada_cliente['json']['cpfCnpj'] == '12345678900'
            assert chamada_cliente['json']['phone'] == '11987654321'
            assert chamada_cliente['json']['postalCode'] == '01310100'
            assert chamada_cliente['json']['addressNumber'] == '100'

            chamada_checkout = next(c for c in chamadas if c['url'].endswith('/checkouts'))
            payload = chamada_checkout['json']
            assert 'nextDueDate' in payload['subscription']
            assert payload['subscription']['cycle'] == 'MONTHLY'
            # Regressão: o Asaas rejeita o checkout com
            # "O campo 'items' é obrigatório." se esse array não vier
            # -- documentação não deixa isso claro, só os exemplos.
            assert len(payload['items']) == 1
            assert payload['items'][0]['value'] == fit.preco_centavos / 100
            assert payload['externalReference'] == str(assinatura.id)
            assert payload['chargeTypes'] == ['RECURRENT']
            # Regressão: o Asaas rejeita billingTypes com PIX/BOLETO
            # quando chargeTypes inclui RECURRENT -- só CREDIT_CARD é
            # aceito pra cobrança recorrente nesse fluxo de checkout.
            assert payload['billingTypes'] == ['CREDIT_CARD']
            assert 'callback' in payload and payload['callback']['successUrl']

            # A assinatura de gateway só se confirma depois que o
            # pagador escolhe forma de pagamento -- não temos
            # gateway_subscription_id ainda neste ponto.
            db.session.refresh(assinatura)
            assert assinatura.gateway_subscription_id is None
            assert assinatura.plano_id == fit.id

    def test_sem_dados_de_cobranca_levanta_erro_especifico_sem_chamar_gateway(self, app, monkeypatch):
        chamou = {'valor': False}

        def _fake_post(*a, **k):
            chamou['valor'] = True
            return _RespostaFake({'id': 'cus_nao_deveria_chamar'})

        monkeypatch.setattr('services.billing_service.requests.post', _fake_post)

        with app.app_context():
            app.config['ASAAS_API_KEY'] = 'chave-de-teste'
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('checkout_sem_cpf')
            BillingService.iniciar_trial(aluno)
            db.session.commit()

            try:
                BillingService.criar_assinatura_checkout(aluno, fit)
                assert False, 'deveria ter levantado DadosCobrancaIncompletosError'
            except DadosCobrancaIncompletosError as e:
                assert set(e.campos) == {'cpf_cnpj', 'telefone', 'endereco_cep', 'endereco_numero'}

            assert chamou['valor'] is False

    def test_faltando_so_um_campo_ja_bloqueia(self, app, monkeypatch):
        """Não basta ter 3 dos 4 campos -- todos são exigidos."""
        chamou = {'valor': False}

        def _fake_post(*a, **k):
            chamou['valor'] = True
            return _RespostaFake({'id': 'cus_nao_deveria_chamar'})

        monkeypatch.setattr('services.billing_service.requests.post', _fake_post)

        with app.app_context():
            app.config['ASAAS_API_KEY'] = 'chave-de-teste'
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('checkout_falta_numero')
            _preencher_dados_cobranca(aluno)
            aluno.endereco_numero = None  # só este falta
            BillingService.iniciar_trial(aluno)
            db.session.commit()

            try:
                BillingService.criar_assinatura_checkout(aluno, fit)
                assert False, 'deveria ter levantado DadosCobrancaIncompletosError'
            except DadosCobrancaIncompletosError as e:
                assert e.campos == ['endereco_numero']

            assert chamou['valor'] is False

    def test_cliente_ja_existente_e_atualizado_via_put_com_cpf(self, app, monkeypatch):
        """Cobre o caso real que já aconteceu em produção: um cliente
        criado ANTES do usuário ter CPF/CNPJ cadastrado (tentativa de
        checkout anterior a esta correção) precisa ser atualizado, não
        recriado, senão fica pra sempre sem o dado."""
        chamadas = []

        def _fake_post(url, json=None, headers=None, timeout=None):
            chamadas.append(('POST', url, json))
            return _RespostaFake({
                'id': 'chk_fake789',
                'link': 'https://sandbox.asaas.com/checkoutSession/show/chk_fake789',
            })

        def _fake_put(url, json=None, headers=None, timeout=None):
            chamadas.append(('PUT', url, json))
            return _RespostaFake({'id': 'cus_ja_existente'})

        monkeypatch.setattr('services.billing_service.requests.post', _fake_post)
        monkeypatch.setattr('services.billing_service.requests.put', _fake_put)

        with app.app_context():
            app.config['ASAAS_API_KEY'] = 'chave-de-teste'
            app.config['APP_BASE_URL'] = 'https://fitlog.up.railway.app'
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('checkout_cliente_existente')
            _preencher_dados_cobranca(aluno, cpf_cnpj='98765432100')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.gateway_customer_id = 'cus_ja_existente'
            db.session.commit()

            BillingService.criar_assinatura_checkout(aluno, fit)

            chamada_put = next(c for c in chamadas if c[0] == 'PUT')
            assert chamada_put[1].endswith('/customers/cus_ja_existente')
            assert chamada_put[2]['cpfCnpj'] == '98765432100'
            # Não deve ter criado um cliente novo por engano
            assert not any(c[0] == 'POST' and c[1].endswith('/customers') for c in chamadas)

    def test_erro_400_do_asaas_propaga_como_http_error(self, app, monkeypatch):
        import requests

        def _fake_post(url, json=None, headers=None, timeout=None):
            if url.endswith('/customers'):
                return _RespostaFake({'id': 'cus_fake456'})
            return _RespostaFake({'errors': [{'description': 'campo inválido'}]}, status_code=400)

        monkeypatch.setattr('services.billing_service.requests.post', _fake_post)

        with app.app_context():
            app.config['ASAAS_API_KEY'] = 'chave-de-teste'
            app.config['APP_BASE_URL'] = 'https://fitlog.up.railway.app'
            _, _, fit = _criar_planos_professor()
            aluno = _criar_usuario('checkout_erro_400')
            _preencher_dados_cobranca(aluno, cpf_cnpj='11122233344')
            BillingService.iniciar_trial(aluno)
            db.session.commit()

            try:
                BillingService.criar_assinatura_checkout(aluno, fit)
                assert False, 'deveria ter levantado HTTPError'
            except requests.HTTPError:
                pass


# ---------------------------------------------------------------------
# Casamento do webhook por externalReference (antes de termos
# gateway_subscription_id gravado)
# ---------------------------------------------------------------------

class TestWebhookPorExternalReference:
    def test_primeiro_evento_casa_por_external_reference_e_grava_subscription_id(self, app):
        with app.app_context():
            aluno = _criar_usuario('webhook_external_ref')
            assinatura = BillingService.iniciar_trial(aluno)
            db.session.commit()
            assinatura_id = assinatura.id

            payload = {
                'id': 'evt_ext_ref_1',
                'event': 'PAYMENT_CONFIRMED',
                'payment': {
                    'subscription': 'sub_novo_123',
                    'externalReference': str(assinatura_id),
                },
            }
            ok = BillingService.processar_webhook(payload)

            assert ok is True
            assinatura = Assinatura.query.get(assinatura_id)
            assert assinatura.status == 'active'
            assert assinatura.gateway_subscription_id == 'sub_novo_123'

    def test_evento_seguinte_ja_casa_direto_por_subscription_id(self, app):
        with app.app_context():
            aluno = _criar_usuario('webhook_subscription_ja_gravado')
            assinatura = BillingService.iniciar_trial(aluno)
            assinatura.gateway_subscription_id = 'sub_ja_existente'
            db.session.commit()
            assinatura_id = assinatura.id

            # externalReference errado de propósito -- prova que o
            # match por subscription_id tem prioridade e nem chega a
            # olhar o externalReference quando já encontrou por lá.
            payload = {
                'id': 'evt_subscription_direto',
                'event': 'PAYMENT_OVERDUE',
                'payment': {'subscription': 'sub_ja_existente', 'externalReference': '999999'},
            }
            BillingService.processar_webhook(payload)

            assinatura = Assinatura.query.get(assinatura_id)
            assert assinatura.status == 'past_due'

    def test_external_reference_nao_numerico_e_ignorado_com_seguranca(self, app):
        with app.app_context():
            payload = {
                'id': 'evt_ext_ref_invalido',
                'event': 'PAYMENT_CONFIRMED',
                'payment': {'externalReference': 'não-é-um-numero'},
            }
            ok = BillingService.processar_webhook(payload)
            assert ok is True  # não quebra, só não encontra nada pra atualizar