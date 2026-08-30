"""Simplifica de volta pra 2 faixas de professor (Pró até 10 alunos,
Premium ilimitado a partir de 11) e remove o ciclo anual -- reversão
parcial de d2e3f4a5b6c7_add_pix_ciclo_anual_e_plano_plus, decisão de
produto: só cobrança mensal (cartão recorrente ou Pix avulso pra
ativar o plano por ~30 dias, ver services/billing_service.py).

Revision ID: e7f8a9b0c1d2
Revises: 22250725ed4f
Create Date: 2026-08-30 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = '22250725ed4f'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    # Quem estava no Plano Plus (10-19 alunos) volta a fazer parte do
    # Premium -- é a faixa mais próxima que ainda cobre a contagem
    # dele. Feito ANTES de apagar a linha do Plano Plus, pra nenhuma
    # assinatura ficar apontando pra um plano_id que não existe mais.
    premium_id = connection.execute(
        sa.text("SELECT id FROM planos WHERE codigo = 'professor_premium'")
    ).scalar()
    plus_id = connection.execute(
        sa.text("SELECT id FROM planos WHERE codigo = 'professor_plus'")
    ).scalar()
    if plus_id and premium_id:
        connection.execute(
            sa.text("UPDATE assinaturas SET plano_id = :premium_id WHERE plano_id = :plus_id"),
            {'premium_id': premium_id, 'plus_id': plus_id},
        )
    if plus_id:
        connection.execute(sa.text("DELETE FROM planos WHERE id = :plus_id"), {'plus_id': plus_id})

    connection.execute(sa.text("UPDATE planos SET max_alunos = 10 WHERE codigo = 'professor_pro'"))
    connection.execute(sa.text("UPDATE planos SET min_alunos = 11 WHERE codigo = 'professor_premium'"))

    op.drop_column('assinaturas', 'ciclo')


def downgrade():
    op.add_column('assinaturas', sa.Column('ciclo', sa.String(length=10), nullable=False, server_default='mensal'))

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE planos SET max_alunos = 9 WHERE codigo = 'professor_pro'"))
    connection.execute(sa.text("UPDATE planos SET min_alunos = 20 WHERE codigo = 'professor_premium'"))

    planos_table = sa.table(
        'planos',
        sa.column('codigo', sa.String),
        sa.column('nome', sa.String),
        sa.column('tipo_usuario', sa.String),
        sa.column('preco_centavos', sa.Integer),
        sa.column('min_alunos', sa.Integer),
        sa.column('max_alunos', sa.Integer),
        sa.column('ativo', sa.Boolean),
        sa.column('created_at', sa.DateTime),
    )
    op.bulk_insert(planos_table, [{
        'codigo': 'professor_plus',
        'nome': 'Plano Plus',
        'tipo_usuario': 'professor',
        'preco_centavos': 5990,
        'min_alunos': 10,
        'max_alunos': 19,
        'ativo': True,
        'created_at': datetime.now(timezone.utc),
    }])
