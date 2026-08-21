"""Adiciona exercicios_usuario.copiado_de_exercicio_id

copiado_de_professor_id (migration anterior) só diz QUEM é o professor
de origem de uma cópia -- não dá pra saber DE QUAL exercício específico
ela veio depois que o professor renomeia o original (o nome deixa de ser
um jeito confiável de re-encontrar o vínculo). Essa coluna guarda uma
auto-referência direta pro exercício de origem, usada pra propagar
edições do professor pras cópias já existentes dos alunos (ver
ExercicioService._propagar_edicao_para_alunos). ondelete='SET NULL'
porque a cópia do aluno é independente -- some só a referência de
origem, não o exercício do aluno, se o original for excluído.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'exercicios_usuario',
        sa.Column('copiado_de_exercicio_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_exercicios_usuario_copiado_de_exercicio_id',
        'exercicios_usuario', 'exercicios_usuario',
        ['copiado_de_exercicio_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'idx_exercicio_usuario_copiado_de_exercicio',
        'exercicios_usuario', ['copiado_de_exercicio_id'],
    )


def downgrade():
    op.drop_index('idx_exercicio_usuario_copiado_de_exercicio', table_name='exercicios_usuario')
    op.drop_constraint('fk_exercicios_usuario_copiado_de_exercicio_id', 'exercicios_usuario', type_='foreignkey')
    op.drop_column('exercicios_usuario', 'copiado_de_exercicio_id')