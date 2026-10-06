"""Verificação de e-mail no cadastro

Campos novos em users: email_verificado_em (NULL = não verificado) e
falhas_login/login_bloqueado_ate (bloqueio temporário por conta no login).
Contas já existentes são marcadas como verificadas agora, para que
ninguém seja trancado para fora quando a verificação passar a ser
obrigatória -- só os cadastros feitos DEPOIS desta migration precisam
confirmar o e-mail.

Revision ID: fcef41d0b373
Revises: d6e7f8a9b0c1
Create Date: 2026-10-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fcef41d0b373'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column(
        'email_verificado_em', sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column('users', sa.Column(
        'falhas_login', sa.Integer(), nullable=False, server_default='0',
    ))
    op.add_column('users', sa.Column(
        'login_bloqueado_ate', sa.DateTime(timezone=True), nullable=True,
    ))
    op.execute("UPDATE users SET email_verificado_em = CURRENT_TIMESTAMP WHERE email_verificado_em IS NULL")


def downgrade():
    op.drop_column('users', 'login_bloqueado_ate')
    op.drop_column('users', 'falhas_login')
    op.drop_column('users', 'email_verificado_em')
