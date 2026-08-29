"""Cria tabela telas_controladas (bloqueio de tela configurável pelo admin)

Antes, Estatísticas/FitBot/Tabela de Progresso eram as únicas telas que
exigiam plano pago, e essa regra estava fixa no código (decorator
@acesso_premium_required sem parâmetro). Agora o admin escolhe, numa
tela própria (/admin/telas-controladas), quais telas exigem Fit/Pró/
Premium ativo e quais ficam livres pra qualquer usuário logado --
ver models.py:TelaControlada e services/tela_controlada_service.py.

Semeia as 6 telas já mapeadas no código nesta entrega:
- estatisticas, tabela_progresso, fitbot: True (bloqueiam) -- mantém
  exatamente o comportamento de antes desta migration, ninguém que já
  usava o app perde acesso nem ganha acesso por engano
- calendario, ranking, dashboard: False (livres) -- são gates NOVOS
  que não existiam antes; começam desligados de propósito pra não
  bloquear ninguém de surpresa. O admin liga cada uma quando quiser
  em /admin/telas-controladas.

Revision ID: 22250725ed4f
Revises: e1f2a3b4c5d6
Create Date: 2026-08-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '22250725ed4f'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


telas_table = sa.table(
    'telas_controladas',
    sa.column('chave', sa.String),
    sa.column('nome_exibicao', sa.String),
    sa.column('bloqueia_sem_plano', sa.Boolean),
)


def upgrade():
    op.create_table(
        'telas_controladas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chave', sa.String(length=50), nullable=False),
        sa.Column('nome_exibicao', sa.String(length=100), nullable=False),
        sa.Column('bloqueia_sem_plano', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_telas_controladas_chave', 'telas_controladas', ['chave'], unique=True)

    op.bulk_insert(telas_table, [
        {'chave': 'estatisticas', 'nome_exibicao': 'Estatísticas', 'bloqueia_sem_plano': True},
        {'chave': 'tabela_progresso', 'nome_exibicao': 'Tabela de Progresso', 'bloqueia_sem_plano': True},
        {'chave': 'fitbot', 'nome_exibicao': 'FitBot', 'bloqueia_sem_plano': True},
        {'chave': 'calendario', 'nome_exibicao': 'Calendário', 'bloqueia_sem_plano': False},
        {'chave': 'ranking', 'nome_exibicao': 'Ranking', 'bloqueia_sem_plano': False},
        {'chave': 'dashboard', 'nome_exibicao': 'Dashboard', 'bloqueia_sem_plano': False},
    ])


def downgrade():
    op.drop_index('ix_telas_controladas_chave', table_name='telas_controladas')
    op.drop_table('telas_controladas')
