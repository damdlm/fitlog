"""Testes de segurança de headers -- Content Security Policy.

CORREÇÃO seção 17 (prompt de hardening): CSP progressiva, cobrindo
exatamente os domínios externos que a aplicação realmente usa (mapeados
por grep em todos os templates), sem quebrar a aplicação atual.
"""


def test_csp_presente_em_toda_resposta(client):
    resp = client.get('/auth/login')
    assert 'Content-Security-Policy' in resp.headers


def test_csp_restringe_default_src_a_self(client):
    resp = client.get('/auth/login')
    csp = resp.headers['Content-Security-Policy']
    assert "default-src 'self'" in csp


def test_csp_libera_apenas_os_cdns_realmente_usados(client):
    resp = client.get('/auth/login')
    csp = resp.headers['Content-Security-Policy']
    assert 'https://cdn.jsdelivr.net' in csp
    assert 'https://cdnjs.cloudflare.com' in csp
    # Nenhum outro domínio externo deveria aparecer na política
    dominios_https = set()
    for parte in csp.split(';'):
        for token in parte.strip().split():
            if token.startswith('https://'):
                dominios_https.add(token)
    assert dominios_https <= {'https://cdn.jsdelivr.net', 'https://cdnjs.cloudflare.com'}


def test_csp_bloqueia_object_e_restringe_frame_ancestors(client):
    resp = client.get('/auth/login')
    csp = resp.headers['Content-Security-Policy']
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp


def test_outros_headers_de_seguranca_presentes(client):
    resp = client.get('/auth/login')
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
    assert resp.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
