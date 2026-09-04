"""Testes para o roteamento/fallback entre provedores de IA do FitBot
(services/fitbot_service.py): retry com backoff em erro transitório,
fallback Groq -> OpenAI e Gemini -> OpenAI quando o provedor principal
falha, tratamento de rate limit (429, sem retry/reserva/alerta) e o
alerta por e-mail aos admins (debounced).

Este é o código de "caminho infeliz" do FitBot -- os testes existentes
em test_fitbot_service.py cobrem o caminho feliz (contexto + resposta
normal do Groq); aqui o foco é tudo que acontece quando um provedor
falha.
"""
import requests

from extensions import cache
from models import db, User
from services import fitbot_service as svc
from services.fitbot_service import (
    FitBotService,
    MENSAGEM_ERRO_GENERICO,
    MENSAGEM_INDISPONIVEL,
    MENSAGEM_LIMITE_ATINGIDO,
    _alertar_falha_provedor,
    _chamar_openai_reserva,
    _post_llm_com_retry,
)


class _RespostaFake:
    def __init__(self, status_code, corpo=None, texto=""):
        self.status_code = status_code
        self._corpo = corpo or {}
        self.text = texto or str(corpo)

    def json(self):
        return self._corpo


def _resposta_groq_ok(texto="Resposta do Groq"):
    return _RespostaFake(200, {"choices": [{"message": {"content": texto}}]})


def _resposta_gemini_ok(texto="Resposta do Gemini"):
    return _RespostaFake(200, {"candidates": [{"content": {"parts": [{"text": texto}]}}]})


def _resposta_openai_ok(texto="Resposta da reserva"):
    return _RespostaFake(200, {"choices": [{"message": {"content": texto}}]})


# ------------------------------------------------------------------
# _post_llm_com_retry -- retry/backoff genérico usado por Groq/Gemini/OpenAI
# ------------------------------------------------------------------
class TestPostLlmComRetry:

    def test_sucesso_de_primeira_nao_tenta_de_novo(self, app, monkeypatch):
        chamadas = []

        def fake_post(url, **kwargs):
            chamadas.append(1)
            return _RespostaFake(200)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            resp = _post_llm_com_retry('http://fake')
        assert resp.status_code == 200
        assert len(chamadas) == 1

    def test_status_nao_retryavel_nao_tenta_de_novo(self, app, monkeypatch):
        """400/401/404/model_not_found não valem retry -- não se
        resolvem tentando de novo (ver STATUS_RETRYAVEIS)."""
        chamadas = []

        def fake_post(url, **kwargs):
            chamadas.append(1)
            return _RespostaFake(400)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            resp = _post_llm_com_retry('http://fake')
        assert resp.status_code == 400
        assert len(chamadas) == 1

    def test_502_tenta_de_novo_e_sucede_na_segunda(self, app, monkeypatch):
        respostas = [_RespostaFake(502), _RespostaFake(200)]

        def fake_post(url, **kwargs):
            return respostas.pop(0)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)  # não espera de verdade no teste

        with app.app_context():
            resp = _post_llm_com_retry('http://fake')
        assert resp.status_code == 200

    def test_esgota_tentativas_e_devolve_o_ultimo_erro(self, app, monkeypatch):
        def fake_post(url, **kwargs):
            return _RespostaFake(503)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)

        with app.app_context():
            resp = _post_llm_com_retry('http://fake')
        # MAX_RETRIES_LLM=1 -> 2 tentativas no total, ambas 503
        assert resp.status_code == 503

    def test_erro_de_rede_tenta_de_novo_e_sucede(self, app, monkeypatch):
        chamadas = {"n": 0}

        def fake_post(url, **kwargs):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise requests.exceptions.ConnectionError("falha simulada")
            return _RespostaFake(200)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)

        with app.app_context():
            resp = _post_llm_com_retry('http://fake')
        assert resp.status_code == 200
        assert chamadas["n"] == 2

    def test_erro_de_rede_em_todas_as_tentativas_propaga_excecao(self, app, monkeypatch):
        def fake_post(url, **kwargs):
            raise requests.exceptions.Timeout("timeout simulado")

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)

        with app.app_context():
            try:
                _post_llm_com_retry('http://fake')
                assert False, "deveria ter levantado a exceção"
            except requests.exceptions.Timeout:
                pass


# ------------------------------------------------------------------
# _chamar_groq -- provedor principal de texto
# ------------------------------------------------------------------
class TestChamarGroq:

    def test_sem_api_key_nao_aciona_reserva(self, app):
        app.config['GROQ_API_KEY'] = None
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is False
        assert resultado['resposta'] == MENSAGEM_INDISPONIVEL

    def test_sucesso(self, app, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _resposta_groq_ok("Oi!"))
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado == {"ok": True, "resposta": "Oi!", "modo": "texto"}

    def test_rate_limit_429_nao_aciona_reserva(self, app, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(429))
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is False
        assert resultado['resposta'] == MENSAGEM_LIMITE_ATINGIDO

    def test_erro_5xx_aciona_reserva(self, app, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(500, texto="erro interno"))
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is True
        assert resultado['resposta'] == MENSAGEM_ERRO_GENERICO

    def test_falha_de_rede_aciona_reserva(self, app, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        monkeypatch.setattr(svc.time, 'sleep', lambda s: None)

        def fake_post(url, **kw):
            raise requests.exceptions.ConnectionError("sem rede")

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado['aciona_reserva'] is True
        assert 'falha de rede' in resultado['detalhe']

    def test_resposta_mal_formada_aciona_reserva(self, app, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(200, {"algo": "inesperado"}))
        with app.app_context():
            resultado = FitBotService._chamar_groq([{"role": "user", "content": "oi"}])
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is True


# ------------------------------------------------------------------
# _chamar_gemini -- provedor principal de imagem
# ------------------------------------------------------------------
class TestChamarGemini:

    def test_sem_api_key_nao_aciona_reserva(self, app):
        app.config['GEMINI_API_KEY'] = None
        with app.app_context():
            resultado = FitBotService._chamar_gemini("oi", "aW1hZ2Vt")
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is False

    def test_sucesso(self, app, monkeypatch):
        app.config['GEMINI_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _resposta_gemini_ok("Vejo um halter"))
        with app.app_context():
            resultado = FitBotService._chamar_gemini("o que é isso?", "aW1hZ2Vt")
        assert resultado == {"ok": True, "resposta": "Vejo um halter", "modo": "imagem"}

    def test_rate_limit_429_nao_aciona_reserva(self, app, monkeypatch):
        app.config['GEMINI_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(429))
        with app.app_context():
            resultado = FitBotService._chamar_gemini("oi", "aW1hZ2Vt")
        assert resultado['aciona_reserva'] is False
        assert resultado['resposta'] == MENSAGEM_LIMITE_ATINGIDO

    def test_resposta_vazia_aciona_reserva(self, app, monkeypatch):
        app.config['GEMINI_API_KEY'] = 'fake'
        resp_vazia = _RespostaFake(200, {"candidates": [{"content": {"parts": [{"text": ""}]}}]})
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: resp_vazia)
        with app.app_context():
            resultado = FitBotService._chamar_gemini("oi", "aW1hZ2Vt")
        assert resultado['ok'] is False
        assert resultado['aciona_reserva'] is True


# ------------------------------------------------------------------
# _chamar_openai_reserva -- reserva única (texto e imagem)
# ------------------------------------------------------------------
class TestChamarOpenaiReserva:

    def test_sem_api_key_retorna_false_none(self, app):
        app.config['OPENAI_API_KEY'] = None
        with app.app_context():
            ok, texto = _chamar_openai_reserva("system", [{"role": "user", "content": "oi"}])
        assert (ok, texto) == (False, None)

    def test_sucesso_texto(self, app, monkeypatch):
        app.config['OPENAI_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _resposta_openai_ok("Claro, posso ajudar"))
        with app.app_context():
            ok, texto = _chamar_openai_reserva("system", [{"role": "user", "content": "oi"}])
        assert ok is True
        assert texto == "Claro, posso ajudar"

    def test_sucesso_com_imagem_substitui_ultima_mensagem_do_usuario(self, app, monkeypatch):
        app.config['OPENAI_API_KEY'] = 'fake'
        capturado = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            capturado['payload'] = json
            return _resposta_openai_ok("Vejo uma barra")

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            ok, texto = _chamar_openai_reserva(
                "system", [{"role": "user", "content": "o que é isso?"}],
                imagem_base64="aW1hZ2Vt",
            )
        assert ok is True
        ultima_msg = capturado['payload']['messages'][-1]
        assert ultima_msg['role'] == 'user'
        # conteúdo vira uma lista [texto, imagem] quando tem imagem
        tipos = [c['type'] for c in ultima_msg['content']]
        assert tipos == ['text', 'image_url']

    def test_falha_retorna_false_none_sem_quebrar(self, app, monkeypatch):
        app.config['OPENAI_API_KEY'] = 'fake'
        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(500, texto="erro"))
        with app.app_context():
            ok, texto = _chamar_openai_reserva("system", [{"role": "user", "content": "oi"}])
        assert (ok, texto) == (False, None)

    def test_falha_de_rede_retorna_false_none(self, app, monkeypatch):
        app.config['OPENAI_API_KEY'] = 'fake'

        def fake_post(url, **kw):
            raise requests.exceptions.Timeout("timeout")

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            ok, texto = _chamar_openai_reserva("system", [{"role": "user", "content": "oi"}])
        assert (ok, texto) == (False, None)


# ------------------------------------------------------------------
# _alertar_falha_provedor -- e-mail aos admins, debounced
# ------------------------------------------------------------------
class TestAlertarFalhaProvedor:

    def _criar_admin(self, username='admin_alerta'):
        admin = User(username=username, email=f'{username}@teste.com', is_admin=True)
        admin.set_password('SenhaForte123!')
        db.session.add(admin)
        db.session.commit()
        return admin

    def test_envia_email_para_admins(self, app, db, monkeypatch):
        self._criar_admin('admin_alerta')
        enviados = []
        monkeypatch.setattr(svc, 'enviar_email', lambda dest, assunto, corpo: enviados.append((dest, assunto)))

        with app.app_context():
            _alertar_falha_provedor("Groq", "HTTP 500", usou_reserva=True)

        # também existe o admin (dev) semeado no fixture da app -- o
        # importante é que o admin criado neste teste recebeu, uma vez.
        destinatarios = [d for d, _ in enviados]
        assert destinatarios.count('admin_alerta@teste.com') == 1
        assert all('Groq' in assunto for _, assunto in enviados)

    def test_debounce_nao_envia_duas_vezes_seguidas(self, app, db, monkeypatch):
        self._criar_admin('admin_debounce')
        enviados = []
        monkeypatch.setattr(svc, 'enviar_email', lambda dest, assunto, corpo: enviados.append(dest))

        with app.app_context():
            _alertar_falha_provedor("Gemini", "HTTP 500", usou_reserva=True)
            _alertar_falha_provedor("Gemini", "HTTP 500 de novo", usou_reserva=True)

        # a 2ª chamada (mesmo provedor, dentro da janela de debounce)
        # não deve gerar um novo envio -- cada admin aparece só 1 vez.
        assert enviados.count('admin_debounce@teste.com') == 1

    def test_sem_admin_e_sem_admin_email_nao_quebra(self, app, db, monkeypatch):
        # força "nenhum destinatário" mesmo com o admin (dev) semeado
        # pelo fixture da app -- o que este teste quer cobrir é
        # especificamente o branch "sem ninguém pra avisar".
        monkeypatch.setattr(svc, '_emails_administradores', lambda: [])
        monkeypatch.setattr(svc, 'enviar_email', lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("não deveria tentar enviar e-mail")
        ))
        with app.app_context():
            # não deve levantar exceção nenhuma
            _alertar_falha_provedor("Groq", "detalhe", usou_reserva=False)

    def test_erro_ao_enviar_nunca_propaga(self, app, db, monkeypatch):
        self._criar_admin('admin_erro_envio')

        def _explode(*a, **kw):
            raise RuntimeError("SMTP fora do ar")

        monkeypatch.setattr(svc, 'enviar_email', _explode)
        with app.app_context():
            # best-effort -- nunca pode derrubar o fluxo do FitBot
            _alertar_falha_provedor("Groq", "detalhe", usou_reserva=False)


# ------------------------------------------------------------------
# Fluxo completo: _responder_com_texto / _responder_com_imagem
# com fallback de ponta a ponta
# ------------------------------------------------------------------
class TestFallbackDePontaAPonta:

    def test_groq_falha_reserva_salva_a_resposta(self, app, db, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        app.config['OPENAI_API_KEY'] = 'fake'

        respostas = {
            svc.GROQ_ENDPOINT: _RespostaFake(500, texto="groq caiu"),
            svc.OPENAI_ENDPOINT: _resposta_openai_ok("Resposta da reserva salvando o dia"),
        }

        def fake_post(url, **kw):
            return respostas[url]

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc, 'enviar_email', lambda *a, **kw: None)

        with app.app_context():
            resultado = FitBotService._responder_com_texto("oi", historico=[])

        assert resultado['ok'] is True
        assert resultado['resposta'] == "Resposta da reserva salvando o dia"

    def test_groq_e_reserva_falham_retorna_erro_do_groq(self, app, db, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        app.config['OPENAI_API_KEY'] = 'fake'

        monkeypatch.setattr(svc._SESSION, 'post', lambda url, **kw: _RespostaFake(500, texto="tudo caiu"))
        monkeypatch.setattr(svc, 'enviar_email', lambda *a, **kw: None)

        with app.app_context():
            resultado = FitBotService._responder_com_texto("oi", historico=[])

        assert resultado['ok'] is False
        assert resultado['resposta'] == MENSAGEM_ERRO_GENERICO

    def test_rate_limit_do_groq_nao_tenta_reserva(self, app, db, monkeypatch):
        app.config['GROQ_API_KEY'] = 'fake'
        app.config['OPENAI_API_KEY'] = 'fake'

        chamou_openai = {"sim": False}

        def fake_post(url, **kw):
            if url == svc.OPENAI_ENDPOINT:
                chamou_openai["sim"] = True
                return _resposta_openai_ok()
            return _RespostaFake(429)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)

        with app.app_context():
            resultado = FitBotService._responder_com_texto("oi", historico=[])

        assert resultado['ok'] is False
        assert resultado['resposta'] == MENSAGEM_LIMITE_ATINGIDO
        assert chamou_openai["sim"] is False

    def test_imagem_invalida_nao_chama_provedor_nenhum(self, app, db, monkeypatch):
        chamou = {"sim": False}

        def fake_post(url, **kw):
            chamou["sim"] = True
            return _RespostaFake(200)

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        with app.app_context():
            resultado = FitBotService._responder_com_imagem("o que é isso?", "não-é-base64-válido!!")

        assert resultado['ok'] is False
        assert resultado['modo'] == 'imagem'
        assert chamou["sim"] is False

    def test_gemini_falha_reserva_salva_a_resposta_da_imagem(self, app, db, monkeypatch):
        app.config['GEMINI_API_KEY'] = 'fake'
        app.config['OPENAI_API_KEY'] = 'fake'

        def fake_post(url, **kw):
            if url == svc.OPENAI_ENDPOINT:
                return _resposta_openai_ok("É um halter de 10kg")
            return _RespostaFake(500, texto="gemini caiu")

        monkeypatch.setattr(svc._SESSION, 'post', fake_post)
        monkeypatch.setattr(svc, 'enviar_email', lambda *a, **kw: None)

        with app.app_context():
            # base64 válido de "imagem" (só precisa decodificar, não
            # precisa ser um JPEG de verdade -- ver base64.b64decode)
            resultado = FitBotService._responder_com_imagem("o que é isso?", "aW1hZ2Vt")

        assert resultado['ok'] is True
        assert resultado['resposta'] == "É um halter de 10kg"
        assert resultado['modo'] == 'imagem'
