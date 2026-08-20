"""Cria tabelas de cobrança/assinatura (planos, assinaturas, eventos_webhook_asaas)

Introduz o modelo de cobrança do fitlog: planos de professor por faixa
de alunos (Pró/Premium) e plano do aluno (Fit) com trial de 30 dias.
O estado de cada assinatura é sempre escrito a partir de webhooks
validados do Asaas, nunca a partir de uma resposta direta ao navegador
(ver services/billing_service.py e models.py:Assinatura).

Semeia os 3 planos combinados com o usuário (professor_pro,
professor_premium, aluno_fit) como dado inicial -- assim a aplicação já
sobe com os planos existindo, sem depender de alguém rodar um script
manual à parte.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta, timezone

# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


planos_table = sa.table(
    'planos',
    sa.column('codigo', sa.String),
    sa.column('nome', sa.String),
    sa.column('tipo_usuario', sa.String),
    sa.column('preco_centavos', sa.Integer),
    sa.column('min_alunos', sa.Integer),
    sa.column('max_alunos', sa.Integer),
    sa.column('ativo', sa.Boolean),
)


def upgrade():
    op.create_table(
        'planos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('codigo', sa.String(length=30), nullable=False),
        sa.Column('nome', sa.String(length=60), nullable=False),
        sa.Column('tipo_usuario', sa.String(length=20), nullable=False),
        sa.Column('preco_centavos', sa.Integer(), nullable=False),
        sa.Column('min_alunos', sa.Integer(), nullable=True),
        sa.Column('max_alunos', sa.Integer(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_planos_codigo', 'planos', ['codigo'], unique=True)

    op.create_table(
        'assinaturas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plano_id', sa.Integer(), sa.ForeignKey('planos.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='trialing'),
        sa.Column('gateway_customer_id', sa.String(length=60), nullable=True),
        sa.Column('gateway_subscription_id', sa.String(length=60), nullable=True),
        sa.Column('trial_termina_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('periodo_atual_fim', sa.DateTime(timezone=True), nullable=True),
        sa.Column('carencia_termina_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_assinaturas_usuario_id', 'assinaturas', ['usuario_id'], unique=True)
    op.create_index('ix_assinaturas_status', 'assinaturas', ['status'])
    op.create_index('ix_assinaturas_gateway_subscription_id', 'assinaturas', ['gateway_subscription_id'])

    op.create_table(
        'eventos_webhook_asaas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.String(length=80), nullable=False),
        sa.Column('tipo_evento', sa.String(length=60), nullable=False),
        sa.Column('processado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_eventos_webhook_asaas_event_id', 'eventos_webhook_asaas', ['event_id'], unique=True)

    # Planos iniciais -- valores combinados em 19/08/2026. Faixa de 0-2
    # alunos do professor fica de fora de propósito: é a faixa gratuita,
    # sem linha de Plano associada (ver BillingService.calcular_tier_professor).
    op.bulk_insert(planos_table, [
        {
            'codigo': 'professor_pro',
            'nome': 'Plano Pró',
            'tipo_usuario': 'professor',
            'preco_centavos': 2990,
            'min_alunos': 3,
            'max_alunos': 10,
            'ativo': True,
        },
        {
            'codigo': 'professor_premium',
            'nome': 'Plano Premium',
            'tipo_usuario': 'professor',
            'preco_centavos': 9990,
            'min_alunos': 11,
            'max_alunos': None,
            'ativo': True,
        },
        {
            'codigo': 'aluno_fit',
            'nome': 'Plano Fit',
            'tipo_usuario': 'aluno',
            'preco_centavos': 599,
            'min_alunos': None,
            'max_alunos': None,
            'ativo': True,
        },
    ])


    # Backfill: usuários que já são alunos ANTES deste deploy precisam
    # de uma Assinatura em trial -- sem isso, Assinatura.acesso_premium_
    # ativo() (models.py) não encontra nenhuma linha pra eles e os
    # bloqueia de Estatísticas/FitBot IMEDIATAMENTE ao subir esta
    # migration, sem os 30 dias de trial que a regra de negócio promete
    # a todo aluno. Dá o mesmo trial de 30 dias a partir de AGORA pra
    # quem já era aluno antes desta migration -- alunos criados DEPOIS
    # já ganham o trial no próprio cadastro (ver
    # BillingService.iniciar_trial_aluno, chamado em auth_routes.py,
    # professor_routes.py e aluno_service.py), então não duplicam aqui.
    connection = op.get_bind()
    agora = datetime.now(timezone.utc)
    trial_fim = agora + timedelta(days=30)

    usuarios_table = sa.table(
        'users',
        sa.column('id', sa.Integer),
        sa.column('tipo_usuario', sa.String),
    )
    assinaturas_table_backfill = sa.table(
        'assinaturas',
        sa.column('usuario_id', sa.Integer),
        sa.column('status', sa.String),
        sa.column('trial_termina_em', sa.DateTime),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )

    alunos_existentes = connection.execute(
        sa.select(usuarios_table.c.id).where(usuarios_table.c.tipo_usuario == 'aluno')
    ).fetchall()

    if alunos_existentes:
        op.bulk_insert(assinaturas_table_backfill, [
            {
                'usuario_id': row.id,
                'status': 'trialing',
                'trial_termina_em': trial_fim,
                'created_at': agora,
                'updated_at': agora,
            }
            for row in alunos_existentes
        ])


def downgrade():
    op.drop_index('ix_eventos_webhook_asaas_event_id', table_name='eventos_webhook_asaas')
    op.drop_table('eventos_webhook_asaas')

    op.drop_index('ix_assinaturas_gateway_subscription_id', table_name='assinaturas')
    op.drop_index('ix_assinaturas_status', table_name='assinaturas')
    op.drop_index('ix_assinaturas_usuario_id', table_name='assinaturas')
    op.drop_table('assinaturas')

    op.drop_index('ix_planos_codigo', table_name='planos')
    op.drop_table('planos')
