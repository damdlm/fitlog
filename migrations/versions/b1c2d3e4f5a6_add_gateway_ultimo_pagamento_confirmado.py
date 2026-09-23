"""Adiciona gateway_ultimo_pagamento_confirmado_id em assinaturas

Guarda o id (no Asaas) do último payment que confirmou/ativou o plano.
Usado por BillingService._deve_ignorar_evento_regressivo pra distinguir
um webhook de atraso/cancelamento sobre a cobrança que está mantendo o
plano ativo agora, de um webhook (chegando fora de ordem, ou sobre uma
cobrança Pix avulsa antiga) que não é mais relevante -- sem essa coluna,
uma cobrança antiga vencendo/sendo cancelada DEPOIS que uma nova já foi
paga derrubava (past_due/canceled) um plano que estava em dia dentro
dos 30 dias. Ver services/billing_service.py:_aplicar_evento.

Revision ID: b1c2d3e4f5a6
Revises: af39f5a1e026
Create Date: 2026-09-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'af39f5a1e026'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assinaturas',
        sa.Column('gateway_ultimo_pagamento_confirmado_id', sa.String(length=60), nullable=True),
    )


def downgrade():
    op.drop_column('assinaturas', 'gateway_ultimo_pagamento_confirmado_id')