"""Cria configuracao_app (singleton) com a flag cobranca_ativa --
liga/desliga o "modo grátis" de lançamento (ver
models.py:ConfiguracaoApp e services/configuracao_service.py).

Semeia a única linha (id=1) já com cobranca_ativa=True, ou seja, não
muda nada do comportamento atual -- o admin decide quando desligar,
pela tela /admin/telas-controladas.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'configuracao_app',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cobranca_ativa', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
    )

    configuracao_table = sa.table(
        'configuracao_app',
        sa.column('id', sa.Integer),
        sa.column('cobranca_ativa', sa.Boolean),
        sa.column('atualizado_em', sa.DateTime),
    )
    op.bulk_insert(configuracao_table, [{
        'id': 1,
        'cobranca_ativa': True,
        'atualizado_em': datetime.now(timezone.utc),
    }])


def downgrade():
    op.drop_table('configuracao_app')
