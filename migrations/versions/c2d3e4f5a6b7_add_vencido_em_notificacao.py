"""Adiciona vencido_em e ultima_notificacao_vencimento_dias em assinaturas

Suporte pra régua de notificações in-app de plano vencido: vencido_em
marca o início do atraso ATUAL (None enquanto em dia), e
ultima_notificacao_vencimento_dias evita notificar duas vezes no mesmo
dia caso o job rode mais de uma vez. Ver
services/billing_service.py:_iniciar_atraso e
notificar_vencimentos_pendentes.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assinaturas',
        sa.Column('vencido_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'assinaturas',
        sa.Column('ultima_notificacao_vencimento_dias', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('assinaturas', 'ultima_notificacao_vencimento_dias')
    op.drop_column('assinaturas', 'vencido_em')