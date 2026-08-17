"""Adiciona users.aparecer_no_ranking (opt-out da tela Melhores Alunos)

Permite que o aluno escolha não aparecer no ranking geral de "Melhores
Alunos" (comparação entre alunos, nome + estatísticas de treino visíveis
a outros usuários logados). Default True: quem não mexer na configuração
aparece normalmente, mas fica reversível a qualquer momento no perfil.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('aparecer_no_ranking', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column('users', 'aparecer_no_ranking')
