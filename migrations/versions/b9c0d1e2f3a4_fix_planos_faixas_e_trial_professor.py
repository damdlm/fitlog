"""Corrige faixa de alunos do Plano Pró/Premium e dá trial de 30 dias para professores existentes

Duas mudanças de regra de negócio:

  1. Faixas corrigidas: Plano Pró cobre 3 a 9 alunos (antes ia até 10);
     Plano Premium passa a valer a partir de 10 alunos (antes era a
     partir de 11). Confirmado com o usuário -- ver conversa que gerou
     esta migration.

  2. Professor agora TAMBÉM precisa do Plano Fit (ou trial) pra acessar
     Estatísticas/FitBot -- antes ele era isento. Sem backfill, todo
     professor já cadastrado ficaria bloqueado dessas telas IMEDIATAMENTE
     ao subir esta migration, sem nenhum trial (mesmo raciocínio do
     backfill de alunos na migration a7b8c9d0e1f2). Dá 30 dias de trial
     a partir de agora pra quem ainda não tem nenhuma Assinatura.

Um professor tem UMA ÚNICA linha em `assinaturas` (não duas) -- o
mesmo registro que hoje representa "sem plano" pode depois passar a
representar Plano Fit, Pró ou Premium, conforme a quantidade de alunos
e o que ele assinar. Ver services/billing_service.py.

Revision ID: b9c0d1e2f3a4
Revises: c9d0e1f2a3b4
Create Date: 2026-08-21 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta, timezone

# revision identifiers, used by Alembic.
revision = 'b9c0d1e2f3a4'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None

TRIAL_DIAS = 30


def upgrade():
    connection = op.get_bind()

    # 1. Corrige as faixas de alunos dos planos de professor.
    connection.execute(sa.text("UPDATE planos SET max_alunos = 9 WHERE codigo = 'professor_pro'"))
    connection.execute(sa.text("UPDATE planos SET min_alunos = 10 WHERE codigo = 'professor_premium'"))

    # 2. Backfill: trial de 30 dias pra todo professor que ainda não
    #    tem nenhuma Assinatura (nunca teve, já que antes desta
    #    migration só alunos ganhavam trial no cadastro).
    agora = datetime.now(timezone.utc)
    trial_fim = agora + timedelta(days=TRIAL_DIAS)

    usuarios_table = sa.table('users', sa.column('id', sa.Integer), sa.column('tipo_usuario', sa.String))
    assinaturas_table = sa.table(
        'assinaturas',
        sa.column('usuario_id', sa.Integer),
        sa.column('status', sa.String),
        sa.column('trial_termina_em', sa.DateTime),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )

    professores = connection.execute(
        sa.select(usuarios_table.c.id).where(usuarios_table.c.tipo_usuario == 'professor')
    ).fetchall()
    ja_tem_assinatura = {
        row.usuario_id for row in connection.execute(
            sa.select(assinaturas_table.c.usuario_id)
        ).fetchall()
    }

    novos = [
        {
            'usuario_id': row.id,
            'status': 'trialing',
            'trial_termina_em': trial_fim,
            'created_at': agora,
            'updated_at': agora,
        }
        for row in professores if row.id not in ja_tem_assinatura
    ]
    if novos:
        op.bulk_insert(assinaturas_table, novos)


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE planos SET max_alunos = 10 WHERE codigo = 'professor_pro'"))
    connection.execute(sa.text("UPDATE planos SET min_alunos = 11 WHERE codigo = 'professor_premium'"))
    # Não desfaz o backfill de trial -- remover assinaturas de trial já
    # concedidas seria mais destrutivo que útil num rollback.
