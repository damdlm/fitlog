"""Adiciona tabela eventos_analytics (analytics de produto server-side)

Analytics privacy-first: sem script de terceiro, sem cookie -- só uma
tabela para registrar os 3 eventos de produto (sign_up,
workout_completed, subscription_started) com parâmetros agregados,
não-identificáveis. Ver services/analytics_service.py.

Revision ID: 2da913803890
Revises: f4a5b6c7d8e9
Create Date: 2026-09-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2da913803890'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'eventos_analytics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome_evento', sa.String(length=60), nullable=False),
        sa.Column('parametros', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_eventos_analytics_nome_evento'),
        'eventos_analytics', ['nome_evento'], unique=False,
    )
    op.create_index(
        op.f('ix_eventos_analytics_criado_em'),
        'eventos_analytics', ['criado_em'], unique=False,
    )


def downgrade():
    op.drop_index(op.f('ix_eventos_analytics_criado_em'), table_name='eventos_analytics')
    op.drop_index(op.f('ix_eventos_analytics_nome_evento'), table_name='eventos_analytics')
    op.drop_table('eventos_analytics')
