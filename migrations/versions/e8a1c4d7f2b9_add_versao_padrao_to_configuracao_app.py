"""Adiciona configuracao_app.versao_padrao_id (plano padrão para alunos novos)

Aponta para a versão de treino (versoes_globais) de uma conta admin que
serve de modelo: todo aluno que se cadastra sozinho, sem professor, recebe
uma cópia dessa estrutura (treinos + exercícios) já na conta dele, e pode
editá-la depois. Nulo = recurso desligado (comportamento de sempre).

ondelete SET NULL: excluir a versão modelo apenas desliga o recurso.

Revision ID: e8a1c4d7f2b9
Revises: fcef41d0b373
Create Date: 2026-10-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e8a1c4d7f2b9'
down_revision = 'fcef41d0b373'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'configuracao_app',
        sa.Column('versao_padrao_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_configuracao_app_versao_padrao',
        'configuracao_app', 'versoes_globais',
        ['versao_padrao_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint(
        'fk_configuracao_app_versao_padrao', 'configuracao_app', type_='foreignkey'
    )
    op.drop_column('configuracao_app', 'versao_padrao_id')
