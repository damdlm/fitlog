"""Slugify simples (sem dependência nova -- só unicodedata da stdlib)."""
import re
import unicodedata


def slugify(texto: str) -> str:
    """Converte um texto livre em slug de URL: minúsculas, sem acento,
    só [a-z0-9-], sem hífens repetidos/nas pontas. Retorna string vazia
    se `texto` não sobrar nada útil (ex: só emojis/pontuação)."""
    if not texto:
        return ''
    # Remove acentos (NFKD separa a letra do diacrítico, o encode/decode
    # ascii descarta o diacrítico isolado).
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    minusculo = sem_acento.lower()
    com_hifen = re.sub(r'[^a-z0-9]+', '-', minusculo)
    return com_hifen.strip('-')
