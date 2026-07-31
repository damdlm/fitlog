"""
Migra as FKs de exercicio_base_id (em versao_exercicios e registros_treino)
de exercicios_base para exercicios_sistema.

Uso:
    railway run python scripts/migrar_para_exercicios_sistema.py

O que este script faz, nessa ordem:
    1. Para cada tabela (versao_exercicios, registros_treino), zera
       (seta NULL) qualquer exercicio_base_id que não exista como id em
       exercicios_sistema — evita violação de FK ao criar a nova
       constraint (exercicios_base e exercicios_sistema são catálogos de
       fontes diferentes, os ids não coincidem).
    2. Remove a constraint de FK antiga (que apontava para exercicios_base).
    3. Cria a nova constraint de FK apontando para exercicios_sistema(id).

Idempotente: pode ser executado mais de uma vez sem erro (usa
IF EXISTS / DROP CONSTRAINT IF EXISTS).

IMPORTANTE: rode isso ANTES de fazer deploy do models.py atualizado, ou
logo em seguida — enquanto a constraint antiga existir, o app não vai
conseguir gravar exercicio_base_id apontando para exercicios_sistema.
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app          # noqa: E402
from models import db               # noqa: E402

TABELAS = ["versao_exercicios", "registros_treino"]


def migrar():
    app = create_app()
    with app.app_context():
        conn = db.session.connection()

        for tabela in TABELAS:
            print(f"\n=== {tabela} ===")

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

            # 2. Zerar referências órfãs (ids de exercicios_base que não existem em exercicios_sistema)
            resultado = conn.execute(text(f"""
                UPDATE {tabela}
                SET exercicio_base_id = NULL
                WHERE exercicio_base_id IS NOT NULL
                  AND exercicio_base_id NOT IN (SELECT id FROM exercicios_sistema)
            """))
            print(f"  {resultado.rowcount} referência(s) órfã(s) zerada(s)")

            # 3. Remover constraint antiga (se existir)
            if constraint_row:
                nome_constraint = constraint_row[0]
                conn.execute(text(
                    f'ALTER TABLE {tabela} DROP CONSTRAINT IF EXISTS "{nome_constraint}"'
                ))
                print(f"  constraint antiga removida: {nome_constraint}")
            else:
                print("  nenhuma constraint de FK antiga encontrada (ok, já migrado?)")

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
            print(f"  nova constraint criada: {nova_constraint} -> exercicios_sistema(id)")

        db.session.commit()
        print("\n✅ Migração concluída.")


if __name__ == "__main__":
    migrar()
