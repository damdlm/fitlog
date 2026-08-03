"""Adiciona coluna tempo_treino em historico_treino

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'historico_treino',
        sa.Column('tempo_treino', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('historico_treino', 'tempo_treino')