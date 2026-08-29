"""Adiciona forma de pagamento (Pix)/ciclo anual/dados de cartão em
assinaturas, e cria a faixa intermediária Plano Plus (10-19 alunos)

Três mudanças:

  1. `assinaturas` ganha forma_pagamento ('cartao'/'pix'), ciclo
     ('mensal'/'anual') e cartao_ultimos_digitos/cartao_bandeira (só
     exibição). Ver services/billing_service.py.

  2. Nova faixa "Plano Plus" pra professor com 10-19 alunos
     (R$59,90/mês) -- fecha o salto grande que existia de R$29,90
     (Pró, até 9) direto pra R$99,90 (Premium, que hoje começa em 10).

  3. Plano Premium passa a valer a partir de 20 alunos (era 10). Quem
     hoje está no Premium com 10-19 alunos cai pro Plus no próximo
     ciclo de verificação de tier (verificar_mudancas_tier_professores)
     -- é uma REDUÇÃO de valor, então não precisa do aviso prévio de 1
     ciclo que upgrades exigem (mesmo raciocínio já documentado em
     verificar_mudancas_tier_professores: só upgrade precisa de aviso
     antes de aplicar; downgrade de preço não surpreende o pagador de
     forma negativa).

Revision ID: d2e3f4a5b6c7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-29 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assinaturas', sa.Column('forma_pagamento', sa.String(length=10), nullable=False, server_default='cartao'))
    op.add_column('assinaturas', sa.Column('ciclo', sa.String(length=10), nullable=False, server_default='mensal'))
    op.add_column('assinaturas', sa.Column('cartao_ultimos_digitos', sa.String(length=4), nullable=True))
    op.add_column('assinaturas', sa.Column('cartao_bandeira', sa.String(length=30), nullable=True))

    connection = op.get_bind()

    # Plano Premium passa a começar em 20 alunos (era 10).
    connection.execute(sa.text("UPDATE planos SET min_alunos = 20 WHERE codigo = 'professor_premium'"))

    # Nova faixa Plus, entre Pró (3-9) e Premium (agora 20+).
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
    ja_existe = connection.execute(
        sa.text("SELECT 1 FROM planos WHERE codigo = 'professor_plus'")
    ).first()
    if not ja_existe:
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


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM planos WHERE codigo = 'professor_plus'"))
    connection.execute(sa.text("UPDATE planos SET min_alunos = 10 WHERE codigo = 'professor_premium'"))

    op.drop_column('assinaturas', 'cartao_bandeira')
    op.drop_column('assinaturas', 'cartao_ultimos_digitos')
    op.drop_column('assinaturas', 'ciclo')
    op.drop_column('assinaturas', 'forma_pagamento')
