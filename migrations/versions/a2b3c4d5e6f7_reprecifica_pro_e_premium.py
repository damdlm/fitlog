"""Reprecifica Plano Pró (R$29,90 -> R$10,90) e Plano Premium
(R$99,90 -> R$29,90)

Muda só o preco_centavos das duas linhas em `planos` -- faixas de
alunos (min_alunos/max_alunos) não são alteradas por esta migration.

Assinaturas já ATIVAS via cartão não são tocadas automaticamente pelo
Asaas: o valor recorrente que o gateway cobra é o que foi fixado na
subscription no momento da criação/último update
(atualizar_valor_assinatura), não algo lido do nosso banco a cada
ciclo. Pra quem já está pagando o valor antigo passar a pagar o novo,
seria necessário chamar atualizar_valor_assinatura() pra cada
assinatura ativa dos planos afetados (fora do escopo desta migration,
que só corrige o preço de tabela usado em cobranças NOVAS a partir de
agora -- checkout novo, upgrade/downgrade de faixa, Pix avulso).

Revision ID: a2b3c4d5e6f7
Revises: c7d8e9f0a1b2
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None

PRECO_ANTIGO_PRO = 2990
PRECO_NOVO_PRO = 1090
PRECO_ANTIGO_PREMIUM = 9990
PRECO_NOVO_PREMIUM = 2990


def upgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE planos SET preco_centavos = :preco WHERE codigo = 'professor_pro'"),
        {'preco': PRECO_NOVO_PRO},
    )
    connection.execute(
        sa.text("UPDATE planos SET preco_centavos = :preco WHERE codigo = 'professor_premium'"),
        {'preco': PRECO_NOVO_PREMIUM},
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE planos SET preco_centavos = :preco WHERE codigo = 'professor_pro'"),
        {'preco': PRECO_ANTIGO_PRO},
    )
    connection.execute(
        sa.text("UPDATE planos SET preco_centavos = :preco WHERE codigo = 'professor_premium'"),
        {'preco': PRECO_ANTIGO_PREMIUM},
    )