"""Cria tabela telas_controladas_professor (bloqueio configurável
pelo admin das telas agregadas de gestão de alunos do professor)

Grupo SEPARADO da tabela telas_controladas já existente -- aquela
cobre o gate de assinatura Fit/Pró/Premium ativa (Estatísticas/
FitBot/etc, via BillingService.usuario_tem_acesso_premium); esta aqui
cobre a regra de limite de alunos + inadimplência do professor (mais
de 2 alunos e assinatura 'blocked' -- ver
BillingService.professor_acesso_alunos_liberado e
utils/decorators.py:professor_acesso_tela_required).

Antes desta migration, Painel/Meus Alunos/Novo Aluno/Solicitações já
estavam bloqueadas incondicionalmente pra professor inadimplente
(sem passar por nenhuma tela de configuração do admin). Semeia as 4
já com bloqueia_sem_plano=True pra preservar exatamente esse
comportamento -- ninguém que já usava o app ganha acesso por engano;
o admin decide dali em diante se quer liberar alguma individualmente
em /admin/telas-controladas.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


telas_professor_table = sa.table(
    'telas_controladas_professor',
    sa.column('chave', sa.String),
    sa.column('nome_exibicao', sa.String),
    sa.column('bloqueia_sem_plano', sa.Boolean),
)


def upgrade():
    op.create_table(
        'telas_controladas_professor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chave', sa.String(length=50), nullable=False),
        sa.Column('nome_exibicao', sa.String(length=100), nullable=False),
        sa.Column('bloqueia_sem_plano', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_telas_controladas_professor_chave', 'telas_controladas_professor', ['chave'], unique=True)

    op.bulk_insert(telas_professor_table, [
        {'chave': 'professor_dashboard', 'nome_exibicao': 'Painel', 'bloqueia_sem_plano': True},
        {'chave': 'professor_meus_alunos', 'nome_exibicao': 'Meus Alunos', 'bloqueia_sem_plano': True},
        {'chave': 'professor_novo_aluno', 'nome_exibicao': 'Novo Aluno', 'bloqueia_sem_plano': True},
        {'chave': 'professor_solicitacoes', 'nome_exibicao': 'Solicitações', 'bloqueia_sem_plano': True},
    ])


def downgrade():
    op.drop_index('ix_telas_controladas_professor_chave', table_name='telas_controladas_professor')
    op.drop_table('telas_controladas_professor')
