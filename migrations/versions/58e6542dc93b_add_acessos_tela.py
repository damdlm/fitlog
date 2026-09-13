"""Adiciona acessos_tela (contador agregado de acessos por tela, para
o relatório "Telas mais acessadas" do admin)

Revision ID: 58e6542dc93b
Revises: f3a4b5c6d7e8
Create Date: 2026-09-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '58e6542dc93b'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'acessos_tela',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(length=120), nullable=False),
        sa.Column('papel', sa.String(length=20), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('contagem', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint', 'papel', 'data', name='uq_acesso_tela_endpoint_papel_data'),
    )
    op.create_index('ix_acessos_tela_endpoint', 'acessos_tela', ['endpoint'])
    op.create_index('ix_acessos_tela_data', 'acessos_tela', ['data'])


def downgrade():
    op.drop_index('ix_acessos_tela_data', table_name='acessos_tela')
    op.drop_index('ix_acessos_tela_endpoint', table_name='acessos_tela')
    op.drop_table('acessos_tela')
