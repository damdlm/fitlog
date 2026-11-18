"""Fichas prontas para começar (lote 6c, E2).

Modelos criados em um toque na tela de ficha (aluno sem ficha ativa) e na
"Nova ficha" do professor para um aluno. Depois de criada, a ficha é uma
ficha comum: tudo pode ser editado, trocado ou apagado.

Cada exercício aponta para o "id" do data/exercises.json (coluna
exercicios_sistema.id_original), que não muda entre ambientes -- o id
numérico do banco muda. Formato: (id_original, séries, reps mín., reps máx.).
Um exercício que não existir no catálogo é simplesmente pulado.
"""

FICHAS_PRONTAS = [
    {
        'slug': 'iniciante-abc',
        'nome': 'Iniciante ABC',
        'detalhe': '3 treinos · academia · 3× por semana',
        'resumo': 'Máquinas e movimentos simples para aprender a execução, '
                  'com 3 séries de 12 em quase tudo.',
        'treinos': [
            {'nome': 'Peito, ombro e tríceps', 'exercicios': [
                ('0577', 3, 12, 12),   # Supino na máquina
                ('0314', 3, 12, 12),   # Supino inclinado com halteres
                ('0603', 3, 12, 12),   # Desenvolvimento na máquina
                ('0334', 3, 12, 12),   # Elevação lateral com halteres
                ('0200', 3, 12, 12),   # Tríceps na polia com corda
            ]},
            {'nome': 'Costas e bíceps', 'exercicios': [
                ('0579', 3, 12, 12),   # Puxada frontal na máquina
                ('1350', 3, 12, 12),   # Remada sentada na máquina
                ('0292', 3, 12, 12),   # Remada unilateral com halter
                ('0031', 3, 12, 12),   # Rosca direta com barra
                ('0313', 3, 12, 12),   # Rosca martelo
            ]},
            {'nome': 'Pernas e abdômen', 'exercicios': [
                ('0739', 3, 12, 12),   # Leg press 45°
                ('0585', 3, 12, 12),   # Cadeira extensora
                ('0599', 3, 12, 12),   # Cadeira flexora
                ('0605', 3, 15, 15),   # Panturrilha em pé na máquina
                ('0274', 3, 15, 15),   # Abdominal supra no chão
            ]},
        ],
    },
    {
        'slug': 'hipertrofia-abc',
        'nome': 'Hipertrofia ABC',
        'detalhe': '3 treinos · academia · 3 a 6× por semana',
        'resumo': 'Mais volume e pesos livres, de 8 a 15 repetições, '
                  'para quem já treina há alguns meses.',
        'treinos': [
            {'nome': 'Peito, ombro e tríceps', 'exercicios': [
                ('0025', 4, 8, 10),    # Supino reto com barra
                ('0314', 4, 10, 12),   # Supino inclinado com halteres
                ('0596', 3, 12, 15),   # Crucifixo na máquina (voador)
                ('0405', 4, 8, 12),    # Desenvolvimento sentado com halteres
                ('0334', 3, 12, 15),   # Elevação lateral com halteres
                ('0061', 3, 10, 12),   # Tríceps testa com barra
                ('0200', 3, 12, 15),   # Tríceps na polia com corda
            ]},
            {'nome': 'Costas e bíceps', 'exercicios': [
                ('0198', 4, 8, 12),    # Puxada na polia
                ('0027', 4, 8, 10),    # Remada curvada com barra
                ('0861', 3, 10, 12),   # Remada sentada com cabo
                ('0292', 3, 10, 12),   # Remada unilateral com halter
                ('0602', 3, 12, 15),   # Crucifixo invertido na máquina
                ('0031', 3, 8, 12),    # Rosca direta com barra
                ('0313', 3, 10, 12),   # Rosca martelo
            ]},
            {'nome': 'Pernas', 'exercicios': [
                ('0043', 4, 8, 10),    # Agachamento livre com barra
                ('0739', 4, 10, 12),   # Leg press 45°
                ('0085', 4, 8, 12),    # Stiff (terra romeno com barra)
                ('0585', 3, 12, 15),   # Cadeira extensora
                ('0586', 3, 10, 12),   # Mesa flexora
                ('1409', 3, 10, 12),   # Elevação pélvica com barra
                ('0594', 4, 12, 15),   # Panturrilha sentado na máquina
            ]},
        ],
    },
    {
        'slug': 'em-casa',
        'nome': 'Em casa',
        'detalhe': '2 treinos · sem equipamento · 3× por semana',
        'resumo': 'Só o peso do corpo, um banco ou cadeira e uma mesa firme. '
                  'Alterne A e B.',
        'treinos': [
            {'nome': 'Superiores e abdômen', 'exercicios': [
                ('0662', 3, 8, 15),    # Flexão de braço
                ('0493', 3, 10, 15),   # Flexão de braço inclinada
                ('2300', 3, 8, 12),    # Remada invertida (joelhos dobrados)
                ('0129', 3, 10, 15),   # Mergulho no banco (joelhos dobrados)
                ('0630', 3, 20, 20),   # Escalador
                ('0274', 3, 15, 20),   # Abdominal supra no chão
            ]},
            {'nome': 'Pernas e condicionamento', 'exercicios': [
                ('2368', 3, 10, 12),   # Agachamento búlgaro
                ('1460', 3, 12, 12),   # Avanço caminhando
                ('0484', 3, 15, 15),   # Ponte de glúteos
                ('1373', 3, 20, 20),   # Panturrilha em pé
                ('0514', 3, 12, 12),   # Agachamento com salto
                ('1160', 3, 10, 10),   # Burpee
            ]},
        ],
    },
    {
        'slug': 'full-body',
        'nome': 'Full body',
        'detalhe': '2 treinos · academia · 2 a 3× por semana',
        'resumo': 'O corpo todo em cada treino. Bom para quem tem poucos dias '
                  'na semana. Alterne A e B.',
        'treinos': [
            {'nome': 'Corpo todo A', 'exercicios': [
                ('1760', 3, 10, 12),   # Agachamento goblet com halter
                ('0289', 3, 10, 12),   # Supino reto com halteres
                ('0198', 3, 10, 12),   # Puxada na polia
                ('1459', 3, 10, 12),   # Terra romeno com halteres
                ('0405', 3, 10, 12),   # Desenvolvimento sentado com halteres
                ('0274', 3, 15, 15),   # Abdominal supra no chão
            ]},
            {'nome': 'Corpo todo B', 'exercicios': [
                ('0739', 3, 10, 12),   # Leg press 45°
                ('0314', 3, 10, 12),   # Supino inclinado com halteres
                ('0861', 3, 10, 12),   # Remada sentada com cabo
                ('0336', 3, 10, 10),   # Avanço com halteres
                ('0334', 3, 12, 15),   # Elevação lateral com halteres
                ('0285', 3, 10, 12),   # Rosca alternada com halteres
                ('0200', 3, 12, 15),   # Tríceps na polia com corda
            ]},
        ],
    },
]

FICHAS_POR_SLUG = {f['slug']: f for f in FICHAS_PRONTAS}
