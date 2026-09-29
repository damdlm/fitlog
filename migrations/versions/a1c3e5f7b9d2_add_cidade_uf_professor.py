"""Adiciona cidade/UF do professor (busca textual futura no mapa)

Capturados junto com a geocodificação do CEP (mesma chamada à BrasilAPI
que já preenche professor_latitude/longitude -- ver
services/geolocalizacao_service.py). Guardados à parte das coordenadas
pra permitir filtrar/agrupar por cidade sem depender de bounding box.

Revision ID: a1c3e5f7b9d2
Revises: e2f4a6c8b0d1
Create Date: 2026-09-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1c3e5f7b9d2'
down_revision = 'e2f4a6c8b0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('professor_cidade', sa.String(120), nullable=True))
    op.add_column('users', sa.Column('professor_uf', sa.String(2), nullable=True))
    op.create_index('ix_users_professor_cidade', 'users', ['professor_cidade'])


def downgrade():
    op.drop_index('ix_users_professor_cidade', table_name='users')
    op.drop_column('users', 'professor_uf')
    op.drop_column('users', 'professor_cidade')