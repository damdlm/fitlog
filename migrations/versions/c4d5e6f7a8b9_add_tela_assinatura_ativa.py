"""Adiciona tela_assinatura_ativa em configuracao_app -- flag
separada de cobranca_ativa que só esconde a tela "Minha Assinatura"
(e o link dela no menu) de quem não é admin, ver
models.py:ConfiguracaoApp.

server_default=true() faz a coluna nascer True pra linha já existente
(id=1, seedada em b3c4d5e6f7a8) sem precisar de um UPDATE separado --
não muda nada do comportamento atual, a tela continua visível até o
admin desativar em /admin/telas-controladas.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'configuracao_app',
        sa.Column('tela_assinatura_ativa', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column('configuracao_app', 'tela_assinatura_ativa')
