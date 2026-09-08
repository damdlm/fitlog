"""Adiciona agrupamento (chave + contador) na tabela notificacoes

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'notificacoes',
        sa.Column('chave_agrupamento', sa.String(length=80), nullable=True)
    )
    op.add_column(
        'notificacoes',
        sa.Column('ocorrencias', sa.Integer(), nullable=False, server_default='1')
    )
    op.create_index(
        'idx_notificacao_agrupamento',
        'notificacoes',
        ['destinatario_id', 'chave_agrupamento', 'lida'],
    )


def downgrade():
    op.drop_index('idx_notificacao_agrupamento', table_name='notificacoes')
    op.drop_column('notificacoes', 'ocorrencias')
    op.drop_column('notificacoes', 'chave_agrupamento')
