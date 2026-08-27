"""Acesso ao bucket de mídia dos exercícios (S3-compatível, ex: Railway
Storage Buckets), usado no lugar do volume local `/app/exercicios`.

Por quê: volumes do Railway não funcionam com múltiplas réplicas (a
própria documentação do Railway é explícita sobre isso: "Replicas
cannot be used with volumes"). Pra escalar horizontalmente, a mídia
precisa estar em algo acessível por qualquer réplica -- um bucket
S3-compatível resolve isso, já que é acessado pela rede, não pelo
disco local do container.

CONFIGURAÇÃO NECESSÁRIA (variáveis de ambiente):
  S3_ENDPOINT_URL      -- endpoint do bucket (Railway mostra isso ao
                           criar o bucket; ajuste o nome da env var
                           aqui se o Railway usar um nome diferente)
  S3_BUCKET_NAME        -- nome do bucket
  S3_ACCESS_KEY_ID       -- chave de acesso
  S3_SECRET_ACCESS_KEY   -- chave secreta
  S3_REGION (opcional)   -- região; buckets S3-compatíveis fora da AWS
                           costumam aceitar qualquer valor aqui (ex:
                           "auto"), mas o parâmetro é exigido pelo SDK

Se essas variáveis não estiverem configuradas, o serviço cai em modo
"desabilitado" (is_configured=False) -- a rota que usa isso, por sua
vez, faz fallback pro volume local, então o app não quebra numa
transição gradual (permite migrar sem downtime: sobe o código, depois
migra os arquivos, depois desliga o fallback).
"""
import os
import logging

logger = logging.getLogger(__name__)


class StorageService:
    _client = None
    _bucket_name = None
    _tried_init = False

    @classmethod
    def _get_client(cls):
        """Cria o cliente S3 (boto3) uma vez só, reaproveita depois.
        Retorna None se não configurado ou se boto3 não estiver
        instalado -- nunca levanta exceção pra não derrubar rotas que
        dependem disso."""
        if cls._tried_init:
            return cls._client

        cls._tried_init = True
        endpoint = os.getenv("S3_ENDPOINT_URL")
        bucket = os.getenv("S3_BUCKET_NAME")
        access_key = os.getenv("S3_ACCESS_KEY_ID")
        secret_key = os.getenv("S3_SECRET_ACCESS_KEY")
        region = os.getenv("S3_REGION", "auto")

        if not all([endpoint, bucket, access_key, secret_key]):
            logger.info(
                "StorageService: variáveis S3_* não configuradas -- "
                "mídia de exercícios continua servida do volume local."
            )
            return None

        try:
            import boto3
            from botocore.config import Config as BotoConfig

            cls._client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
                config=BotoConfig(signature_version="s3v4"),
            )
            cls._bucket_name = bucket
            logger.info("StorageService: cliente S3 inicializado (bucket=%s)", bucket)
        except ImportError:
            logger.warning("StorageService: boto3 não instalado -- rode pip install boto3")
        except Exception:
            logger.exception("StorageService: falha ao inicializar cliente S3")

        return cls._client

    @classmethod
    def is_configured(cls) -> bool:
        return cls._get_client() is not None

    @classmethod
    def upload_file(cls, caminho_local: str, chave: str, content_type: str = None) -> bool:
        """Sobe um arquivo local pro bucket, na chave `chave` (ex:
        "videos/0001-2gPfomN.gif"). Usado pelo script de migração."""
        client = cls._get_client()
        if client is None:
            return False
        try:
            extra_args = {"ContentType": content_type} if content_type else {}
            client.upload_file(caminho_local, cls._bucket_name, chave, ExtraArgs=extra_args)
            return True
        except Exception:
            logger.exception("StorageService: falha ao subir %s", chave)
            return False

    @classmethod
    def generate_presigned_url(cls, chave: str, expira_em_segundos: int = 3600) -> str | None:
        """Gera uma URL temporária de leitura pra chave `chave`. Usada
        pela rota /exercicios-media pra redirecionar o navegador direto
        pro bucket, sem passar pelo backend (evita gastar uma thread do
        Gunicorn e banda do próprio serviço servindo arquivo estático)."""
        client = cls._get_client()
        if client is None:
            return None
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": cls._bucket_name, "Key": chave},
                ExpiresIn=expira_em_segundos,
            )
        except Exception:
            logger.exception("StorageService: falha ao gerar URL para %s", chave)
            return None

    @classmethod
    def object_exists(cls, chave: str) -> bool:
        client = cls._get_client()
        if client is None:
            return False
        try:
            client.head_object(Bucket=cls._bucket_name, Key=chave)
            return True
        except Exception:
            return False