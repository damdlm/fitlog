"""Adiciona exercicios_sistema.nicknames (nomes alternativos p/ busca)

Permite que a busca de exercícios do catálogo (exercicios_sistema) encontre
resultados também por apelidos/nomes alternativos (ex: "Crunch 3/4" para
"Abdominal supra 3/4"), além do nome principal. Populado pelo script de seed
a partir de data/exercises.json.

Revision ID: b7c8d9e0f1a2
Revises: a3b4c5d6e7f8
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'exercicios_sistema',
        sa.Column('nicknames', sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column('exercicios_sistema', 'nicknames')
