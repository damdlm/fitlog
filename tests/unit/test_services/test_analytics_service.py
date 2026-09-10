"""
Testes de regressão para services/analytics_service.py e os 3 pontos
de disparo (sign_up, workout_completed, subscription_started).

Cobertura deliberadamente enxuta (smoke tests) -- o objetivo é
garantir que os eventos disparam nos momentos certos, não vazam PII e
não quebram o fluxo principal quando desligados/com erro, não testar
cada combinação possível de parâmetro.
"""
from models import db, User, EventoAnalytics, Assinatura, Plano
from services.analytics_service import AnalyticsService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('Senha1234')
    db.session.add(user)
    db.session.commit()
    return user


class TestAnalyticsServiceTrackDiretamente:
    def test_desligado_por_padrao_nao_grava_nada(self, app):
        with app.app_context():
            AnalyticsService.track('sign_up', method='email')
            assert EventoAnalytics.query.count() == 0

    def test_ligado_grava_evento_permitido(self, app):
        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            AnalyticsService.track('sign_up', method='email')
            evento = EventoAnalytics.query.one()
            assert evento.nome_evento == 'sign_up'
            assert evento.parametros == {'method': 'email'}

    def test_evento_desconhecido_e_ignorado(self, app):
        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            AnalyticsService.track('evento_qualquer_nao_previsto')
            assert EventoAnalytics.query.count() == 0

    def test_parametro_fora_da_allowlist_e_descartado_sem_quebrar(self, app):
        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            AnalyticsService.track('sign_up', method='email', email='vazou@teste.com')
            evento = EventoAnalytics.query.one()
            assert evento.parametros == {'method': 'email'}
            assert 'email' not in (evento.parametros or {})


class TestSignUpNoCadastro:
    def test_cadastro_com_sucesso_dispara_sign_up(self, client, app):
        app.config['ANALYTICS_ENABLED'] = True

        resp = client.post('/auth/register', data={
            'username': 'novo_usuario_analytics',
            'email': 'novo_usuario_analytics@teste.com',
            'password': 'Senha1234',
            'confirm_password': 'Senha1234',
            'tipo_usuario': 'aluno',
            'aceite_termos': 'on',
        }, follow_redirects=True)

        assert resp.status_code == 200
        with app.app_context():
            eventos = EventoAnalytics.query.filter_by(nome_evento='sign_up').all()
            assert len(eventos) == 1
            assert eventos[0].parametros == {'method': 'email'}

    def test_cadastro_com_erro_de_validacao_nao_dispara_evento(self, client, app):
        app.config['ANALYTICS_ENABLED'] = True

        client.post('/auth/register', data={
            'username': 'ab',  # username curto demais -- falha de validação
            'email': 'invalido@teste.com',
            'password': 'Senha1234',
            'confirm_password': 'Senha1234',
            'tipo_usuario': 'aluno',
            'aceite_termos': 'on',
        })

        with app.app_context():
            assert EventoAnalytics.query.filter_by(nome_evento='sign_up').count() == 0


class TestWorkoutCompletedAoSalvarRegistros:
    def test_salvar_registros_com_sucesso_dispara_workout_completed(self, app):
        from datetime import date
        from services.registro_service import RegistroService
        from models import TreinoVersao, VersaoGlobal, ExercicioUsuario

        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            user = _criar_usuario('analytics_workout')

            versao = VersaoGlobal(
                numero_versao=1, descricao='v1', divisao='ABC',
                data_inicio=date(2024, 1, 1), user_id=user.id,
            )
            db.session.add(versao)
            db.session.commit()

            treino = TreinoVersao(
                versao_id=versao.id, codigo='A', nome_treino='Treino A',
                descricao_treino='d',
            )
            db.session.add(treino)
            db.session.commit()

            exercicio = ExercicioUsuario(usuario_id=user.id, nome='Supino')
            db.session.add(exercicio)
            db.session.commit()

            ok = RegistroService.salvar_registros(
                treino_id=treino.id, versao_id=versao.id, periodo='Janeiro/2024', semana=1,
                dados_exercicios={
                    str(exercicio.id): {
                        'carga': 40, 'repeticoes': 10, 'num_series': 3,
                        'exercicio_id': exercicio.id, 'tipo': 'usuario',
                    },
                },
                user_id=user.id,
            )

            assert ok is True
            evento = EventoAnalytics.query.filter_by(nome_evento='workout_completed').one()
            # Só contagem agregada -- nunca nome de exercício, carga ou ID.
            assert evento.parametros == {'exercise_count': 1}


class TestSubscriptionStartedNoWebhook:
    def _criar_assinatura_trialing(self, plano=None):
        aluno = _criar_usuario(f'webhook_analytics_{id(object())}')
        assinatura = Assinatura(
            usuario_id=aluno.id, status='trialing',
            gateway_subscription_id='sub_analytics_1',
            plano_id=plano.id if plano else None,
        )
        db.session.add(assinatura)
        db.session.commit()
        return assinatura

    def test_primeira_confirmacao_dispara_subscription_started_com_valor(self, app):
        from services.billing_service import BillingService

        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            plano = Plano(
                codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno',
                preco_centavos=599, ativo=True,
            )
            db.session.add(plano)
            db.session.flush()
            self._criar_assinatura_trialing(plano=plano)

            ok = BillingService.processar_webhook({
                'id': 'evt_analytics_1', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'subscription': 'sub_analytics_1'},
            })

            assert ok is True
            evento = EventoAnalytics.query.filter_by(nome_evento='subscription_started').one()
            assert evento.parametros == {'value': 5.99, 'currency': 'BRL', 'plano': 'aluno_fit'}

    def test_renovacao_de_assinatura_ja_ativa_nao_duplica_evento(self, app):
        from services.billing_service import BillingService

        app.config['ANALYTICS_ENABLED'] = True
        with app.app_context():
            assinatura = self._criar_assinatura_trialing()
            assinatura.status = 'active'
            db.session.commit()

            ok = BillingService.processar_webhook({
                'id': 'evt_analytics_renovacao', 'event': 'PAYMENT_CONFIRMED',
                'payment': {'subscription': 'sub_analytics_1'},
            })

            assert ok is True
            assert EventoAnalytics.query.filter_by(nome_evento='subscription_started').count() == 0
