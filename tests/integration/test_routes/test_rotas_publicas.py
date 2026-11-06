"""
Rotas PÚBLICAS (sem login) que estavam sem nenhum teste:

  GET  /auth/check-email          e   GET /auth/check-username
  GET  /contato/publico           e   POST /contato/publico/enviar

Por serem abertas à internet, o foco é: o que elas devolvem para entrada
hostil/estranha, o rate limit por IP, escape de HTML no e-mail enviado ao
admin (HTML injection) e o honeypot anti-bot. O envio de e-mail e a Groq
são sempre substituídos por stubs -- nada sai pra rede.
"""

import io
from types import SimpleNamespace

import pytest
import requests
from werkzeug.datastructures import FileStorage

import services.contato_service as contato_mod
from extensions import limiter
from models import db, User
from services.contato_service import ContatoService, MAX_AUDIO_BYTES


@pytest.fixture(autouse=True)
def _limiter_limpo():
    limiter.reset()
    yield
    limiter.reset()


def _usuario(username, email=None):
    u = User(username=username, email=email or f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u


# ------------------------------------------------------------------
# /auth/check-email e /auth/check-username
# ------------------------------------------------------------------

@pytest.mark.parametrize('rota,param', [('/auth/check-email', 'email'), ('/auth/check-username', 'username')])
class TestCheckDisponibilidade:

    def test_valor_inexistente_retorna_false(self, client, rota, param):
        resp = client.get(rota, query_string={param: 'ninguem-usa-isto'})
        assert resp.status_code == 200
        assert resp.get_json() == {'exists': False}

    @pytest.mark.parametrize('vazio', ['', '   ', '\t\n'])
    def test_vazio_ou_so_espacos_retorna_false_sem_consultar_o_banco(self, client, rota, param, vazio):
        resp = client.get(rota, query_string={param: vazio})
        assert resp.get_json() == {'exists': False}

    def test_sem_parametro_retorna_false(self, client, rota, param):
        assert client.get(rota).get_json() == {'exists': False}

    def test_nao_exige_login(self, client, rota, param):
        assert client.get(rota, query_string={param: 'x'}).status_code == 200

    def test_so_aceita_get(self, client, rota, param):
        assert client.post(rota, data={param: 'x'}).status_code == 405

    def test_tentativa_de_sql_injection_e_tratada_como_texto(self, client, rota, param, app):
        _usuario('real')
        resp = client.get(rota, query_string={param: "' OR '1'='1"})
        assert resp.status_code == 200
        assert resp.get_json() == {'exists': False}

    def test_limite_de_10_consultas_por_minuto_por_ip(self, client, rota, param):
        codigos = [client.get(rota, query_string={param: f'v{i}'}).status_code for i in range(11)]
        assert codigos[:10] == [200] * 10
        assert codigos[10] == 429


class TestCheckEmail:

    def test_email_cadastrado_retorna_true(self, client, app):
        _usuario('maria', 'maria@teste.com')
        assert client.get('/auth/check-email', query_string={'email': 'maria@teste.com'}).get_json() == {'exists': True}

    def test_espacos_nas_pontas_sao_ignorados(self, client, app):
        _usuario('joao', 'joao@teste.com')
        assert client.get('/auth/check-email', query_string={'email': '  joao@teste.com  '}).get_json() == {'exists': True}

    def test_so_existe_se_for_exatamente_o_mesmo_email(self, client, app):
        _usuario('ana', 'ana@teste.com')
        assert client.get('/auth/check-email', query_string={'email': 'ana@teste.com.br'}).get_json() == {'exists': False}
        assert client.get('/auth/check-email', query_string={'email': 'ana'}).get_json() == {'exists': False}

    def test_nao_vaza_nenhum_dado_alem_de_exists(self, client, app):
        _usuario('bia', 'bia@teste.com')
        assert set(client.get('/auth/check-email', query_string={'email': 'bia@teste.com'}).get_json()) == {'exists'}


class TestCheckUsername:

    def test_usuario_cadastrado_retorna_true(self, client, app):
        _usuario('carlos')
        assert client.get('/auth/check-username', query_string={'username': 'carlos'}).get_json() == {'exists': True}

    def test_espacos_nas_pontas_sao_ignorados(self, client, app):
        _usuario('duda')
        assert client.get('/auth/check-username', query_string={'username': ' duda '}).get_json() == {'exists': True}

    def test_prefixo_nao_conta_como_existente(self, client, app):
        _usuario('eduardo')
        assert client.get('/auth/check-username', query_string={'username': 'edu'}).get_json() == {'exists': False}


# ------------------------------------------------------------------
# /contato/publico (página) e /contato/publico/enviar (POST)
# ------------------------------------------------------------------

@pytest.fixture
def emails(monkeypatch):
    """Substitui o envio real e registra cada e-mail 'enviado'."""
    enviados = []

    def _fake(destinatario, assunto, corpo_texto, corpo_html=None):
        enviados.append({'para': destinatario, 'assunto': assunto, 'texto': corpo_texto, 'html': corpo_html})
        return True

    monkeypatch.setattr(contato_mod, 'enviar_email', _fake)
    return enviados


VALIDO = {'nome': 'Fulano de Tal', 'email': 'fulano@exemplo.com', 'mensagem': 'Quero saber mais sobre os planos.'}


def _enviar(client, **campos):
    return client.post('/contato/publico/enviar', json={**VALIDO, **campos})


class TestPaginaContatoPublico:

    def test_renderiza_sem_login(self, client):
        resp = client.get('/contato/publico')
        assert resp.status_code == 200
        assert 'empresa_website' in resp.get_data(as_text=True)       # campo-isca do honeypot


class TestEnviarContatoPublico:

    def test_envia_para_o_admin_com_os_dados_do_visitante(self, client, app, emails):
        resp = _enviar(client)

        assert resp.status_code == 200
        assert resp.get_json() == {'ok': True, 'erro': None}
        assert len(emails) == 1
        assert emails[0]['para'] == 'admin@localhost'              # admin semeado pelo create_app
        assert 'Fulano de Tal' in emails[0]['assunto']
        assert 'fulano@exemplo.com' in emails[0]['texto']
        assert 'Quero saber mais sobre os planos.' in emails[0]['texto']

    def test_envia_uma_copia_para_cada_admin(self, client, app, emails):
        extra = _usuario('admin2', 'admin2@teste.com')
        extra.is_admin = True
        db.session.commit()

        _enviar(client)

        assert {e['para'] for e in emails} == {'admin@localhost', 'admin2@teste.com'}

    def test_sem_admin_cai_no_ADMIN_EMAIL_configurado(self, client, app, emails):
        User.query.delete()
        db.session.commit()
        app.config['ADMIN_EMAIL'] = 'fallback@fitlog.com'

        resp = _enviar(client)

        assert resp.status_code == 200
        assert [e['para'] for e in emails] == ['fallback@fitlog.com']

    def test_sem_nenhum_destinatario_recusa_em_vez_de_fingir_sucesso(self, client, app, emails):
        User.query.delete()
        db.session.commit()
        app.config['ADMIN_EMAIL'] = None

        resp = _enviar(client)

        assert resp.status_code == 400
        assert 'Não foi possível enviar' in resp.get_json()['erro']
        assert emails == []

    def test_falha_de_envio_nao_vira_erro_para_o_visitante(self, client, app, monkeypatch):
        """Sem RESEND_API_KEY (dev) enviar_email só loga e devolve False."""
        monkeypatch.setattr(contato_mod, 'enviar_email', lambda *a, **k: False)
        assert _enviar(client).status_code == 200

    # ---------------- honeypot ----------------

    def test_honeypot_preenchido_finge_sucesso_mas_nao_envia_nada(self, client, app, emails):
        resp = _enviar(client, empresa_website='http://spam.example')

        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True            # não dá pista ao robô
        assert emails == []

    def test_honeypot_vazio_nao_bloqueia_visitante_real(self, client, app, emails):
        assert _enviar(client, empresa_website='').status_code == 200
        assert len(emails) == 1

    # ---------------- validação ----------------

    @pytest.mark.parametrize('nome', ['', '   ', None, 'n' * 121])
    def test_nome_ausente_ou_longo_demais_e_recusado(self, client, app, emails, nome):
        resp = _enviar(client, nome=nome)

        assert resp.status_code == 400
        assert resp.get_json() == {'ok': False, 'erro': 'Informe seu nome.'}
        assert emails == []

    def test_nome_com_exatamente_120_caracteres_e_aceito(self, client, app, emails):
        assert _enviar(client, nome='n' * 120).status_code == 200

    @pytest.mark.parametrize('email', ['', '   ', None])
    def test_email_ausente_e_recusado(self, client, app, emails, email):
        resp = _enviar(client, email=email)

        assert resp.status_code == 400
        assert 'e-mail válido' in resp.get_json()['erro']
        assert emails == []

    @pytest.mark.parametrize('invalido', ['abc', 'sem-arroba.com', '@@@', 'a@b', 'a b@c.com'])
    def test_email_com_formato_invalido_e_recusado(self, client, app, emails, invalido):
        resp = _enviar(client, email=invalido)

        assert resp.status_code == 400
        assert emails == []

    @pytest.mark.parametrize('mensagem', ['', '   ', None])
    def test_mensagem_vazia_e_recusada(self, client, app, emails, mensagem):
        resp = _enviar(client, mensagem=mensagem)

        assert resp.status_code == 400
        assert 'Escreva sua mensagem' in resp.get_json()['erro']

    def test_mensagem_acima_de_4000_caracteres_e_recusada(self, client, app, emails):
        resp = _enviar(client, mensagem='m' * 4001)

        assert resp.status_code == 400
        assert 'muito longa' in resp.get_json()['erro']
        assert emails == []

    def test_mensagem_com_exatamente_4000_caracteres_e_aceita(self, client, app, emails):
        assert _enviar(client, mensagem='m' * 4000).status_code == 200

    def test_corpo_ausente_ou_nao_json_e_tratado_como_campos_vazios(self, client, app, emails):
        assert client.post('/contato/publico/enviar').status_code == 400
        assert client.post('/contato/publico/enviar', data='isto não é json',
                           content_type='application/json').status_code == 400
        assert emails == []

    def test_so_aceita_post(self, client):
        assert client.get('/contato/publico/enviar').status_code == 405

    # ---------------- segurança ----------------

    def test_html_do_visitante_e_escapado_no_email_ao_admin(self, client, app, emails):
        """HTML injection: nome/e-mail/mensagem viram texto no corpo HTML."""
        _enviar(client,
                nome='<script>alert(1)</script>',
                mensagem='<img src=x onerror=alert(2)> & "aspas"')

        html = emails[0]['html']
        assert '<script>' not in html and '<img' not in html
        assert '&lt;script&gt;' in html
        assert '&lt;img src=x onerror=alert(2)&gt;' in html
        assert '&amp;' in html

    def test_corpo_texto_leva_a_mensagem_original_sem_escape(self, client, app, emails):
        _enviar(client, mensagem='5 < 6 & 7 > 3')
        assert '5 < 6 & 7 > 3' in emails[0]['texto']

    def test_limite_de_5_envios_por_hora_por_ip(self, client, app, emails):
        codigos = [_enviar(client).status_code for _ in range(6)]

        assert codigos[:5] == [200] * 5
        assert codigos[5] == 429
        assert len(emails) == 5


# ------------------------------------------------------------------
# ContatoService.transcrever_audio (Groq mockada) + rota /contato/transcrever
# ------------------------------------------------------------------

def _audio(conteudo=b'RIFFfake-audio', nome='fala.webm', tipo='audio/webm'):
    return FileStorage(stream=io.BytesIO(conteudo), filename=nome, content_type=tipo)


@pytest.fixture
def groq(app, monkeypatch):
    app.config['GROQ_API_KEY'] = 'chave-groq-teste'
    estado = SimpleNamespace(chamadas=[], resposta=None, erro=None)

    class _Resp:
        def __init__(self, dados):
            self._d = dados

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    def _post(url, headers=None, files=None, data=None, timeout=None):
        estado.chamadas.append({'url': url, 'headers': headers, 'files': files, 'data': data, 'timeout': timeout})
        if estado.erro:
            raise estado.erro
        return _Resp(estado.resposta if estado.resposta is not None else {'text': 'olá mundo'})

    monkeypatch.setattr(contato_mod.requests, 'post', _post)
    return estado


class TestTranscreverAudio:

    def test_sem_chave_da_groq_retorna_indisponivel_sem_chamar_a_rede(self, app, groq):
        app.config['GROQ_API_KEY'] = None

        r = ContatoService.transcrever_audio(_audio())

        assert r['ok'] is False and 'indisponível' in r['texto']
        assert groq.chamadas == []

    def test_audio_vazio(self, app, groq):
        r = ContatoService.transcrever_audio(_audio(b''))
        assert r['ok'] is False and 'vazio' in r['texto']
        assert groq.chamadas == []

    def test_audio_acima_do_limite_e_recusado_antes_de_enviar(self, app, groq):
        r = ContatoService.transcrever_audio(_audio(b'x' * (MAX_AUDIO_BYTES + 1)))
        assert r['ok'] is False and 'muito longo' in r['texto']
        assert groq.chamadas == []

    def test_audio_no_limite_exato_e_aceito(self, app, groq):
        assert ContatoService.transcrever_audio(_audio(b'x' * MAX_AUDIO_BYTES))['ok'] is True

    def test_sucesso_devolve_o_texto_sem_espacos_nas_pontas(self, app, groq):
        groq.resposta = {'text': '  quero reportar um erro  '}
        assert ContatoService.transcrever_audio(_audio()) == {'ok': True, 'texto': 'quero reportar um erro'}

    def test_envia_chave_modelo_idioma_e_timeout_corretos(self, app, groq):
        ContatoService.transcrever_audio(_audio())

        c = groq.chamadas[0]
        assert c['headers'] == {'Authorization': 'Bearer chave-groq-teste'}
        assert c['data'] == {'model': 'whisper-large-v3-turbo', 'language': 'pt', 'response_format': 'json'}
        assert c['timeout'] == contato_mod.TIMEOUT
        assert c['files']['file'][0] == 'fala.webm'
        assert c['files']['file'][2] == 'audio/webm'

    def test_modelo_configuravel_pelo_app(self, app, groq):
        app.config['GROQ_WHISPER_MODEL'] = 'whisper-outro'
        ContatoService.transcrever_audio(_audio())
        assert groq.chamadas[0]['data']['model'] == 'whisper-outro'

    def test_arquivo_sem_nome_nem_tipo_usa_padroes(self, app, groq):
        ContatoService.transcrever_audio(FileStorage(stream=io.BytesIO(b'abc'), filename=None, content_type=None))
        assert groq.chamadas[0]['files']['file'][0] == 'audio.webm'
        assert groq.chamadas[0]['files']['file'][2] == 'audio/webm'

    @pytest.mark.parametrize('resposta', [{'text': ''}, {'text': '   '}, {'text': None}, {}])
    def test_transcricao_vazia_pede_para_tentar_de_novo(self, app, groq, resposta):
        groq.resposta = resposta
        r = ContatoService.transcrever_audio(_audio())
        assert r['ok'] is False and 'entender' in r['texto']

    def test_timeout_tem_mensagem_propria(self, app, groq):
        groq.erro = requests.exceptions.Timeout('lento')
        r = ContatoService.transcrever_audio(_audio())
        assert r['ok'] is False and 'demorou demais' in r['texto']

    @pytest.mark.parametrize('erro', [
        requests.exceptions.ConnectionError('sem rede'),
        requests.exceptions.HTTPError('500'),
        RuntimeError('qualquer coisa'),
    ])
    def test_outras_falhas_viram_mensagem_amigavel_sem_vazar_detalhe(self, app, groq, erro):
        groq.erro = erro
        r = ContatoService.transcrever_audio(_audio())
        assert r['ok'] is False
        assert 'Não foi possível transcrever' in r['texto']
        assert str(erro) not in r['texto']


class TestRotaTranscrever:

    def test_sucesso_retorna_200_e_o_texto(self, auth_client, monkeypatch):
        monkeypatch.setattr(ContatoService, 'transcrever_audio',
                            staticmethod(lambda arq: {'ok': True, 'texto': 'transcrito'}))

        resp = auth_client.post('/contato/transcrever', data={'audio': (io.BytesIO(b'abc'), 'a.webm')},
                                content_type='multipart/form-data')

        assert resp.status_code == 200
        assert resp.get_json() == {'ok': True, 'texto': 'transcrito'}

    def test_falha_do_servico_retorna_503(self, auth_client, monkeypatch):
        monkeypatch.setattr(ContatoService, 'transcrever_audio',
                            staticmethod(lambda arq: {'ok': False, 'texto': 'indisponível'}))

        resp = auth_client.post('/contato/transcrever', data={'audio': (io.BytesIO(b'abc'), 'a.webm')},
                                content_type='multipart/form-data')

        assert resp.status_code == 503
