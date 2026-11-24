"""Catálogo: animações em alta resolução (Gif do Treino) e exercícios novos

- 486 exercícios do catálogo trocam o GIF de 180 px por um vídeo MP4 de
  720 px (mesmo desenho da Gym visual, em alta resolução) e ganham uma
  miniatura WebP. Entre eles, exercícios que não tinham animação nenhuma.
- 494 exercícios novos (ids 8001 em diante), com nome, grupo, músculo
  principal (alvo), secundários, equipamento e instruções em português.

Os dados ficam em data/catalogo_gifdotreino.json (congelado: não editar
depois de aplicado; o data/exercises.json traz o mesmo conteúdo para o
seed). Os arquivos de mídia sobem para o bucket ANTES do deploy, com
scripts/migrar_midia_para_bucket.py --media-dir <pasta midia-gdt>.

Revision ID: a3c7e9b1d5f2
Revises: e1f3a7b9c2d4
Create Date: 2026-11-24 14:00:00.000000
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'a3c7e9b1d5f2'
down_revision = 'e1f3a7b9c2d4'
branch_labels = None
depends_on = None

DADOS = Path(__file__).resolve().parents[2] / 'data' / 'catalogo_gifdotreino.json'

sistema = sa.table(
    'exercicios_sistema',
    sa.column('id', sa.Integer), sa.column('id_original', sa.String), sa.column('nome', sa.String),
    sa.column('categoria', sa.String), sa.column('parte_corpo', sa.String),
    sa.column('equipamento', sa.String), sa.column('instrucao_pt', sa.Text),
    sa.column('passos_pt', sa.JSON), sa.column('grupo_muscular', sa.String),
    sa.column('musculos_secundarios', sa.JSON), sa.column('nicknames', sa.JSON),
    sa.column('alvo', sa.String), sa.column('imagem', sa.String), sa.column('gif_url', sa.String),
    sa.column('atribuicao', sa.String), sa.column('modo_registro', sa.String),
    sa.column('created_at', sa.DateTime(timezone=True)),
)


def _dados():
    with open(DADOS, encoding='utf-8') as f:
        return json.load(f)


def _trocar_midia(conn, midias):
    """midias: {id_original: [gif_url, imagem]}"""
    stmt = (sistema.update()
            .where(sistema.c.id_original == sa.bindparam('b_id'))
            .values(gif_url=sa.bindparam('b_gif'), imagem=sa.bindparam('b_img')))
    linhas = [{'b_id': i, 'b_gif': g, 'b_img': img} for i, (g, img) in midias.items()]
    if linhas:
        conn.execute(stmt, linhas)


def upgrade():
    dados = _dados()
    conn = op.get_bind()
    _trocar_midia(conn, dados['trocas'])

    ids = [n['id_original'] for n in dados['novos']]
    existentes = {linha[0] for linha in conn.execute(
        sa.select(sistema.c.id_original).where(sistema.c.id_original.in_(ids)))}
    agora = datetime.now(timezone.utc)
    novos = [dict(n, created_at=agora) for n in dados['novos'] if n['id_original'] not in existentes]
    if novos:
        op.bulk_insert(sistema, novos)


def downgrade():
    dados = _dados()
    conn = op.get_bind()
    _trocar_midia(conn, dados['antigos'])
    # Só apaga os novos que ninguém usou em ficha ou registro de treino.
    ids = [n['id_original'] for n in dados['novos']]
    conn.execute(
        sa.text(
            "DELETE FROM exercicios_sistema WHERE id_original IN :ids "
            "AND id NOT IN (SELECT exercicio_base_id FROM registros_treino WHERE exercicio_base_id IS NOT NULL) "
            "AND id NOT IN (SELECT exercicio_base_id FROM versao_exercicios WHERE exercicio_base_id IS NOT NULL)"
        ).bindparams(sa.bindparam('ids', expanding=True)),
        {'ids': ids},
    )
