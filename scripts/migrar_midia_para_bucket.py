#!/usr/bin/env python3
"""Migra os arquivos de mídia de exercícios do volume local do Railway
(/app/exercicios) para o bucket S3-compatível.

USO (rodar de dentro do container em produção, ou localmente com
EXERCICIOS_MEDIA_DIR apontando pra uma cópia do volume):

    python3 scripts/migrar_midia_para_bucket.py            # migra tudo
    python3 scripts/migrar_midia_para_bucket.py --dry-run  # só lista, não sobe nada
    python3 scripts/migrar_midia_para_bucket.py --verificar  # confere o que já foi migrado

Idempotente: pode rodar de novo sem problema -- arquivos que já existem
no bucket (mesmo nome/chave) são pulados por padrão, a menos que
--forcar seja passado.
"""
import os
import sys
import argparse
import mimetypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.storage_service import StorageService


def encontrar_arquivos(media_dir: str):
    """Lista todos os arquivos do volume, com o caminho relativo que
    vira a "chave" no bucket (mesmo esquema que gif_url/imagem usam
    hoje, ex: "videos/0001-2gPfomN.gif")."""
    arquivos = []
    for raiz, _dirs, nomes in os.walk(media_dir):
        for nome in nomes:
            caminho_absoluto = os.path.join(raiz, nome)
            chave = os.path.relpath(caminho_absoluto, media_dir)
            # Bucket S3 usa "/" mesmo em qualquer SO
            chave = chave.replace(os.sep, "/")
            arquivos.append((caminho_absoluto, chave))
    return arquivos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="só lista o que seria migrado, não sobe nada")
    parser.add_argument("--verificar", action="store_true", help="confere quantos arquivos já estão no bucket")
    parser.add_argument("--forcar", action="store_true", help="sobe de novo mesmo que já exista no bucket")
    parser.add_argument("--media-dir", default=os.environ.get("EXERCICIOS_MEDIA_DIR", "/app/exercicios"))
    args = parser.parse_args()

    if not StorageService.is_configured():
        print("StorageService não configurado (variáveis S3_* ausentes) -- "
              "nada a migrar ainda. Isso é esperado antes do bucket existir; "
              "quando as variáveis forem configuradas, o próximo deploy migra "
              "automaticamente (este script roda no preDeployCommand).")
        sys.exit(0)  # sucesso, não falha o deploy -- é um "ainda não é hora"

    if not os.path.isdir(args.media_dir):
        print(f"ERRO: diretório '{args.media_dir}' não existe ou não é acessível daqui.")
        sys.exit(1)

    arquivos = encontrar_arquivos(args.media_dir)
    print(f"Encontrados {len(arquivos)} arquivos em '{args.media_dir}'.\n")

    if args.verificar:
        existentes = sum(1 for _, chave in arquivos if StorageService.object_exists(chave))
        print(f"Já estão no bucket: {existentes}/{len(arquivos)}")
        if existentes < len(arquivos):
            print(f"Faltam migrar: {len(arquivos) - existentes}")
        return

    if args.dry_run:
        for caminho, chave in arquivos[:20]:
            print(f"  [dry-run] {caminho} -> s3://{chave}")
        if len(arquivos) > 20:
            print(f"  ... e mais {len(arquivos) - 20} arquivo(s)")
        print("\nNenhum arquivo foi de fato enviado (--dry-run).")
        return

    enviados, pulados, falhas = 0, 0, 0
    for i, (caminho, chave) in enumerate(arquivos, 1):
        if not args.forcar and StorageService.object_exists(chave):
            pulados += 1
            continue

        content_type, _ = mimetypes.guess_type(caminho)
        ok = StorageService.upload_file(caminho, chave, content_type=content_type)
        if ok:
            enviados += 1
        else:
            falhas += 1
            print(f"  FALHOU: {chave}")

        if i % 50 == 0:
            print(f"  ... {i}/{len(arquivos)} processados "
                  f"(enviados={enviados}, pulados={pulados}, falhas={falhas})")

    print(f"\nConcluído: {enviados} enviados, {pulados} já existiam (pulados), {falhas} falharam.")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()