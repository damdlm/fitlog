"""Mídia do Gif do Treino: MP4 → WebP animado (480px)

No iPhone, o <video> da demonstração travava a página inteira de vez em
quando (só voltava fechando o app), mesmo com o vídeo invisível do modo
treino pausado. Os GIFs antigos, exibidos num <img>, nunca travaram: as
mesmas animações passam a ser WebP animado (gerado dos GIFs originais em
1080px), exibido no <img> do modal como os GIFs.

Só troca o caminho em gif_url; os arquivos vêm do pacote enviado ao bucket
ANTES do deploy (scripts/migrar_midia_para_bucket.py --media-dir). Os MP4
continuam no bucket (o downgrade volta para eles).

Revision ID: d2f6a8c4e0b3
Revises: b5d8f2a4c6e1
Create Date: 2026-11-25 10:45:00.000000
"""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'd2f6a8c4e0b3'
down_revision = 'b5d8f2a4c6e1'
branch_labels = None
depends_on = None

# Dados congelados desta migração (não editar depois de aplicada).
DADOS = Path(__file__).resolve().parents[2] / 'data' / 'catalogo_gifdotreino_webp.json'

sistema = sa.table(
    'exercicios_sistema',
    sa.column('gif_url', sa.String),
)


def _mapa():
    return json.loads(DADOS.read_text(encoding='utf-8'))['mp4_para_webp']


def _trocar(pares):
    conn = op.get_bind()
    stmt = (
        sistema.update()
        .where(sistema.c.gif_url == sa.bindparam('antes'))
        .values(gif_url=sa.bindparam('depois'))
    )
    conn.execute(stmt, [{'antes': a, 'depois': d} for a, d in pares])


def upgrade():
    _trocar(_mapa().items())


def downgrade():
    _trocar((d, a) for a, d in _mapa().items())
