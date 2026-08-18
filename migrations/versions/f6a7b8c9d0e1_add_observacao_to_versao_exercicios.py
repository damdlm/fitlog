"""Adiciona versao_exercicios.observacao (nota curta por exercício no treino)

Permite anotar uma observação curta (até 60 caracteres) para um exercício
especificamente dentro de um treino de uma versão -- ex: "pegada aberta",
"cadência lenta na descida". Diferente de exercicios_usuario.observacoes,
que é sobre o exercício em si e vale em todos os treinos onde ele aparece.
Exibida na tela de registrar treino, junto ao exercício.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'versao_exercicios',
        sa.Column('observacao', sa.String(length=60), nullable=True),
    )


def downgrade():
    op.drop_column('versao_exercicios', 'observacao')