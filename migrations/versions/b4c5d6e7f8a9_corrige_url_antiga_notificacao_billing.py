"""Corrige URL antiga (sem /billing) em notificações de billing já gravadas

Bug real: services/billing_service.py gravava o link das notificações
de plano vencido/cancelado/upgrade de tier como '/minha-assinatura',
mas a rota fica em '/billing/minha-assinatura' (blueprint registrado
com esse prefixo em routes/__init__.py). O código já foi corrigido,
mas isso só vale para notificações CRIADAS depois do deploy -- quem já
tinha uma dessas notificações não lidas na caixa continua clicando
numa URL quebrada gravada no banco, porque o texto já estava salvo
antes da correção. Esta migration atualiza os registros existentes.

Revision ID: b4c5d6e7f8a9
Revises: a1c3e5f7b9d2
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8a9'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE notificacoes SET url = '/billing/minha-assinatura' "
        "WHERE url = '/minha-assinatura'"
    )


def downgrade():
    op.execute(
        "UPDATE notificacoes SET url = '/minha-assinatura' "
        "WHERE url = '/billing/minha-assinatura'"
    )