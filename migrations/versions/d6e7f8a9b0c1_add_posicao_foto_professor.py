"""Adiciona a posição da foto do professor na página pública

Campos novos em users (só usados quando tipo_usuario='professor'):
professor_foto_pos_x e professor_foto_pos_y -- posição da foto dentro
do círculo, em % (0-100, como o CSS object-position). 50/50 =
centralizada, que é como todas as fotos já eram exibidas antes.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column(
        'professor_foto_pos_x', sa.Integer(), nullable=False, server_default='50',
    ))
    op.add_column('users', sa.Column(
        'professor_foto_pos_y', sa.Integer(), nullable=False, server_default='50',
    ))


def downgrade():
    op.drop_column('users', 'professor_foto_pos_y')
    op.drop_column('users', 'professor_foto_pos_x')
