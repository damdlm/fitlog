"""Catálogo Gif do Treino: correções depois da revisão das animações

Revisão visual dos 494 exercícios novos da a3c7e9b1d5f2:
- equipamento errado em 39 (ex.: snatch e hang clean marcados como peso
  corporal ou cabo; exercícios com gymstick sem a faixa elástica);
- músculo-alvo errado em 23 (ex.: crucifixo inverso como peitoral ou
  trapézio, flexão de braço com joelhos como quadríceps);
- 16 nomes ajustados: em inglês (o nome antigo vira apelido, para a busca
  continuar achando), com erro de digitação ou ambíguos;
- 8039 "Caminhada na parada de mão" deixa de ser cardio (registro por carga);
- 8446 "Agachamento frontal" e 8463 "Bom dia" eram outro ângulo de 0042 e
  0044: o 0042 ganha a animação HD do 8446 e os dois saem do catálogo
  (se alguém já usou, ficam como "v. 2").

Revision ID: b5d8f2a4c6e1
Revises: a3c7e9b1d5f2
Create Date: 2026-11-24 17:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b5d8f2a4c6e1'
down_revision = 'a3c7e9b1d5f2'
branch_labels = None
depends_on = None

# id_original -> {coluna: [valor antigo, valor novo]}
CORRECOES = {'8037': {'alvo': ['Quadríceps', 'Dorsais'],
          'categoria': ['Pernas superiores', 'Costas'],
          'parte_corpo': ['Pernas superiores', 'Costas']},
 '8039': {'alvo': ['Sistema cardiovascular', 'Deltoides'],
          'categoria': ['Cardio', 'Ombros'],
          'modo_registro': ['tempo', 'carga'],
          'parte_corpo': ['Cardio', 'Ombros']},
 '8044': {'alvo': ['Isquiotibiais', 'Glúteos']},
 '8062': {'alvo': ['Quadríceps', 'Peitorais'],
          'categoria': ['Pernas superiores', 'Peito'],
          'equipamento': ['Halter', 'Peso corporal'],
          'nome': ['Flexão de joelhos', 'Flexão de braço com joelhos apoiados'],
          'parte_corpo': ['Pernas superiores', 'Peito']},
 '8071': {'alvo': ['Deltoides', 'Tríceps'],
          'categoria': ['Ombros', 'Braços'],
          'parte_corpo': ['Ombros', 'Braços']},
 '8072': {'alvo': ['Abdômen', 'Tríceps'],
          'categoria': ['Cintura', 'Braços'],
          'parte_corpo': ['Cintura', 'Braços']},
 '8110': {'equipamento': ['Cabo', 'Barra']},
 '8113': {'nome': ['Arremesso de medicina bola com levantamento de tronco',
                   'Arremesso de bola medicinal com levantamento de tronco']},
 '8114': {'equipamento': ['Peso corporal', 'Barra'],
          'nicknames': [[], ['Barbell hang clean']],
          'nome': ['Barbell hang clean', 'Hang clean com barra']},
 '8116': {'alvo': ['Deltoides', 'Quadríceps'],
          'categoria': ['Ombros', 'Pernas superiores'],
          'parte_corpo': ['Ombros', 'Pernas superiores']},
 '8118': {'equipamento': ['Kettlebell', 'Barra'],
          'nome': ['Carregamento Zercher', 'Carregamento Zercher com barra']},
 '8120': {'nicknames': [[], ['Dumbbell devil press']],
          'nome': ['Dumbbell devil press', 'Devil press com halteres']},
 '8121': {'nicknames': [[], ['Dumbbell power clean']],
          'nome': ['Dumbbell power clean', 'Power clean com halteres']},
 '8124': {'equipamento': ['Peso corporal', 'Barra'],
          'nicknames': [[], ['Heaving snatch balance']],
          'nome': ['Heaving snatch balance', 'Snatch balance com barra']},
 '8129': {'equipamento': ['Cabo', 'Barra'],
          'nicknames': [[], ['Muscle snatch']],
          'nome': ['Muscle snatch', 'Muscle snatch com barra']},
 '8131': {'alvo': ['Costas superiores', 'Glúteos'],
          'categoria': ['Costas', 'Pernas superiores'],
          'parte_corpo': ['Costas', 'Pernas superiores']},
 '8132': {'alvo': ['Abdômen', 'Glúteos'],
          'categoria': ['Cintura', 'Pernas superiores'],
          'parte_corpo': ['Cintura', 'Pernas superiores']},
 '8133': {'equipamento': ['Halter', 'Com peso']},
 '8144': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8160': {'equipamento': ['Peso corporal', 'Medicine ball']},
 '8162': {'alvo': ['Quadríceps', 'Deltoides'],
          'categoria': ['Pernas superiores', 'Ombros'],
          'parte_corpo': ['Pernas superiores', 'Ombros']},
 '8163': {'alvo': ['Quadríceps', 'Deltoides'],
          'categoria': ['Pernas superiores', 'Ombros'],
          'parte_corpo': ['Pernas superiores', 'Ombros']},
 '8169': {'equipamento': ['Máquina de alavanca', 'Peso corporal']},
 '8171': {'nome': ['Corrida latera', 'Corrida lateral']},
 '8178': {'alvo': ['Peitorais', 'Deltoides'],
          'categoria': ['Peito', 'Ombros'],
          'equipamento': ['Peso corporal', 'Faixa elástica'],
          'parte_corpo': ['Peito', 'Ombros']},
 '8180': {'nome': ['Cópia de abdominal de rã com bola de exercícios',
                   'Abdominal sapo com bola de exercício']},
 '8182': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8184': {'equipamento': ['Halter', 'Peso corporal']},
 '8185': {'alvo': ['Deltoides', 'Glúteos'],
          'categoria': ['Ombros', 'Pernas superiores'],
          'parte_corpo': ['Ombros', 'Pernas superiores']},
 '8186': {'alvo': ['Deltoides', 'Glúteos'],
          'categoria': ['Ombros', 'Pernas superiores'],
          'parte_corpo': ['Ombros', 'Pernas superiores']},
 '8194': {'equipamento': ['Halter', 'Peso corporal']},
 '8195': {'alvo': ['Peitorais', 'Abdômen'],
          'categoria': ['Peito', 'Cintura'],
          'parte_corpo': ['Peito', 'Cintura']},
 '8196': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8201': {'alvo': ['Quadríceps', 'Glúteos'],
          'equipamento': ['Máquina de alavanca', 'Peso corporal'],
          'nome': ['Extensão de perna reta', 'Extensão de quadril em quatro apoios com perna reta']},
 '8204': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8214': {'alvo': ['Peitorais', 'Deltoides'],
          'categoria': ['Peito', 'Ombros'],
          'parte_corpo': ['Peito', 'Ombros']},
 '8216': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8223': {'equipamento': ['Máquina de alavanca', 'Faixa elástica']},
 '8241': {'alvo': ['Dorsais', 'Deltoides'],
          'categoria': ['Costas', 'Ombros'],
          'parte_corpo': ['Costas', 'Ombros']},
 '8243': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8248': {'equipamento': ['Peso corporal', 'Com peso']},
 '8268': {'equipamento': ['Peso corporal', 'Faixa elástica']},
 '8280': {'nome': ['Gluteos coice nilateral polia baixa', 'Glúteo coice unilateral na polia baixa']},
 '8295': {'equipamento': ['Faixa elástica', 'Peso corporal']},
 '8347': {'equipamento': ['Halter', 'Peso corporal']},
 '8348': {'equipamento': ['Halter', 'Peso corporal']},
 '8349': {'equipamento': ['Halter', 'Peso corporal']},
 '8350': {'alvo': ['Peitorais', 'Glúteos'],
          'categoria': ['Peito', 'Pernas superiores'],
          'parte_corpo': ['Peito', 'Pernas superiores']},
 '8354': {'alvo': ['Deltoides', 'Quadríceps'],
          'categoria': ['Ombros', 'Pernas superiores'],
          'parte_corpo': ['Ombros', 'Pernas superiores']},
 '8384': {'equipamento': ['Halter', 'Peso corporal']},
 '8387': {'equipamento': ['Halter', 'Peso corporal']},
 '8390': {'alvo': ['Deltoides', 'Isquiotibiais'],
          'categoria': ['Ombros', 'Pernas superiores'],
          'parte_corpo': ['Ombros', 'Pernas superiores']},
 '8408': {'equipamento': ['Peso corporal', 'Halter']},
 '8417': {'equipamento': ['Peso corporal', 'Com peso']},
 '8433': {'equipamento': ['Peso corporal', 'Barra'],
          'nome': ['Supino com pegada aberta', 'Supino com barra pegada aberta']},
 '8435': {'equipamento': ['Peso corporal', 'Halter']},
 '8446': {'equipamento': ['Peso corporal', 'Barra']},
 '8452': {'equipamento': ['Peso corporal', 'Barra']},
 '8463': {'equipamento': ['Peso corporal', 'Barra']},
 '8464': {'alvo': ['Panturrilhas', 'Quadríceps'],
          'categoria': ['Pernas inferiores', 'Pernas superiores'],
          'parte_corpo': ['Pernas inferiores', 'Pernas superiores']},
 '8471': {'equipamento': ['Halter', 'Barra']},
 '8478': {'equipamento': ['Halter', 'Barra'],
          'nome': ['Encolhimento acima da cabeça', 'Encolhimento acima da cabeça com barra']},
 '8483': {'alvo': ['Trapézio', 'Deltoides'],
          'categoria': ['Costas', 'Ombros'],
          'nome': ['Remada invertida com cable inclinado', 'Crucifixo inverso curvado no cabo'],
          'parte_corpo': ['Costas', 'Ombros']},
 '8484': {'equipamento': ['Halter', 'Cabo']},
 '8490': {'equipamento': ['Peso corporal', 'Barra'], 'nome': ['Supino fechado', 'Supino fechado com barra']}}

# 0042 recebe a animação HD do 8446: id -> [antes, depois] de (gif_url, imagem)
MIDIA = {
    '0042': [['videos/0042-zG0zs85.gif', 'images/0042-zG0zs85.jpg'],
             ['videos/gdt/agachamento-frontal-ba00153.mp4', 'images/gdt/agachamento-frontal-48b2aba.webp']],
}

# Duplicados de exercícios que já existiam: id -> nome se já tiver sido usado
DUPLICADOS = {'8446': 'Agachamento frontal com barra v. 2', '8463': 'Bom dia com barra v. 2'}

sistema = sa.table(
    'exercicios_sistema',
    sa.column('id', sa.Integer), sa.column('id_original', sa.String), sa.column('nome', sa.String),
    sa.column('categoria', sa.String), sa.column('parte_corpo', sa.String),
    sa.column('equipamento', sa.String), sa.column('nicknames', sa.JSON),
    sa.column('alvo', sa.String), sa.column('modo_registro', sa.String),
    sa.column('imagem', sa.String), sa.column('gif_url', sa.String),
)

_USADOS = (
    "id IN (SELECT exercicio_base_id FROM registros_treino WHERE exercicio_base_id IS NOT NULL) "
    "OR id IN (SELECT exercicio_base_id FROM versao_exercicios WHERE exercicio_base_id IS NOT NULL)"
)


def _aplicar(conn, lado):
    for fid, campos in CORRECOES.items():
        valores = {col: par[lado] for col, par in campos.items()}
        conn.execute(sistema.update().where(sistema.c.id_original == fid).values(**valores))
    for fid, par in MIDIA.items():
        gif, img = par[lado]
        conn.execute(sistema.update().where(sistema.c.id_original == fid).values(gif_url=gif, imagem=img))


def upgrade():
    conn = op.get_bind()
    _aplicar(conn, 1)
    ids = list(DUPLICADOS)
    # Já usados em ficha/registro: ficam, com nome de variação.
    for fid, nome in DUPLICADOS.items():
        conn.execute(
            sa.text(f"UPDATE exercicios_sistema SET nome = :nome WHERE id_original = :fid AND ({_USADOS})"),
            {'nome': nome, 'fid': fid},
        )
    conn.execute(
        sa.text(f"DELETE FROM exercicios_sistema WHERE id_original IN :ids AND NOT ({_USADOS})")
        .bindparams(sa.bindparam('ids', expanding=True)),
        {'ids': ids},
    )


def downgrade():
    # Os duplicados apagados não voltam (o downgrade da a3c7e9b1d5f2 os
    # apagaria de qualquer forma); o resto volta ao valor anterior.
    _aplicar(op.get_bind(), 0)