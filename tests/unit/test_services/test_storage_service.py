"""Testes para StorageService -- cliente S3-compatível usado pra mídia
de exercícios (Railway Buckets), ver docstring do módulo. Cobre: modo
"desabilitado" sem variáveis S3_* configuradas (fallback pro volume
local), inicialização do cliente (memoizada -- só cria uma vez),
upload, URL assinada, streaming com suporte a Range, e o caso especial
de NoSuchKey durante uma migração em andamento.

boto3 nunca é chamado de verdade -- tudo mockado.
"""
import pytest

from services.storage_service import StorageService


class _FakeS3Error(Exception):
    """Simula uma ClientError do botocore, que carrega .response com o
    código do erro (ex: NoSuchKey)."""
    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


@pytest.fixture(autouse=True)
def _resetar_estado_do_cliente():
    """StorageService memoiza o cliente em atributos de CLASSE
    (_client/_tried_init) -- sem resetar entre testes, o primeiro teste
    que inicializa (ou falha ao inicializar) contaminaria todos os
    outros."""
    StorageService._client = None
    StorageService._bucket_name = None
    StorageService._tried_init = False
    yield
    StorageService._client = None
    StorageService._bucket_name = None
    StorageService._tried_init = False


def _configurar_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.exemplo.com")
    monkeypatch.setenv("S3_BUCKET_NAME", "meu-bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "chave-fake")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "segredo-fake")


class TestGetClientEIsConfigured:

    def test_sem_variaveis_de_ambiente_fica_desabilitado(self, monkeypatch):
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)

        assert StorageService.is_configured() is False

    def test_variavel_faltando_fica_desabilitado(self, monkeypatch):
        """Todas as 4 são obrigatórias -- faltar uma só já desabilita."""
        monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.exemplo.com")
        monkeypatch.setenv("S3_BUCKET_NAME", "meu-bucket")
        monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)

        assert StorageService.is_configured() is False

    def test_com_todas_variaveis_inicializa_o_cliente(self, monkeypatch):
        _configurar_env(monkeypatch)
        chamadas = {}

        def fake_client(servico, **kwargs):
            chamadas['servico'] = servico
            chamadas['kwargs'] = kwargs
            return object()

        monkeypatch.setattr('boto3.client', fake_client)

        assert StorageService.is_configured() is True
        assert chamadas['servico'] == 's3'
        assert chamadas['kwargs']['endpoint_url'] == 'https://s3.exemplo.com'
        assert chamadas['kwargs']['aws_access_key_id'] == 'chave-fake'

    def test_cliente_e_inicializado_uma_unica_vez(self, monkeypatch):
        """Chamadas repetidas não devem recriar o cliente -- ver
        _tried_init."""
        _configurar_env(monkeypatch)
        contador = {"n": 0}

        def fake_client(servico, **kwargs):
            contador["n"] += 1
            return object()

        monkeypatch.setattr('boto3.client', fake_client)

        StorageService.is_configured()
        StorageService.is_configured()
        StorageService.upload_file('/tmp/x', 'chave')

        assert contador["n"] == 1

    def test_falha_ao_inicializar_nao_propaga_e_fica_desabilitado(self, monkeypatch):
        _configurar_env(monkeypatch)

        def fake_client(servico, **kwargs):
            raise RuntimeError("credenciais inválidas")

        monkeypatch.setattr('boto3.client', fake_client)

        assert StorageService.is_configured() is False


class TestUploadFile:

    def test_sem_cliente_configurado_retorna_false(self, monkeypatch):
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert StorageService.upload_file('/tmp/video.mp4', 'videos/x.mp4') is False

    def test_sucesso_retorna_true_e_passa_content_type(self, monkeypatch):
        _configurar_env(monkeypatch)
        capturado = {}

        class _FakeClient:
            def upload_file(self, caminho, bucket, chave, ExtraArgs=None):
                capturado.update(caminho=caminho, bucket=bucket, chave=chave, extra=ExtraArgs)

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        sucesso = StorageService.upload_file('/tmp/video.mp4', 'videos/x.mp4', content_type='video/mp4')

        assert sucesso is True
        assert capturado['bucket'] == 'meu-bucket'
        assert capturado['extra'] == {'ContentType': 'video/mp4'}

    def test_falha_no_upload_retorna_false_sem_quebrar(self, monkeypatch):
        _configurar_env(monkeypatch)

        class _FakeClient:
            def upload_file(self, *a, **kw):
                raise RuntimeError("timeout de rede")

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.upload_file('/tmp/x', 'chave') is False


class TestGeneratePresignedUrl:

    def test_sem_cliente_retorna_none(self, monkeypatch):
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert StorageService.generate_presigned_url('videos/x.mp4') is None

    def test_sucesso_retorna_url_com_expiracao_correta(self, monkeypatch):
        _configurar_env(monkeypatch)
        capturado = {}

        class _FakeClient:
            def generate_presigned_url(self, operacao, Params=None, ExpiresIn=None):
                capturado.update(operacao=operacao, params=Params, expira=ExpiresIn)
                return 'https://s3.exemplo.com/assinada'

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        url = StorageService.generate_presigned_url('videos/x.mp4', expira_em_segundos=120)

        assert url == 'https://s3.exemplo.com/assinada'
        assert capturado['operacao'] == 'get_object'
        assert capturado['expira'] == 120
        assert capturado['params'] == {'Bucket': 'meu-bucket', 'Key': 'videos/x.mp4'}

    def test_falha_retorna_none(self, monkeypatch):
        _configurar_env(monkeypatch)

        class _FakeClient:
            def generate_presigned_url(self, *a, **kw):
                raise RuntimeError("erro ao assinar")

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.generate_presigned_url('videos/x.mp4') is None


class TestGetObjectStream:

    def test_sem_cliente_retorna_none(self, monkeypatch):
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert StorageService.get_object_stream('videos/x.mp4') is None

    def test_sucesso_sem_range_monta_dict_completo(self, monkeypatch):
        _configurar_env(monkeypatch)
        corpo_fake = object()

        class _FakeClient:
            def get_object(self, **params):
                assert 'Range' not in params
                return {
                    "Body": corpo_fake, "ContentType": "video/mp4",
                    "ContentLength": 1024,
                }

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        resultado = StorageService.get_object_stream('videos/x.mp4')

        assert resultado['body'] is corpo_fake
        assert resultado['content_type'] == 'video/mp4'
        assert resultado['content_length'] == 1024
        assert resultado['is_partial'] is False

    def test_com_range_header_repassa_pro_s3_e_marca_partial(self, monkeypatch):
        _configurar_env(monkeypatch)
        capturado = {}

        class _FakeClient:
            def get_object(self, **params):
                capturado.update(params)
                return {
                    "Body": object(), "ContentType": "video/mp4",
                    "ContentLength": 512, "ContentRange": "bytes 0-511/2048",
                }

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        resultado = StorageService.get_object_stream('videos/x.mp4', range_header='bytes=0-511')

        assert capturado['Range'] == 'bytes=0-511'
        assert resultado['is_partial'] is True
        assert resultado['content_range'] == 'bytes 0-511/2048'

    def test_nosuchkey_retorna_none_silenciosamente(self, monkeypatch):
        """Esperado durante uma migração em andamento -- não é erro de
        verdade, só significa 'ainda não subiu pro bucket'."""
        _configurar_env(monkeypatch)

        class _FakeClient:
            def get_object(self, **params):
                raise _FakeS3Error("NoSuchKey")

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.get_object_stream('videos/inexistente.mp4') is None

    def test_erro_generico_tambem_retorna_none_sem_quebrar(self, monkeypatch):
        _configurar_env(monkeypatch)

        class _FakeClient:
            def get_object(self, **params):
                raise RuntimeError("falha de rede")

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.get_object_stream('videos/x.mp4') is None


class TestObjectExists:

    def test_sem_cliente_retorna_false(self, monkeypatch):
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert StorageService.object_exists('videos/x.mp4') is False

    def test_objeto_existe_retorna_true(self, monkeypatch):
        _configurar_env(monkeypatch)

        class _FakeClient:
            def head_object(self, **params):
                return {}

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.object_exists('videos/x.mp4') is True

    def test_objeto_nao_existe_retorna_false(self, monkeypatch):
        _configurar_env(monkeypatch)

        class _FakeClient:
            def head_object(self, **params):
                raise _FakeS3Error("404")

        monkeypatch.setattr('boto3.client', lambda *a, **kw: _FakeClient())

        assert StorageService.object_exists('videos/inexistente.mp4') is False
