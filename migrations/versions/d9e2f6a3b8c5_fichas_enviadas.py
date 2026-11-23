"""Fichas enviadas pelo professor para vários alunos (lote 4)

Guarda as fichas que ainda vão entrar: "quando a ficha atual vencer"
(aplicada pelo cron diário) ou "como sugestão" (o aluno aceita ou
recusa). A troca imediata não usa esta tabela.

Revision ID: d9e2f6a3b8c5
Revises: c8d1e5f2a7b4
Create Date: 2026-11-23 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9e2f6a3b8c5'
down_revision = 'c8d1e5f2a7b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fichas_enviadas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('professor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('aluno_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('origem_versao_id', sa.Integer(), sa.ForeignKey('versoes_globais.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('origem_modelo', sa.String(length=60), nullable=True),
        sa.Column('descricao', sa.String(length=200), nullable=False),
        sa.Column('validade_meses', sa.Integer(), nullable=True),
        sa.Column('modo', sa.String(length=12), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pendente'),
        sa.Column('versao_alvo_id', sa.Integer(), sa.ForeignKey('versoes_globais.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('versao_criada_id', sa.Integer(), sa.ForeignKey('versoes_globais.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('motivo', sa.String(length=200), nullable=True),
        sa.Column('criada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('respondida_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_ficha_enviada_aluno_status', 'fichas_enviadas', ['aluno_id', 'status'])
    op.create_index('idx_ficha_enviada_professor_status', 'fichas_enviadas', ['professor_id', 'status'])


def downgrade():
    op.drop_index('idx_ficha_enviada_professor_status', table_name='fichas_enviadas')
    op.drop_index('idx_ficha_enviada_aluno_status', table_name='fichas_enviadas')
    op.drop_table('fichas_enviadas')
