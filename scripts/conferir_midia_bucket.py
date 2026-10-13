#!/usr/bin/env python3
"""Confere se o GIF de cada exercício existe de fato no bucket.

SOMENTE LEITURA: não envia, não apaga e não altera nada.

DE ONDE VÊM AS CHAVES ESPERADAS (--fonte)
    json   (padrão) data/exercises.json, campo gif_url
    db     tabela exercicios_sistema, campo gif_url (precisa de DATABASE_URL;
           ex.: `railway run python3 scripts/conferir_midia_bucket.py --fonte db ...`)

COMO CONFERIR (--modo)
    s3     lista o bucket e compara. Precisa das variáveis S3_ENDPOINT_URL,
           S3_BUCKET_NAME, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY e, opcional,
           S3_REGION (as mesmas do app).
    http   pergunta ao próprio site, SEM credenciais: faz GET em
           <url>/exercicios-media/<chave> pedindo só 1 byte (Range) por arquivo.
           Use --url https://www.fitlog.vip. Gera ~1 requisição por GIF
           (--simultaneas controla o ritmo; o padrão, 4, é gentil com a produção).

EXEMPLOS
    python3 scripts/conferir_midia_bucket.py --modo s3
    python3 scripts/conferir_midia_bucket.py --modo http --url https://www.fitlog.vip

Gera relatorio_midia_exercicios.csv e sai com código 1 se faltar algum arquivo.
"""
import argparse
import csv
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PADRAO = os.path.join(RAIZ, 'data', 'exercises.json')


def carregar_do_json(caminho=JSON_PADRAO):
    """[(id, nome, chave)] só dos exercícios que têm gif_url."""
    with open(caminho, encoding='utf-8') as f:
        dados = json.load(f)
    lista = dados if isinstance(dados, list) else list(dados.values())
    return [(str(x.get('id')), x.get('name', ''), x['gif_url'].strip())
            for x in lista if (x.get('gif_url') or '').strip()]


def carregar_do_banco():
    sys.path.insert(0, RAIZ)
    from app import create_app
    from models import ExercicioSistema
    app = create_app()
    with app.app_context():
        return [(str(e.id), e.nome, e.gif_url.strip()) for e in ExercicioSistema.query.all()
                if (e.gif_url or '').strip()]


def listar_bucket(client, bucket):
    """{chave: tamanho} de todos os objetos do bucket (somente listagem)."""
    existentes = {}
    for pagina in client.get_paginator('list_objects_v2').paginate(Bucket=bucket):
        for obj in pagina.get('Contents', []):
            existentes[obj['Key']] = obj['Size']
    return existentes


def comparar(esperados, existentes):
    """Devolve (linhas, extras). linhas: [(id, nome, chave, situacao, detalhe)]."""
    linhas = []
    for ex_id, nome, chave in esperados:
        problema = None
        if chave.startswith('/') or chave != chave.strip() or '..' in chave.split('/'):
            problema = 'chave com formato suspeito'
        if chave not in existentes:
            linhas.append((ex_id, nome, chave, 'faltando', problema or 'não existe no bucket'))
        elif existentes[chave] == 0:
            linhas.append((ex_id, nome, chave, 'vazio', 'objeto com 0 bytes'))
        else:
            linhas.append((ex_id, nome, chave, 'ok', f'{existentes[chave]} bytes'))
    usadas = {c for _, _, c in esperados}
    extras = sorted(k for k in existentes if k not in usadas)
    return linhas, extras


def _pedir(base_url, chave, tentativas=3):
    url = f"{base_url.rstrip('/')}/exercicios-media/{chave}"
    req = urllib.request.Request(url, headers={'Range': 'bytes=0-0', 'User-Agent': 'fitlog-conferir-midia'})
    ultimo = 'erro desconhecido'
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                tipo = r.headers.get('Content-Type', '')
                if not tipo.startswith(('image/', 'video/')):
                    return 'erro', f'tipo inesperado: {tipo or "(vazio)"}'
                return 'ok', f'HTTP {r.status} {tipo}'
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 'faltando', 'HTTP 404'
            if e.code == 429:
                return 'limitado', 'HTTP 429 (limite de requisições do site)'
            ultimo = f'HTTP {e.code}'
            if e.code < 500:
                return 'erro', ultimo
        except Exception as e:  # timeout, DNS, conexão recusada
            ultimo = f'{type(e).__name__}: {e}'
        time.sleep(1.5 * (tentativa + 1))
    return 'erro', ultimo


def conferir_http(esperados, base_url, simultaneas=4):
    unicas = sorted({c for _, _, c in esperados})
    parar = threading.Event()

    def conferir(chave):
        # O site limita requisições por IP (hoje 300/hora, ver extensions.py).
        # Ao primeiro 429 paramos tudo: continuar só geraria centenas de
        # resultados sem valor e manteria o seu IP bloqueado por mais tempo.
        if parar.is_set():
            return 'nao-conferido', 'interrompido após HTTP 429'
        resultado = _pedir(base_url, chave)
        if resultado[0] == 'limitado':
            parar.set()
        return resultado

    with ThreadPoolExecutor(max_workers=max(1, simultaneas)) as pool:
        resultados = {}
        for i, (chave, res) in enumerate(zip(unicas, pool.map(conferir, unicas)), 1):
            resultados[chave] = res
            if i % 100 == 0:
                print(f'  ... {i}/{len(unicas)} conferidos', flush=True)
    return [(ex_id, nome, chave, *resultados[chave]) for ex_id, nome, chave in esperados]


def _cliente_s3():
    faltam = [v for v in ('S3_ENDPOINT_URL', 'S3_BUCKET_NAME', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY')
              if not os.getenv(v)]
    if faltam:
        sys.exit('Faltam variáveis de ambiente para o modo s3: ' + ', '.join(faltam))
    import boto3
    from botocore.config import Config
    cliente = boto3.client(
        's3', endpoint_url=os.environ['S3_ENDPOINT_URL'],
        aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
        region_name=os.getenv('S3_REGION', 'auto'), config=Config(signature_version='s3v4'))
    return cliente, os.environ['S3_BUCKET_NAME']


def main(argv=None):
    p = argparse.ArgumentParser(description='Confere os GIFs dos exercícios no bucket (somente leitura).')
    p.add_argument('--fonte', choices=('json', 'db'), default='json')
    p.add_argument('--modo', choices=('s3', 'http'), required=True)
    p.add_argument('--url', help='endereço do site (modo http), ex.: https://www.fitlog.vip')
    p.add_argument('--simultaneas', type=int, default=4, help='requisições em paralelo no modo http (padrão 4)')
    p.add_argument('--json', default=JSON_PADRAO, help='arquivo de exercícios (padrão: data/exercises.json)')
    p.add_argument('--saida', default='relatorio_midia_exercicios.csv')
    a = p.parse_args(argv)
    if a.modo == 'http' and not a.url:
        p.error('--url é obrigatório no modo http')

    esperados = carregar_do_banco() if a.fonte == 'db' else carregar_do_json(a.json)
    print(f'Fonte {a.fonte}: {len(esperados)} exercícios com gif_url '
          f'({len({c for _, _, c in esperados})} arquivos distintos)')

    extras = None
    if a.modo == 's3':
        cliente, bucket = _cliente_s3()
        existentes = listar_bucket(cliente, bucket)
        print(f'Bucket "{bucket}": {len(existentes)} objetos')
        linhas, extras = comparar(esperados, existentes)
    else:
        print(f'Conferindo {a.url} com {a.simultaneas} requisições simultâneas...')
        linhas = conferir_http(esperados, a.url, a.simultaneas)

    with open(a.saida, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['exercicio_id', 'nome', 'chave', 'situacao', 'detalhe'])
        w.writerows(linhas)

    contagem = Counter(l[3] for l in linhas)
    print('\nRESULTADO: ' + ' | '.join(f'{k}: {v}' for k, v in sorted(contagem.items())))
    problemas = [l for l in linhas if l[3] != 'ok']
    for ex_id, nome, chave, sit, det in problemas[:50]:
        print(f'  [{sit}] id={ex_id} {nome[:40]} -> {chave} ({det})')
    if len(problemas) > 50:
        print(f'  ... e mais {len(problemas) - 50} no CSV')
    if extras is not None:
        por_pasta = Counter(k.split('/')[0] for k in extras)
        print(f'No bucket e não referenciados por nenhum exercício: {len(extras)} '
              f'({dict(por_pasta)}) -- ex.: fotos de professores ficam em professores/, é esperado')
    print(f'Relatório completo: {a.saida}')
    if contagem.get('limitado'):
        print('\nATENÇÃO: o site respondeu 429 (limite de requisições por IP) e a conferência foi '
              'interrompida, então o resultado acima NÃO é completo. Use --modo s3 (não passa pelo '
              'site e não tem esse limite) ou rode de novo quando o limite da mídia for liberado.')
        return 3
    return 1 if any(l[3] in ('faltando', 'vazio') for l in linhas) else 0


if __name__ == '__main__':
    sys.exit(main())
