"""Adiciona coluna versao em consentimentos_lgpd

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-08-31 00:00:00.000000

A tabela consentimentos_lgpd já existe em produção (migration
f1a2b3c4d5e6), criada sem a coluna `versao` -- ela só passou a ser
necessária com o versionamento de aceite de Termos de Uso/Política de
Privacidade (ver services/privacidade_service.py). Coluna nullable,
sem valor obrigatório, então não exige nenhum preenchimento retroativo
nas linhas já existentes.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'consentimentos_lgpd',
        sa.Column('versao', sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column('consentimentos_lgpd', 'versao')