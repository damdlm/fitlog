"""Remove tabela treinos; codigo/created_at passam a viver em treinos_versao

O treino (letra A, B, C...) deixa de ser uma entidade compartilhada entre
versões (tabela `treinos`, reaproveitada via treino_id em cada
treinos_versao) e passa a ser local a cada versão: o campo `codigo` agora
mora diretamente em `treinos_versao`, junto de um novo `created_at`.

Como consequência, `registros_treino` (o histórico de tudo que já foi
registrado) deixa de apontar para `treinos.id` e passa a apontar
diretamente para `treinos_versao.id` -- o que já identifica univocamente
o treino (não precisa mais de versao_id + treino_id combinados).

A tabela `treinos` deixa de ser referenciada por qualquer FK depois desta
migration e é removida.

Estratégia (dados de produção, sem perder histórico):
  1. Adiciona `treinos_versao.codigo` (nullable) e `treinos_versao.created_at`.
  2. Backfill de `codigo` a partir de `treinos.codigo` (via treino_id).
     Backfill de `created_at` a partir de `treinos.created_at` (aproximação:
     não temos o instante exato em que a letra foi vinculada a ESTA
     versão, então usamos a criação original da letra como melhor sinal
     disponível).
  3. Adiciona `registros_treino.treino_versao_id` (nullable), backfill via
     JOIN (registros_treino.versao_id, registros_treino.treino_id) ->
     treinos_versao (que tinha unique constraint em versao_id+treino_id,
     então o match é 1:1).
  4. Torna as colunas novas NOT NULL, ajusta constraints/índices, remove
     as colunas antigas (`treinos_versao.treino_id`,
     `registros_treino.treino_id`) e por fim a tabela `treinos`.

Os nomes reais das constraints de FK são descobertos via
information_schema em vez de hardcoded -- mesma cautela já usada na
migration b2c3d4e5f6a7 (o nome padrão do Postgres pode não bater com o
que está em produção, dependendo de como/quando a tabela foi criada).

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-08-26 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def _nome_fk(conn, tabela, coluna):
    """Descobre o nome real da constraint de FK de `tabela.coluna`."""
    row = conn.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = :tabela
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = :coluna
    """), {"tabela": tabela, "coluna": coluna}).fetchone()
    return row[0] if row else None


def upgrade():
    conn = op.get_bind()

    # --- 1. Novas colunas (nullable por enquanto) ---
    op.add_column('treinos_versao', sa.Column('codigo', sa.String(length=1), nullable=True))
    op.add_column('treinos_versao', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('registros_treino', sa.Column('treino_versao_id', sa.Integer(), nullable=True))

    # --- 2. Backfill de treinos_versao.codigo / created_at a partir de treinos ---
    conn.execute(sa.text("""
        UPDATE treinos_versao tv
        SET codigo = t.codigo,
            created_at = t.created_at
        FROM treinos t
        WHERE tv.treino_id = t.id
    """))

    # --- 3. Backfill de registros_treino.treino_versao_id ---
    conn.execute(sa.text("""
        UPDATE registros_treino r
        SET treino_versao_id = tv.id
        FROM treinos_versao tv
        WHERE tv.versao_id = r.versao_id
          AND tv.treino_id = r.treino_id
    """))

    # --- 4. Constraints/índices antigos (dependem das colunas a remover) ---
    op.drop_constraint('unique_treino_na_versao', 'treinos_versao', type_='unique')
    op.drop_index('idx_treino_versao_treino', table_name='treinos_versao')
    op.drop_index('idx_registro_busca', table_name='registros_treino')

    # --- Colunas novas viram NOT NULL + constraints definitivas ---
    op.alter_column('treinos_versao', 'codigo', existing_type=sa.String(length=1), nullable=False)
    op.alter_column('registros_treino', 'treino_versao_id', existing_type=sa.Integer(), nullable=False)

    op.create_unique_constraint('unique_treino_na_versao', 'treinos_versao', ['versao_id', 'codigo'])
    op.create_index('idx_registro_busca', 'registros_treino', ['user_id', 'treino_versao_id', 'periodo', 'semana'])

    # --- Remove colunas/FKs antigas e a tabela treinos ---
    fk_treinos_versao = _nome_fk(conn, 'treinos_versao', 'treino_id')
    if fk_treinos_versao:
        op.drop_constraint(fk_treinos_versao, 'treinos_versao', type_='foreignkey')
    op.drop_column('treinos_versao', 'treino_id')

    fk_registros_treino = _nome_fk(conn, 'registros_treino', 'treino_id')
    if fk_registros_treino:
        op.drop_constraint(fk_registros_treino, 'registros_treino', type_='foreignkey')
    op.drop_column('registros_treino', 'treino_id')

    op.create_foreign_key(
        'registros_treino_treino_versao_id_fkey', 'registros_treino', 'treinos_versao',
        ['treino_versao_id'], ['id'], ondelete='CASCADE'
    )

    op.drop_table('treinos')


def downgrade():
    # Recria a tabela treinos (dados de codigo/nome/descricao originais
    # não são recuperáveis a partir daqui -- downgrade é só estrutural).
    op.create_table(
        'treinos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=1), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'codigo', name='unique_treino_por_usuario'),
    )
    op.create_index('idx_treino_user', 'treinos', ['user_id'])
    op.create_index('idx_treino_codigo', 'treinos', ['codigo'])

    op.add_column('treinos_versao', sa.Column('treino_id', sa.Integer(), nullable=True))
    op.add_column('registros_treino', sa.Column('treino_id', sa.Integer(), nullable=True))

    conn = op.get_bind()
    fk_rtv = _nome_fk(conn, 'registros_treino', 'treino_versao_id')
    if fk_rtv:
        op.drop_constraint(fk_rtv, 'registros_treino', type_='foreignkey')
    op.drop_index('idx_registro_busca', table_name='registros_treino')
    op.drop_constraint('unique_treino_na_versao', 'treinos_versao', type_='unique')

    op.create_foreign_key(
        'treinos_versao_treino_id_fkey', 'treinos_versao', 'treinos', ['treino_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'registros_treino_treino_id_fkey', 'registros_treino', 'treinos', ['treino_id'], ['id']
    )

    op.create_index('idx_treino_versao_treino', 'treinos_versao', ['treino_id'])
    op.create_index('idx_registro_busca', 'registros_treino', ['user_id', 'treino_id', 'periodo', 'semana'])
    op.create_unique_constraint('unique_treino_na_versao', 'treinos_versao', ['versao_id', 'treino_id'])

    op.alter_column('treinos_versao', 'treino_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('registros_treino', 'treino_id', existing_type=sa.Integer(), nullable=False)

    op.drop_column('registros_treino', 'treino_versao_id')
    op.drop_column('treinos_versao', 'created_at')
    op.drop_column('treinos_versao', 'codigo')
