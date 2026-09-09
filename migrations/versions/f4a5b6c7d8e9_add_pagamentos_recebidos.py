"""Cria tabela pagamentos_recebidos (histórico de pagamentos confirmados)

Alimenta a tela financeira do admin (/admin/financeiro) com um
histórico de cada cobrança confirmada pelo Asaas -- valor bruto, taxa
do gateway, forma de pagamento, plano e tipo de usuário no momento do
pagamento. Gravado em services/billing_service.py:_aplicar_evento, no
mesmo instante em que um webhook de confirmação de pagamento é
aplicado à Assinatura correspondente.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pagamentos_recebidos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('plano_id', sa.Integer(), sa.ForeignKey('planos.id'), nullable=True),
        sa.Column('gateway_payment_id', sa.String(length=60), nullable=False),
        sa.Column('plano_codigo', sa.String(length=30), nullable=True),
        sa.Column('tipo_usuario', sa.String(length=20), nullable=True),
        sa.Column('forma_pagamento', sa.String(length=10), nullable=False),
        sa.Column('valor_bruto_centavos', sa.Integer(), nullable=False),
        sa.Column('taxa_asaas_centavos', sa.Integer(), nullable=True),
        sa.Column('valor_liquido_centavos', sa.Integer(), nullable=True),
        sa.Column('confirmado_em', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_pagamentos_recebidos_usuario_id', 'pagamentos_recebidos', ['usuario_id'])
    op.create_index('ix_pagamentos_recebidos_gateway_payment_id', 'pagamentos_recebidos', ['gateway_payment_id'], unique=True)
    op.create_index('ix_pagamentos_recebidos_confirmado_em', 'pagamentos_recebidos', ['confirmado_em'])


def downgrade():
    op.drop_index('ix_pagamentos_recebidos_confirmado_em', table_name='pagamentos_recebidos')
    op.drop_index('ix_pagamentos_recebidos_gateway_payment_id', table_name='pagamentos_recebidos')
    op.drop_index('ix_pagamentos_recebidos_usuario_id', table_name='pagamentos_recebidos')
    op.drop_table('pagamentos_recebidos')
