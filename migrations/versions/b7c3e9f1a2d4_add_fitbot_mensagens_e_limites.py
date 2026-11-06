"""Adiciona fitbot_mensagens e os limites do FitBot em configuracao_app

fitbot_mensagens: uma linha por pergunta respondida pelo FitBot (quem,
quando, texto ou foto -- sem o conteúdo da conversa). Base da cota diária
por usuário, do teto mensal do app e dos números da tela Admin > FitBot.

configuracao_app:
- fitbot_limite_diario_usuario: mensagens por usuário por dia (padrão 30;
  nulo = sem limite).
- fitbot_limite_mensal_total: teto do app inteiro no mês (nulo = sem teto).

Revision ID: b7c3e9f1a2d4
Revises: e8a1c4d7f2b9
Create Date: 2026-11-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7c3e9f1a2d4'
down_revision = 'e8a1c4d7f2b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fitbot_mensagens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('modo', sa.String(length=10), nullable=False, server_default='texto'),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_fitbot_mensagens_criado_em', 'fitbot_mensagens', ['criado_em'])
    op.create_index('ix_fitbot_mensagens_user_criado', 'fitbot_mensagens', ['user_id', 'criado_em'])

    op.add_column(
        'configuracao_app',
        sa.Column('fitbot_limite_diario_usuario', sa.Integer(), nullable=True, server_default='30'),
    )
    op.add_column(
        'configuracao_app',
        sa.Column('fitbot_limite_mensal_total', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('configuracao_app', 'fitbot_limite_mensal_total')
    op.drop_column('configuracao_app', 'fitbot_limite_diario_usuario')
    op.drop_index('ix_fitbot_mensagens_user_criado', table_name='fitbot_mensagens')
    op.drop_index('ix_fitbot_mensagens_criado_em', table_name='fitbot_mensagens')
    op.drop_table('fitbot_mensagens')
