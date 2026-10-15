#!/usr/bin/env python3
"""Baixa uma cópia de segurança de TODO o bucket de mídia para uma pasta local.

SOMENTE LEITURA em relação ao bucket: só lista e baixa (ListObjects/GetObject).
Não envia, não apaga e não altera nada nele.

RODE NO SEU COMPUTADOR (não no Console do Railway: o disco do container é
apagado a cada deploy e você não conseguiria levar os arquivos de lá).

Variáveis de ambiente (as mesmas do app, copie do serviço fitlog > Variables):
    S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
    e, se existir, S3_REGION

USO
    pip install boto3
    python3 scripts/backup_bucket.py                      # baixa tudo
    python3 scripts/backup_bucket.py --somente-listar     # só mostra quantos arquivos e MB
    python3 scripts/backup_bucket.py --prefixo videos/    # só uma pasta do bucket
    python3 scripts/backup_bucket.py --destino D:\\backup  # escolher a pasta

É RETOMÁVEL: rodar de novo pula o que já foi baixado (mesmo tamanho) e baixa só
o que falta. Ao final confere o tamanho de cada arquivo local contra o bucket,
grava MANIFESTO.csv e sai com código 1 se algo falhou.
"""
import argparse
import csv
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path


def listar(client, bucket, prefixo=''):
    """Todos os objetos (paginado): [{'Key','Size','ETag','LastModified'}]."""
    objetos = []
    for pagina in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefixo):
        objetos.extend(pagina.get('Contents', []))
    return objetos


def destino_seguro(raiz, chave):
    """Caminho local para a chave, ou None se a chave tentar sair da pasta de
    destino (barra inicial, '..', contra-barra) -- nunca gravamos fora dela."""
    if not chave or chave.startswith('/') or '\\' in chave or '..' in chave.split('/') or chave.endswith('/'):
        return None
    alvo = (Path(raiz) / chave).resolve()
    return alvo if Path(raiz).resolve() in alvo.parents else None


def baixar_um(client, bucket, obj, raiz, tentativas=3):
    """('baixado'|'ja-existia'|'ignorado'|'falhou', detalhe)."""
    chave, tamanho = obj['Key'], obj['Size']
    alvo = destino_seguro(raiz, chave)
    if alvo is None:
        return 'ignorado', 'chave com formato inseguro'
    if alvo.is_file() and alvo.stat().st_size == tamanho:
        return 'ja-existia', ''
    parcial = alvo.with_name(alvo.name + '.parcial')
    ultimo = ''
    for tentativa in range(tentativas):
        try:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, chave, str(parcial))
            if parcial.stat().st_size != tamanho:
                raise IOError(f'tamanho {parcial.stat().st_size} != esperado {tamanho}')
            os.replace(parcial, alvo)
            return 'baixado', ''
        except Exception as e:
            ultimo = f'{type(e).__name__}: {e}'
            time.sleep(1.5 * (tentativa + 1))
    if parcial.exists():
        parcial.unlink()
    return 'falhou', ultimo


def verificar(objetos, raiz):
    """Confere cada arquivo local contra o bucket: [(chave, situacao)]."""
    resultado = []
    for obj in objetos:
        alvo = destino_seguro(raiz, obj['Key'])
        if alvo is None:
            resultado.append((obj['Key'], 'ignorado'))
        elif not alvo.is_file():
            resultado.append((obj['Key'], 'ausente'))
        elif alvo.stat().st_size != obj['Size']:
            resultado.append((obj['Key'], 'tamanho-diferente'))
        else:
            resultado.append((obj['Key'], 'ok'))
    return resultado


def _cliente_s3():
    faltam = [v for v in ('S3_ENDPOINT_URL', 'S3_BUCKET_NAME', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY')
              if not os.getenv(v)]
    if faltam:
        sys.exit('Faltam variáveis de ambiente: ' + ', '.join(faltam))
    import boto3
    from botocore.config import Config
    cliente = boto3.client(
        's3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
        aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
        region_name=os.getenv('S3_REGION', 'auto'), config=Config(signature_version='s3v4'))
    return cliente, os.environ['S3_BUCKET_NAME']


def main(argv=None, cliente=None, bucket=None):
    p = argparse.ArgumentParser(description='Cópia de segurança do bucket de mídia (somente leitura).')
    p.add_argument('--destino', default=f'backup_bucket_{date.today().isoformat()}')
    p.add_argument('--prefixo', default='', help='baixar só esta pasta do bucket, ex.: videos/')
    p.add_argument('--simultaneos', type=int, default=4)
    p.add_argument('--somente-listar', action='store_true')
    a = p.parse_args(argv)

    if cliente is None:
        cliente, bucket = _cliente_s3()
    objetos = [o for o in listar(cliente, bucket, a.prefixo) if not o['Key'].endswith('/')]
    total_mb = sum(o['Size'] for o in objetos) / 1024 / 1024
    por_pasta = Counter(o['Key'].split('/')[0] for o in objetos)
    print(f'Bucket "{bucket}": {len(objetos)} objetos, {total_mb:.1f} MB  {dict(por_pasta)}')
    if a.somente_listar:
        return 0

    Path(a.destino).mkdir(parents=True, exist_ok=True)
    print(f'Baixando para: {Path(a.destino).resolve()}')
    contagem, falhas = Counter(), []
    with ThreadPoolExecutor(max_workers=max(1, a.simultaneos)) as pool:
        resultados = pool.map(lambda o: baixar_um(cliente, bucket, o, a.destino), objetos)
        for i, (obj, (situacao, detalhe)) in enumerate(zip(objetos, resultados), 1):
            contagem[situacao] += 1
            if situacao in ('falhou', 'ignorado'):
                falhas.append((obj['Key'], situacao, detalhe))
            if i % 200 == 0:
                print(f'  ... {i}/{len(objetos)}', flush=True)

    conferencia = dict(verificar(objetos, a.destino))
    manifesto = Path(a.destino) / 'MANIFESTO.csv'
    with open(manifesto, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['chave', 'tamanho', 'etag', 'modificado_em', 'conferencia'])
        for o in objetos:
            w.writerow([o['Key'], o['Size'], str(o.get('ETag', '')).strip('"'),
                        o.get('LastModified', ''), conferencia[o['Key']]])

    ruins = {k: v for k, v in conferencia.items() if v != 'ok'}
    print('\nRESULTADO: ' + ' | '.join(f'{k}: {v}' for k, v in sorted(contagem.items()))
          + f' | conferidos ok: {len(objetos) - len(ruins)}/{len(objetos)}')
    for chave, situacao, detalhe in falhas[:30]:
        print(f'  [{situacao}] {chave} ({detalhe})')
    for chave, situacao in list(ruins.items())[:30]:
        print(f'  [conferência: {situacao}] {chave}')
    print(f'Manifesto: {manifesto}')
    if ruins or falhas:
        print('\nATENÇÃO: o backup NÃO está completo. Rode o comando de novo (ele só baixa o que falta).')
        return 1
    print('\nBackup completo e conferido (tamanho de todos os arquivos bate com o bucket).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
