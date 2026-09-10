"""
Testes de regressão para as rotas de SEO estático dinâmico
(robots.txt, sitemap.xml, llms.txt) definidas em app.py.
"""
import xml.etree.ElementTree as ET


class TestRobotsTxt:
    def test_retorna_200_texto_plano(self, client):
        resp = client.get('/robots.txt')

        assert resp.status_code == 200
        assert resp.content_type.startswith('text/plain')

    def test_aponta_para_o_sitemap(self, client):
        resp = client.get('/robots.txt')

        assert b'Sitemap: ' in resp.data
        assert b'/sitemap.xml' in resp.data

    def test_bloqueia_areas_privadas_e_libera_a_raiz(self, client):
        resp = client.get('/robots.txt')
        texto = resp.data.decode('utf-8')

        assert 'Allow: /' in texto
        areas_privadas = (
            '/admin', '/professor', '/aluno', '/api', '/billing',
            '/contato/', '/fitbot', '/auth/reset-password',
        )
        for area_privada in areas_privadas:
            assert f'Disallow: {area_privada}' in texto

    def test_libera_o_contato_publico_apesar_do_contato_privado_bloqueado(self, client):
        # routes/contato_routes.py: '/contato/' (chat) e afins continuam
        # @login_required e bloqueados, mas '/contato/publico' é público
        # de propósito (link fica na landing) -- precisa do Allow mais
        # específico pra não ficar preso no Disallow: /contato/ genérico.
        texto = client.get('/robots.txt').data.decode('utf-8')

        assert 'Allow: /contato/publico' in texto


class TestSitemapXml:
    def test_retorna_200_xml_valido(self, client):
        resp = client.get('/sitemap.xml')

        assert resp.status_code == 200
        assert resp.content_type.startswith('application/xml')
        # Levanta exceção se não for XML bem formado.
        ET.fromstring(resp.data)

    def test_contem_somente_urls_publicas(self, client):
        resp = client.get('/sitemap.xml')
        texto = resp.data.decode('utf-8')

        assert '<loc>' in texto
        rotas_privadas = (
            '/dashboard', '/admin', '/professor', '/aluno', '/api',
            '/billing', '/auth/login', '/auth/register',
        )
        for rota_privada in rotas_privadas:
            assert rota_privada not in texto
        # /contato/publico é público (diferente de /contato/, o chat
        # autenticado) -- precisa estar no sitemap; só o privado deve
        # ficar de fora.
        assert '/contato/publico' in texto
        assert '/contato/enviar' not in texto


class TestLlmsTxt:
    def test_retorna_200_texto_plano_com_links_publicos(self, client):
        resp = client.get('/llms.txt')

        assert resp.status_code == 200
        assert resp.content_type.startswith('text/plain')
        assert b'FitLog' in resp.data
        assert b'/privacidade/' in resp.data
