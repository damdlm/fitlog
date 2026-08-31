"""Adiciona tabela consentimentos_lgpd

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-08-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'consentimentos_lgpd',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('concedido', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('contexto', sa.String(length=200), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'idx_consentimento_usuario_tipo',
        'consentimentos_lgpd',
        ['usuario_id', 'tipo'],
    )


def downgrade():
    op.drop_index('idx_consentimento_usuario_tipo', table_name='consentimentos_lgpd')
    op.drop_table('consentimentos_lgpd')
