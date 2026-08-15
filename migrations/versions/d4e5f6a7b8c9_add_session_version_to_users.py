"""Adiciona users.session_version (CORREÇÃO 10 do hardening de segurança)

Permite invalidar sessões antigas após troca de senha sem precisar de
uma tabela/query extra por requisição: o valor é comparado com o que
foi gravado na sessão assinada do Flask no momento do login.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-13 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('users', 'session_version')
