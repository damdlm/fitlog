"""Adiciona assinaturas.tier_desatualizado_notificado_em

Guarda a última vez que o professor foi notificado de que o plano de
gestão atual não cobre mais a quantidade de alunos que ele tem (upgrade
necessário) -- controla o intervalo entre lembretes (ver
BillingService.notificar_professores_tier_desatualizado). Sempre None
pra assinatura de aluno (só professor usa isso).

Coluna já existia em models.py (commit 5631f1ab, "feat: notificações de
cancelamento, tier desatualizado e vencimento no dia 0") mas a migration
correspondente nunca foi criada, causando UndefinedColumn em produção
no cron fitlog-cron-billing-carencias.

Revision ID: c935c9397dd0
Revises: d3e4f5a6b7c8
Create Date: 2026-09-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c935c9397dd0'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'assinaturas',
        sa.Column('tier_desatualizado_notificado_em', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('assinaturas', 'tier_desatualizado_notificado_em')