"""Adiciona crash_logs (travamentos de frontend e backend, painel
/admin/crash-logs)

Revision ID: c7d8e9f0a1b2
Revises: 58e6542dc93b
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = '58e6542dc93b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'crash_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('origem', sa.String(length=10), nullable=False),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('mensagem', sa.Text(), nullable=False),
        sa.Column('detalhes', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crash_logs_origem', 'crash_logs', ['origem'])
    op.create_index('ix_crash_logs_usuario_id', 'crash_logs', ['usuario_id'])
    op.create_index('ix_crash_logs_criado_em', 'crash_logs', ['criado_em'])


def downgrade():
    op.drop_index('ix_crash_logs_criado_em', table_name='crash_logs')
    op.drop_index('ix_crash_logs_usuario_id', table_name='crash_logs')
    op.drop_index('ix_crash_logs_origem', table_name='crash_logs')
    op.drop_table('crash_logs')
