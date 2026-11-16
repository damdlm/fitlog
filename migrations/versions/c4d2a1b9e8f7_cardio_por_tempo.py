"""Cardio registrado por tempo (com distância e intensidade opcionais)

- exercicios_usuario.modo_registro e exercicios_sistema.modo_registro:
  'carga' (padrão, como sempre) ou 'tempo'.
- historico_treino: carga e repeticoes passam a aceitar NULL (série de
  cardio não tem); novas colunas duracao_segundos, distancia_km e
  intensidade.
- Catálogo: marca como 'tempo' os cardios de máquina/corrida que já
  existiam e acrescenta Esteira, Bicicleta ergométrica, Spinning, Remo
  ergômetro, Caminhada, Natação e Escada (simulador). Os dados ficam
  aqui (e em data/exercises.json) para chegarem a produção sem depender
  de rodar o seed à mão. Ver services/cardio.py.

Revision ID: c4d2a1b9e8f7
Revises: b7c3e9f1a2d4
Create Date: 2026-11-16 12:00:00.000000
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = 'c4d2a1b9e8f7'
down_revision = 'b7c3e9f1a2d4'
branch_labels = None
depends_on = None

IDS_ORIGINAIS_POR_TEMPO = ('2331', '2612', '0685', '0684', '2138', '0798',
                           '2141', '3666', '2311', '5225', '5227', '5228')

NOVOS = [
    ('9001', 'Esteira', ['Corrida na esteira', 'Caminhada na esteira', 'Treadmill'], 'Esteira',
     'Ajuste a velocidade e a inclinação aos poucos. Mantenha o tronco ereto, olhe para a frente e evite apoiar as mãos nas barras laterais.'),
    ('9002', 'Bicicleta ergométrica', ['Bike', 'Bicicleta', 'Bike ergométrica'], 'Bicicleta ergométrica',
     'Regule o banco na altura do quadril, com o joelho quase estendido no ponto mais baixo do pedal. Pedale em ritmo constante.'),
    ('9003', 'Spinning', ['Bike indoor', 'Ciclismo indoor', 'Bike de spinning'], 'Bicicleta de spinning',
     'Ajuste banco e guidão antes de começar. Alterne a carga e a cadência conforme a aula ou o seu plano.'),
    ('9004', 'Remo ergômetro', ['Remo', 'Remada no remo', 'Rowing'], 'Remo ergômetro',
     'Empurre primeiro com as pernas, depois incline o tronco e puxe com os braços. Volte na ordem inversa, sem pressa.'),
    ('9005', 'Caminhada', ['Caminhada ao ar livre', 'Andar', 'Walking'], 'Nenhum',
     'Caminhe em ritmo que eleve a respiração sem impedir de conversar. Use calçado confortável.'),
    ('9006', 'Natação', ['Nadar', 'Piscina', 'Swimming'], 'Piscina',
     'Aqueça com braçadas leves e mantenha o ritmo respiratório. Alterne estilos se quiser variar o esforço.'),
    ('9007', 'Escada (simulador)', ['Escada', 'Simulador de escada', 'Stair climber', 'Escada rolante'], 'Simulador de escada',
     'Mantenha o tronco ereto e apoie o pé inteiro em cada degrau. Use o corrimão só para equilíbrio.'),
]


def upgrade():
    op.add_column('exercicios_usuario', sa.Column(
        'modo_registro', sa.String(10), nullable=False, server_default='carga'))
    op.add_column('exercicios_sistema', sa.Column(
        'modo_registro', sa.String(10), nullable=False, server_default='carga'))

    with op.batch_alter_table('historico_treino') as batch:
        batch.alter_column('carga', existing_type=sa.Numeric(5, 1), nullable=True)
        batch.alter_column('repeticoes', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('duracao_segundos', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('distancia_km', sa.Numeric(6, 2), nullable=True))
        batch.add_column(sa.Column('intensidade', sa.String(10), nullable=True))

    sistema = sa.table(
        'exercicios_sistema',
        sa.column('id_original', sa.String), sa.column('nome', sa.String),
        sa.column('categoria', sa.String), sa.column('parte_corpo', sa.String),
        sa.column('equipamento', sa.String), sa.column('instrucao_pt', sa.Text),
        sa.column('passos_pt', sa.JSON), sa.column('grupo_muscular', sa.String),
        sa.column('musculos_secundarios', sa.JSON), sa.column('nicknames', sa.JSON),
        sa.column('alvo', sa.String), sa.column('modo_registro', sa.String),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    conn = op.get_bind()
    conn.execute(
        sistema.update()
        .where(sistema.c.id_original.in_(IDS_ORIGINAIS_POR_TEMPO))
        .values(modo_registro='tempo')
    )
    existentes = {
        linha[0] for linha in conn.execute(
            sa.select(sistema.c.id_original).where(sistema.c.id_original.in_([n[0] for n in NOVOS]))
        )
    }
    agora = datetime.now(timezone.utc)
    novos = [{
        'id_original': id_original, 'nome': nome, 'categoria': 'Cardio', 'parte_corpo': 'Cardio',
        'equipamento': equipamento, 'instrucao_pt': instrucao, 'passos_pt': [instrucao],
        'grupo_muscular': 'Cardio', 'musculos_secundarios': [], 'nicknames': apelidos,
        'alvo': 'Sistema cardiovascular', 'modo_registro': 'tempo', 'created_at': agora,
    } for id_original, nome, apelidos, equipamento, instrucao in NOVOS if id_original not in existentes]
    if novos:
        op.bulk_insert(sistema, novos)


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM exercicios_sistema WHERE id_original IN ('9001','9002','9003','9004','9005','9006','9007') "
        "AND id NOT IN (SELECT exercicio_base_id FROM registros_treino WHERE exercicio_base_id IS NOT NULL) "
        "AND id NOT IN (SELECT exercicio_base_id FROM versao_exercicios WHERE exercicio_base_id IS NOT NULL)"
    ))
    # Séries de cardio não têm carga/repetições: sem isso o NOT NULL abaixo falha.
    conn.execute(sa.text("DELETE FROM historico_treino WHERE carga IS NULL OR repeticoes IS NULL"))
    with op.batch_alter_table('historico_treino') as batch:
        batch.drop_column('intensidade')
        batch.drop_column('distancia_km')
        batch.drop_column('duracao_segundos')
        batch.alter_column('repeticoes', existing_type=sa.Integer(), nullable=False)
        batch.alter_column('carga', existing_type=sa.Numeric(5, 1), nullable=False)
    op.drop_column('exercicios_sistema', 'modo_registro')
    op.drop_column('exercicios_usuario', 'modo_registro')
