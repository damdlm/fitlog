"""Adiciona cpf_cnpj em users

O Asaas exige CPF/CNPJ pra gerar qualquer cobrança de verdade (é
exigência da Receita Federal para qualquer transação financeira no
Brasil) -- sem isso, POST /customers até funciona (só cadastra nome e
e-mail), mas POST /checkouts falha com 400 na hora de efetivamente
criar a cobrança vinculada a esse cliente.

Coluna nullable: só é preenchida quando o usuário assina pela primeira
vez (ver routes/billing_routes.py:assinar) -- não pedimos isso no
cadastro pra não criar fricção pra quem nunca vai pagar nada.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-22 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c0d1e2f3a4b5'
down_revision = 'b9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('cpf_cnpj', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('users', 'cpf_cnpj')
