"""Meta de séries e repetições por exercício da ficha (lote 6b, T4)

A ficha guardava só o exercício e uma observação de 60 caracteres; a meta
("4 × 10–12") ficava no texto livre, sem a tela de registro conseguir usar.
Três colunas opcionais em versao_exercicios:

- meta_series: quantas séries (1 a 10)
- meta_reps_min / meta_reps_max: faixa de repetições (1 a 100). Meta de
  número fixo ("4 × 10") grava min = max = 10.

Todas nulas por padrão: fichas existentes seguem iguais.

Revision ID: b7e2c4d9a1f3
Revises: 0aa93ffc7a76
Create Date: 2026-11-18 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e2c4d9a1f3'
down_revision = '0aa93ffc7a76'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('versao_exercicios') as batch:
        batch.add_column(sa.Column('meta_series', sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column('meta_reps_min', sa.SmallInteger(), nullable=True))
        batch.add_column(sa.Column('meta_reps_max', sa.SmallInteger(), nullable=True))


def downgrade():
    with op.batch_alter_table('versao_exercicios') as batch:
        batch.drop_column('meta_reps_max')
        batch.drop_column('meta_reps_min')
        batch.drop_column('meta_series')
