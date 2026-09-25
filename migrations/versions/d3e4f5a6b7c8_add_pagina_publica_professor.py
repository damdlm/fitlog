"""Adiciona página pública do professor (perfil + avaliações)

Campos novos em users (só usados quando tipo_usuario='professor'):
professor_slug, professor_tagline, professor_bio, professor_cref,
professor_especialidades (JSON), professor_instagram,
professor_foto_chave, professor_mostrar_avaliacoes. Mais a tabela
avaliacoes_professor (nota de 1-5 estrelas de um aluno pro seu
professor, uma por vínculo). Ver models.py:User e
models.py:AvaliacaoProfessor.

Revision ID: d3e4f5a6b7c8
Revises: 51d349d30bb7
Create Date: 2026-09-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = '51d349d30bb7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('professor_slug', sa.String(length=220), nullable=True))
    op.add_column('users', sa.Column('professor_tagline', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('professor_bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('professor_cref', sa.String(length=30), nullable=True))
    op.add_column('users', sa.Column('professor_especialidades', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('professor_instagram', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('professor_foto_chave', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column(
        'professor_mostrar_avaliacoes', sa.Boolean(), nullable=False, server_default=sa.true()
    ))
    op.create_unique_constraint('uq_users_professor_slug', 'users', ['professor_slug'])

    op.create_table(
        'avaliacoes_professor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aluno_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('professor_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('nota', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('aluno_id', 'professor_id', name='uq_avaliacao_aluno_professor'),
        sa.CheckConstraint('nota >= 1 AND nota <= 5', name='ck_avaliacao_nota_1_a_5'),
    )
    op.create_index('idx_avaliacao_professor', 'avaliacoes_professor', ['professor_id'])


def downgrade():
    op.drop_index('idx_avaliacao_professor', table_name='avaliacoes_professor')
    op.drop_table('avaliacoes_professor')

    op.drop_constraint('uq_users_professor_slug', 'users', type_='unique')
    op.drop_column('users', 'professor_mostrar_avaliacoes')
    op.drop_column('users', 'professor_foto_chave')
    op.drop_column('users', 'professor_instagram')
    op.drop_column('users', 'professor_especialidades')
    op.drop_column('users', 'professor_cref')
    op.drop_column('users', 'professor_bio')
    op.drop_column('users', 'professor_tagline')
    op.drop_column('users', 'professor_slug')
