"""Corrige FK de exercicio_base_id: exercicios_base -> exercicios_sistema

Equivalente ao scripts/migrar_para_exercicios_sistema.py, agora como
migração Alembic de verdade -- roda automaticamente no deploy (ver
Procfile: `release: alembic upgrade head`), em vez de depender de alguém
lembrar de rodar o script manualmente via `railway run`.

Idempotente: usa IF EXISTS / DROP CONSTRAINT IF EXISTS, pode rodar mais
de uma vez sem erro (inclusive se scripts/migrar_para_exercicios_sistema.py
já tiver sido rodado manualmente antes -- nesse caso essa migração não
encontra a constraint antiga e só confirma que a nova já existe).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10 00:00:00.000000
"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

TABELAS = ["versao_exercicios", "registros_treino"]


def upgrade():
    conn = op.get_bind()

    for tabela in TABELAS:
        # 1. Descobrir o nome real da constraint de FK atual sobre exercicio_base_id
        constraint_row = conn.execute(text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = :tabela
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'exercicio_base_id'
        """), {"tabela": tabela}).fetchone()

        # 2. Zerar referências órfãs (ids de exercicios_base que não existem
        #    em exercicios_sistema) -- evita violação de FK ao criar a nova
        #    constraint, já que exercicios_base e exercicios_sistema são
        #    catálogos de fontes diferentes e os ids não coincidem.
        conn.execute(text(f"""
            UPDATE {tabela}
            SET exercicio_base_id = NULL
            WHERE exercicio_base_id IS NOT NULL
              AND exercicio_base_id NOT IN (SELECT id FROM exercicios_sistema)
        """))

        # 3. Remover constraint antiga (se existir)
        if constraint_row:
            nome_constraint = constraint_row[0]
            conn.execute(text(
                f'ALTER TABLE {tabela} DROP CONSTRAINT IF EXISTS "{nome_constraint}"'
            ))

        # 4. Criar a nova constraint apontando para exercicios_sistema
        nova_constraint = f"{tabela}_exercicio_base_id_exercicios_sistema_fkey"
        conn.execute(text(f"""
            ALTER TABLE {tabela} DROP CONSTRAINT IF EXISTS "{nova_constraint}"
        """))
        conn.execute(text(f"""
            ALTER TABLE {tabela}
            ADD CONSTRAINT "{nova_constraint}"
            FOREIGN KEY (exercicio_base_id)
            REFERENCES exercicios_sistema(id)
            ON DELETE CASCADE
        """))


def downgrade():
    # Não implementado de propósito: reverter exigiria saber o nome exato
    # da constraint antiga (variava por ambiente) e garantir que a tabela
    # exercicios_base ainda existe e contém os ids referenciados -- não é
    # seguro assumir isso automaticamente. Se precisar reverter, trate como
    # incidente manual, com dump do banco antes.
    pass