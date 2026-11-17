"""Nomes de academia nos apelidos do catálogo (lote 4, T3)

"Cadeira extensora", "mesa flexora", "peck deck", "puxada triângulo",
"serrote", "graviton"... não encontravam nada: o catálogo usa o nome
descritivo ("Extensão de perna na máquina de alavanca"). Acrescenta aos
apelidos (exercicios_sistema.nicknames) os nomes usados nas academias do
Brasil para ~50 aparelhos e exercícios comuns, e o nome curto ("Rosca
martelo", "Supino reto") no exercício principal de cada família, para
ele aparecer primeiro na busca.

Só acrescenta (nada é removido nem renomeado) e pode rodar de novo sem
duplicar. O mesmo conteúdo foi gravado em data/exercises.json, para o
script de seed continuar coerente com o banco.

Revision ID: 0aa93ffc7a76
Revises: c4d2a1b9e8f7
Create Date: 2026-11-17 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0aa93ffc7a76'
down_revision = 'c4d2a1b9e8f7'
branch_labels = None
depends_on = None

# id_original -> apelidos acrescentados (conferido: nenhum repete o nome ou
# um apelido de outro exercício)
APELIDOS = {
    '0585': ["Cadeira extensora", "Extensora", "Cadeira de extensão"],
    '0586': ["Mesa flexora", "Flexora deitada", "Flexora deitado"],
    '0599': ["Cadeira flexora", "Flexora sentada", "Flexora sentado"],
    '0597': ["Cadeira abdutora", "Abdutora", "Abdução na máquina"],
    '0598': ["Cadeira adutora", "Adutora", "Adução na máquina"],
    '0228': ["Glúteo na polia", "Glúteo no cabo", "Coice na polia", "Glúteo em pé na polia"],
    '5222': ["Glúteo 4 apoios", "Glúteo quatro apoios", "Coice de glúteo"],
    '0596': ["Peck deck", "Pec deck", "Voador", "Crucifixo máquina", "Voador peitoral"],
    '0602': ["Peck deck invertido", "Voador invertido", "Crucifixo invertido máquina"],
    '0155': ["Crossover", "Cross over", "Crossover na polia"],
    '0198': ["Puxada frontal", "Puxada alta", "Puxada aberta", "Puxada frente", "Pulldown frente"],
    '2616': ["Puxada triângulo", "Puxada com triângulo", "Puxada fechada no triângulo"],
    '0245': ["Puxada supinada"],
    '0180': ["Remada baixa", "Remada sentada no triângulo"],
    '0292': ["Serrote", "Remada serrote", "Remada unilateral", "Remada unilateral com halter"],
    '0606': ["Remada cavalinho", "Cavalinho", "Remada no cavalinho"],
    '0027': ["Remada curvada"],
    '0572': ["Graviton", "Gravitron", "Barra fixa no graviton"],
    '0872': ["Abdominal infra", "Abdominal inferior", "Infra"],
    '2331': ["Elíptico", "Transport", "Transport elíptico"],
    '0336': ["Afundo", "Afundo com halteres"],
    '0054': ["Afundo com barra"],
    '0043': ["Agachamento livre", "Agachamento livre com barra", "Agachamento costas"],
    '0743': ["Hack", "Hack machine", "Agachamento hack"],
    '0739': ["Leg press", "Leg press 45"],
    '0201': ["Tríceps pulley", "Tríceps polia", "Tríceps na polia", "Tríceps barra reta"],
    '0200': ["Tríceps corda", "Tríceps polia com corda", "Tríceps pulley com corda"],
    '0061': ["Tríceps testa", "Tríceps testa com barra"],
    '0814': ["Tríceps banco", "Tríceps no banco"],
    '0251': ["Paralelas", "Mergulho nas paralelas"],
    '0662': ["Flexão de solo", "Apoio de frente"],
    '0605': ["Panturrilha em pé", "Gêmeos em pé", "Panturrilha em pé na máquina"],
    '0594': ["Panturrilha sentado", "Panturrilha sentada", "Sóleo sentado"],
    '0308': ["Crucifixo reto", "Crucifixo reto com halteres"],
    '0313': ["Rosca martelo"],
    '0031': ["Rosca direta", "Rosca direta barra reta"],
    '0070': ["Rosca scott"],
    '0297': ["Rosca concentrada"],
    '1412': ["Rosca punho", "Rosca de punho"],
    '0334': ["Elevação lateral"],
    '0310': ["Elevação frontal"],
    '0405': ["Desenvolvimento com halteres", "Desenvolvimento halteres"],
    '1456': ["Desenvolvimento militar"],
    '0095': ["Encolhimento"],
    '0120': ["Remada alta"],
    '0025': ["Supino reto", "Supino reto barra"],
    '0047': ["Supino inclinado", "Supino inclinado barra"],
    '0033': ["Supino declinado", "Supino declinado barra"],
    '1409': ["Elevação pélvica", "Hip thrust"],
    '0032': ["Levantamento terra", "Terra"],
    '0116': ["Stiff"],
}

_tabela = sa.table(
    'exercicios_sistema',
    sa.column('id', sa.Integer),
    sa.column('id_original', sa.String),
    sa.column('nicknames', sa.JSON),
)


def _linhas(conn):
    return conn.execute(
        sa.select(_tabela.c.id, _tabela.c.id_original, _tabela.c.nicknames)
        .where(_tabela.c.id_original.in_(list(APELIDOS)))
    ).fetchall()


def upgrade():
    conn = op.get_bind()
    for id_, id_original, atuais in _linhas(conn):
        atuais = list(atuais or [])
        existentes = {a.lower() for a in atuais}
        novos = [a for a in APELIDOS[id_original] if a.lower() not in existentes]
        if novos:
            conn.execute(_tabela.update().where(_tabela.c.id == id_).values(nicknames=atuais + novos))


def downgrade():
    conn = op.get_bind()
    for id_, id_original, atuais in _linhas(conn):
        remover = {a.lower() for a in APELIDOS[id_original]}
        restantes = [a for a in (atuais or []) if a.lower() not in remover]
        if len(restantes) != len(atuais or []):
            conn.execute(_tabela.update().where(_tabela.c.id == id_).values(nicknames=restantes))
