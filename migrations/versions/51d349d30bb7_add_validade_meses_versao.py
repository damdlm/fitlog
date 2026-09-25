"""Adiciona validade_meses e alerta_expiracao_enviado_em em versoes_globais

Permite que o professor (ou o próprio aluno, em versões auto-geridas)
defina um prazo de validade opcional para a versão, em meses, contado a
partir de data_inicio (que já é sempre a data real de início de uso --
criação ou clonagem, nunca escolhida pelo cliente). alerta_expiracao_
enviado_em evita alertar aluno/professor mais de uma vez pela mesma
expiração (ver comando CLI "versoes-alertar-expiracao" e
VersaoService/NotificacaoService).

Revision ID: 51d349d30bb7
Revises: c2d3e4f5a6b7
Create Date: 2026-09-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '51d349d30bb7'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'versoes_globais',
        sa.Column('validade_meses', sa.Integer(), nullable=True),
    )
    op.add_column(
        'versoes_globais',
        sa.Column('alerta_expiracao_enviado_em', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('versoes_globais', 'alerta_expiracao_enviado_em')
    op.drop_column('versoes_globais', 'validade_meses')