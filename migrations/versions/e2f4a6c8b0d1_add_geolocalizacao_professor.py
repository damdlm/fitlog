"""Adiciona geolocalização do professor (mapa de busca do aluno)

Campos novos em users (só usados quando tipo_usuario='professor'):
professor_latitude, professor_longitude, professor_geo_atualizado_em,
professor_visivel_no_mapa. Reaproveita o endereco_cep que já existe em
User (hoje usado só para o checkout Asaas -- ver services/billing_service.py)
como origem da geocodificação; nenhuma coluna de CEP nova é criada.

Ver models.py:User e services/geolocalizacao_service.py.

Revision ID: e2f4a6c8b0d1
Revises: c935c9397dd0
Create Date: 2026-09-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e2f4a6c8b0d1'
down_revision = 'c935c9397dd0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('professor_latitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('professor_longitude', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('professor_geo_atualizado_em', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column(
        'professor_visivel_no_mapa', sa.Boolean(), nullable=False, server_default=sa.false()
    ))
    op.create_index(
        'ix_users_professor_geo', 'users', ['professor_latitude', 'professor_longitude']
    )


def downgrade():
    op.drop_index('ix_users_professor_geo', table_name='users')
    op.drop_column('users', 'professor_visivel_no_mapa')
    op.drop_column('users', 'professor_geo_atualizado_em')
    op.drop_column('users', 'professor_longitude')
    op.drop_column('users', 'professor_latitude')
