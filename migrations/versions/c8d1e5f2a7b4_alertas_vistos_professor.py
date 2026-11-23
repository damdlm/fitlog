"""Alertas do painel do professor marcados como "Visto" (lote 3)

Uma linha por (professor, aluno, tipo de alerta). A coluna `chave`
identifica a ocorrência do alerta: enquanto o alerta atual tiver a
mesma chave ele fica oculto; quando a situação muda (o aluno treina e
para de novo, outra semana, outra ficha) a chave muda e ele volta.

Revision ID: c8d1e5f2a7b4
Revises: b7e2c4d9a1f3
Create Date: 2026-11-23 16:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c8d1e5f2a7b4'
down_revision = 'b7e2c4d9a1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'alertas_vistos_professor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('professor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('aluno_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('chave', sa.String(length=40), nullable=False),
        sa.Column('visto_em', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('professor_id', 'aluno_id', 'tipo', name='uq_alerta_visto_prof_aluno_tipo'),
    )
    op.create_index('idx_alerta_visto_professor', 'alertas_vistos_professor', ['professor_id'])


def downgrade():
    op.drop_index('idx_alerta_visto_professor', table_name='alertas_vistos_professor')
    op.drop_table('alertas_vistos_professor')
