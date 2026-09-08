"""Adiciona tabela de notificações (aluno <-> professor)

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notificacoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('destinatario_id', sa.Integer(), nullable=False),
        sa.Column('remetente_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('titulo', sa.String(length=150), nullable=False),
        sa.Column('mensagem', sa.String(length=300), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=True),
        sa.Column('lida', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['destinatario_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['remetente_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_notificacao_destinatario',
        'notificacoes',
        ['destinatario_id', 'lida', 'created_at'],
    )


def downgrade():
    op.drop_index('idx_notificacao_destinatario', table_name='notificacoes')
    op.drop_table('notificacoes')
