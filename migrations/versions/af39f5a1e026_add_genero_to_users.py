"""Adiciona users.genero (opcional, para personalizar mensagens)

Campo opcional ('M'/'F'/nulo) preenchido pelo próprio usuário no
cadastro ou em Meu Perfil. Usado hoje só para escolher a mensagem de
boas-vindas no login (ver utils/genero_utils.py e
routes/auth_routes.py:login) -- quando nulo, o app cai numa heurística
pelo primeiro nome e, na falta de um nome reconhecido, numa mensagem
neutra. Nenhuma outra tela depende deste campo.

Revision ID: af39f5a1e026
Revises: d5e6f7a8b9c0
Create Date: 2026-09-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'af39f5a1e026'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('genero', sa.String(length=1), nullable=True),
    )


def downgrade():
    op.drop_column('users', 'genero')