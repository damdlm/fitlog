"""Analytics de produto do FitLog -- privacy-first, 100% server-side.

Sem nenhum script no navegador, sem cookie de rastreamento, sem
terceiro recebendo dado nenhum: cada evento é gravado direto na
própria tabela `eventos_analytics` do FitLog (ver models.py). Isso
mantém a política de privacidade (templates/privacidade/politica.html)
verdadeira sem precisar reescrevê-la -- ela já promete não usar
"ferramentas de rastreamento de terceiros", e nenhuma foi adicionada
aqui.

Só existem 3 eventos, de propósito:
- sign_up             -- cadastro concluído (routes/auth_routes.py)
- workout_completed   -- sessão de treino salva com sucesso
                         (services/registro_service.py). Adaptado: o
                         FitLog não tem um conceito de "treino
                         concluído" fechado no modelo de dados -- o
                         evento dispara quando uma sessão de exercícios
                         é salva (RegistroService.salvar_registros),
                         que pode incluir edições de uma sessão já
                         salva, não só a primeira vez.
- subscription_started -- assinatura vira 'active' vindo de um status
                         não-ativo (services/billing_service.py) --
                         primeira ativação/conversão real, não cada
                         renovação mensal.

Nenhum outro nome é aceito -- ver EVENTOS_PERMITIDOS. Nenhum parâmetro
de PII é aceito em nenhum evento (ver PARAMETROS_PERMITIDOS): nada de
e-mail, nome, CPF, telefone, ID de usuário/aluno/professor ou conteúdo
de treino.

ATIVAÇÃO: controlada por ANALYTICS_ENABLED (config.py) -- desligado
por padrão em qualquer ambiente até ser explicitamente ligado.

Fail-safe: qualquer erro aqui é logado e engolido, nunca propagado --
registrar analytics não pode derrubar cadastro, treino ou pagamento.
"""

import logging

from flask import current_app

from models import db, EventoAnalytics

logger = logging.getLogger(__name__)

EVENTOS_PERMITIDOS = {'sign_up', 'workout_completed', 'subscription_started'}

# Allow-list por evento -- qualquer parâmetro fora dessa lista é
# descartado antes de gravar (defesa em profundidade: mesmo que um
# chamador futuro passe algo indevido por engano, nunca é persistido).
PARAMETROS_PERMITIDOS = {
    'sign_up': {'method'},
    'workout_completed': {'exercise_count', 'workout_type', 'duration_bucket'},
    'subscription_started': {'value', 'currency', 'plano'},
}


class AnalyticsService:

    @staticmethod
    def track(nome_evento, **parametros):
        """Registra um evento de produto, se analytics estiver ligado.

        Nunca lança exceção -- uma falha aqui não pode quebrar o fluxo
        que disparou o evento (cadastro, treino, pagamento)."""
        try:
            if not current_app.config.get('ANALYTICS_ENABLED'):
                return

            if nome_evento not in EVENTOS_PERMITIDOS:
                logger.warning(
                    'AnalyticsService.track chamado com evento desconhecido: %s (ignorado)',
                    nome_evento,
                )
                return

            permitidos = PARAMETROS_PERMITIDOS.get(nome_evento, set())
            parametros_filtrados = {
                chave: valor for chave, valor in parametros.items() if chave in permitidos
            }
            descartados = set(parametros) - permitidos
            if descartados:
                logger.warning(
                    'AnalyticsService.track (%s): parâmetro(s) fora da allow-list descartado(s): %s',
                    nome_evento, sorted(descartados),
                )

            db.session.add(EventoAnalytics(
                nome_evento=nome_evento,
                parametros=parametros_filtrados or None,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception(
                'Falha ao registrar evento de analytics (%s) -- ignorada de propósito',
                nome_evento,
            )
