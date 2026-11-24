"""Peso corporal opcional do usuário (nível de força no Progresso)

Revision ID: e1f3a7b9c2d4
Revises: d9e2f6a3b8c5
Create Date: 2026-11-23 21:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f3a7b9c2d4'
down_revision = 'd9e2f6a3b8c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('peso_kg', sa.Numeric(5, 1), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_column('peso_kg')
