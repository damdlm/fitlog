"""Adiciona fitbot_chamadas (uso técnico das IAs) e historico_metricas
(snapshots periódicos do painel de monitoramento)

Revision ID: f3a4b5c6d7e8
Revises: 2da913803890
Create Date: 2026-09-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = '2da913803890'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fitbot_chamadas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provedor', sa.String(length=20), nullable=False),
        sa.Column('sucesso', sa.Boolean(), nullable=False),
        sa.Column('duracao_ms', sa.Integer(), nullable=False),
        sa.Column('tokens_entrada', sa.Integer(), nullable=True),
        sa.Column('tokens_saida', sa.Integer(), nullable=True),
        sa.Column('motivo_falha', sa.String(length=120), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fitbot_chamadas_provedor', 'fitbot_chamadas', ['provedor'])
    op.create_index('ix_fitbot_chamadas_criado_em', 'fitbot_chamadas', ['criado_em'])

    op.create_table(
        'historico_metricas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('coletado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dados', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_historico_metricas_coletado_em', 'historico_metricas', ['coletado_em'])


def downgrade():
    op.drop_index('ix_historico_metricas_coletado_em', table_name='historico_metricas')
    op.drop_table('historico_metricas')

    op.drop_index('ix_fitbot_chamadas_criado_em', table_name='fitbot_chamadas')
    op.drop_index('ix_fitbot_chamadas_provedor', table_name='fitbot_chamadas')
    op.drop_table('fitbot_chamadas')
