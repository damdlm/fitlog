"""P2-b: o rate limit do webhook separa quem tem o token certo de quem não tem."""
from routes.billing_routes import _chave_rate_limit_webhook


def test_webhook_com_token_certo_e_errado_usam_baldes_diferentes(app):
    app.config['ASAAS_WEBHOOK_TOKEN'] = 'token-correto'
    with app.test_request_context('/billing/webhook/asaas', method='POST',
                                  headers={'asaas-access-token': 'token-correto'}):
        chave_asaas = _chave_rate_limit_webhook()
    with app.test_request_context('/billing/webhook/asaas', method='POST',
                                  headers={'asaas-access-token': 'errado'}):
        chave_anonima = _chave_rate_limit_webhook()
    with app.test_request_context('/billing/webhook/asaas', method='POST'):
        chave_sem_token = _chave_rate_limit_webhook()
    assert chave_asaas == 'asaas-webhook-autenticado'
    assert chave_anonima.startswith('asaas-webhook-anonimo:')
    assert chave_sem_token.startswith('asaas-webhook-anonimo:')
    assert chave_asaas != chave_anonima