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
        # '/professor/pagina/<slug>' é pública e agora entra no sitemap;
        # por isso aqui ficam só as rotas PRIVADAS do professor.
        rotas_privadas = (
            '/dashboard', '/admin', '/professor/dashboard',
            '/professor/alunos', '/professor/pagina/editar', '/aluno',
            '/api', '/billing', '/auth/login', '/auth/register',
        )
        for rota_privada in rotas_privadas:
            assert rota_privada not in texto
        # /contato/publico é público (diferente de /contato/, o chat
        # autenticado) -- precisa estar no sitemap; só o privado deve
        # ficar de fora.
        assert '/contato/publico' in texto
        assert '/contato/enviar' not in texto


class TestSitemapCompleto:
    @staticmethod
    def _locs(resp):
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        raiz = ET.fromstring(resp.data)
        return [e.text for e in raiz.findall('s:url/s:loc', ns)]

    @staticmethod
    def _criar_professor(username, slug, ativo=True, tipo='professor'):
        from models import db, User
        user = User(username=username, email=f'{username}@teste.com',
                    tipo_usuario=tipo, nome_completo=username.title(),
                    professor_slug=slug, ativo=ativo)
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        return user

    def test_contem_paginas_fixas_publicas(self, client):
        locs = self._locs(client.get('/sitemap.xml'))

        for caminho in ('/', '/precos', '/faq', '/privacidade/',
                        '/privacidade/termos', '/contato/publico'):
            assert any(u.endswith(caminho) for u in locs), caminho

    def test_inclui_professor_ativo_com_slug(self, client):
        with client.application.app_context():
            self._criar_professor('prof_ok', 'prof-ok')

        locs = self._locs(client.get('/sitemap.xml'))

        assert any(u.endswith('/professor/pagina/prof-ok') for u in locs)

    def test_exclui_professor_inativo_sem_slug_e_nao_professor(self, client):
        with client.application.app_context():
            self._criar_professor('prof_inativo', 'prof-inativo', ativo=False)
            self._criar_professor('prof_sem_slug', None)
            self._criar_professor('aluno_com_slug', 'aluno-com-slug', tipo='aluno')

        texto = client.get('/sitemap.xml').data.decode('utf-8')

        assert 'prof-inativo' not in texto
        assert 'prof_sem_slug' not in texto
        assert 'aluno-com-slug' not in texto

    def test_nunca_lista_a_pagina_de_edicao(self, client):
        with client.application.app_context():
            self._criar_professor('prof_x', 'prof-x')

        texto = client.get('/sitemap.xml').data.decode('utf-8')

        assert '/professor/pagina/editar' not in texto

    def test_todas_as_urls_usam_o_dominio_configurado(self, client):
        client.application.config['APP_BASE_URL'] = 'https://exemplo.test/'
        try:
            with client.application.app_context():
                self._criar_professor('prof_dom', 'prof-dom')
            resp = client.get('/sitemap.xml')
        finally:
            client.application.config['APP_BASE_URL'] = None

        locs = self._locs(resp)
        assert locs
        for u in locs:
            assert u.startswith('https://exemplo.test/'), u
            assert 'railway.app' not in u
        # barra final configurada não pode gerar '//' no meio da URL
        assert not any('//' in u.replace('https://', '', 1) for u in locs)

    def test_cache_http_curto(self, client):
        resp = client.get('/sitemap.xml')

        assert 'max-age=3600' in resp.headers.get('Cache-Control', '')


class TestRobotsUsaDominioConfigurado:
    def test_sitemap_do_robots_usa_app_base_url(self, client):
        client.application.config['APP_BASE_URL'] = 'https://exemplo.test'
        try:
            texto = client.get('/robots.txt').data.decode('utf-8')
        finally:
            client.application.config['APP_BASE_URL'] = None

        assert 'Sitemap: https://exemplo.test/sitemap.xml' in texto
        assert 'railway.app' not in texto


class TestLlmsTxt:
    def test_retorna_200_texto_plano_com_links_publicos(self, client):
        resp = client.get('/llms.txt')

        assert resp.status_code == 200
        assert resp.content_type.startswith('text/plain')
        assert b'FitLog' in resp.data
        assert b'/privacidade/' in resp.data
