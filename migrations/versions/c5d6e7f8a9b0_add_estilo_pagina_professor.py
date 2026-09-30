"""Adiciona o estilo visual da página pública do professor

Campo novo em users (só usado quando tipo_usuario='professor'):
professor_estilo_pagina -- chave de ESTILOS_PAGINA em
services/professor_perfil_service.py ('diagonal', 'textura', ...).
Professores que já existiam ficam com 'diagonal' (o estilo que já
viam antes desta migration) via server_default.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column(
        'professor_estilo_pagina', sa.String(length=30),
        nullable=False, server_default='diagonal',
    ))


def downgrade():
    op.drop_column('users', 'professor_estilo_pagina')
