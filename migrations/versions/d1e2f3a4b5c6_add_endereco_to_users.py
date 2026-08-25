"""Adiciona endereco_cep e endereco_numero em users

O checkout de assinatura recorrente por cartão de crédito (RECURRENT +
CREDIT_CARD) exige que o cliente no Asaas tenha phone, address,
addressNumber, postalCode, province e city preenchidos -- a própria API
respondeu isso explicitamente ao tentar criar um checkout sem esses
dados. Mandando só o CEP (postalCode), o Asaas preenche address/
province/city automaticamente a partir dele -- só addressNumber e phone
continuam precisando ser enviados à parte (telefone já existia em
users.telefone; só CEP e número do endereço são novos).

Coluna nullable: só é preenchida quando o usuário assina pela primeira
vez (ver routes/billing_routes.py:assinar), igual ao cpf_cnpj da
migration anterior.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-08-23 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c0d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('endereco_cep', sa.String(length=9), nullable=True))
    op.add_column('users', sa.Column('endereco_numero', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('users', 'endereco_numero')
    op.drop_column('users', 'endereco_cep')
