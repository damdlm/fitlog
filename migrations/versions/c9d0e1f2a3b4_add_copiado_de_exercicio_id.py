"""Adiciona exercicios_usuario.copiado_de_professor_id e copiado_de_exercicio_id

Consolida duas migrações que deveriam ter sido commitadas em sequência:
a que cria copiado_de_professor_id (usada pela propagação automática --
quando um professor cadastra um exercício próprio, uma cópia é criada
pra cada aluno vinculado a ele, ver ExercicioService.criar_exercicio_customizado)
e a que cria copiado_de_exercicio_id (auto-referência pro exercício
ESPECÍFICO de origem, usada pra propagar EDIÇÕES do professor pras
cópias já existentes, ver ExercicioService._propagar_edicao_para_alunos
-- copiado_de_professor_id sozinho só diz quem é o professor, não dá
pra re-encontrar de qual exercício veio a cópia depois que o professor
renomeia o original).

A primeira delas foi escrita e usada localmente numa sessão anterior,
mas nunca chegou a ser commitada no repositório -- só a segunda (que
dependia dela) foi, deixando a cadeia do Alembic quebrada (apontando
pra uma revisão inexistente) e derrubando o deploy. Esta migração junta
as duas num só arquivo válido.

Cada bloco confere se a coluna/constraint/índice já existe antes de
criar (idempotente) -- não dá pra saber com certeza, só pelo
repositório, se copiado_de_professor_id chegou a ser aplicada
manualmente no banco em algum momento; assim a migração funciona nos
dois cenários sem quebrar.

ondelete='SET NULL' nos dois FKs porque a cópia do aluno é
independente -- some só a referência de origem, não o exercício do
aluno, se o professor (ou o exercício original) for removido.

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
Create Date: 2026-08-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _colunas_existentes(inspector, tabela):
    return {c['name'] for c in inspector.get_columns(tabela)}


def _colunas_com_fk(inspector, tabela):
    """Conjunto de colunas que já têm QUALQUER foreign key apontando
    pra fora delas nesta tabela -- checagem por coluna, não por nome de
    constraint. Evita criar uma constraint duplicada (mesmo efeito,
    nome diferente) caso a coluna já tenha sido criada por outro
    caminho -- por exemplo, se em algum momento ela foi adicionada via
    db.create_all() direto (que nomeia a FK automaticamente, diferente
    do nome que esta migração usaria)."""
    colunas = set()
    for fk in inspector.get_foreign_keys(tabela):
        colunas.update(fk['constrained_columns'])
    return colunas


def _indices_existentes(inspector, tabela):
    return {ix['name'] for ix in inspector.get_indexes(tabela)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    colunas = _colunas_existentes(inspector, 'exercicios_usuario')
    colunas_com_fk = _colunas_com_fk(inspector, 'exercicios_usuario')
    indices = _indices_existentes(inspector, 'exercicios_usuario')

    if 'copiado_de_professor_id' not in colunas:
        op.add_column(
            'exercicios_usuario',
            sa.Column('copiado_de_professor_id', sa.Integer(), nullable=True),
        )
    if 'copiado_de_professor_id' not in colunas_com_fk:
        op.create_foreign_key(
            'fk_exercicios_usuario_copiado_de_professor_id',
            'exercicios_usuario', 'users',
            ['copiado_de_professor_id'], ['id'],
            ondelete='SET NULL',
        )

    if 'copiado_de_exercicio_id' not in colunas:
        op.add_column(
            'exercicios_usuario',
            sa.Column('copiado_de_exercicio_id', sa.Integer(), nullable=True),
        )
    if 'copiado_de_exercicio_id' not in colunas_com_fk:
        op.create_foreign_key(
            'fk_exercicios_usuario_copiado_de_exercicio_id',
            'exercicios_usuario', 'exercicios_usuario',
            ['copiado_de_exercicio_id'], ['id'],
            ondelete='SET NULL',
        )
    if 'idx_exercicio_usuario_copiado_de_exercicio' not in indices:
        op.create_index(
            'idx_exercicio_usuario_copiado_de_exercicio',
            'exercicios_usuario', ['copiado_de_exercicio_id'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indices = _indices_existentes(inspector, 'exercicios_usuario')
    colunas = _colunas_existentes(inspector, 'exercicios_usuario')

    def _nome_fk_da_coluna(tabela, coluna):
        for fk in sa.inspect(bind).get_foreign_keys(tabela):
            if coluna in fk['constrained_columns']:
                return fk['name']
        return None

    if 'idx_exercicio_usuario_copiado_de_exercicio' in indices:
        op.drop_index('idx_exercicio_usuario_copiado_de_exercicio', table_name='exercicios_usuario')

    nome_fk = _nome_fk_da_coluna('exercicios_usuario', 'copiado_de_exercicio_id')
    if nome_fk:
        op.drop_constraint(nome_fk, 'exercicios_usuario', type_='foreignkey')
    if 'copiado_de_exercicio_id' in colunas:
        op.drop_column('exercicios_usuario', 'copiado_de_exercicio_id')

    nome_fk = _nome_fk_da_coluna('exercicios_usuario', 'copiado_de_professor_id')
    if nome_fk:
        op.drop_constraint(nome_fk, 'exercicios_usuario', type_='foreignkey')
    if 'copiado_de_professor_id' in colunas:
        op.drop_column('exercicios_usuario', 'copiado_de_professor_id')