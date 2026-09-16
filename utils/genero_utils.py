# -*- coding: utf-8 -*-
"""
Inferência opcional de gênero para personalizar mensagens (ex: boas-vindas).

Prioridade sempre é o campo `User.genero`, preenchido pelo próprio usuário
no cadastro ou em Meu Perfil -- é a única fonte confiável. Quando o campo
está vazio, `resolver_genero()` cai numa heurística pelo primeiro nome
(lista de nomes comuns em português + um fallback fraco por terminação).

Isso é só uma heurística de UX (qual mensagem mostrar), nunca um dado
factual do usuário -- não é salvo, não é exibido em nenhuma tela, e erra
em nomes unissex, estrangeiros, apelidos ou abreviações. Quando não dá
pra decidir com confiança, retorna None e quem chamou deve usar uma
mensagem neutra.
"""
import unicodedata

# Nomes masculinos e femininos comuns no Brasil (lista não-exaustiva,
# cobre a maioria dos casos do dia a dia -- ver resolver_genero() para o
# que acontece fora dela).
NOMES_MASCULINOS = {
    'joao', 'jose', 'antonio', 'francisco', 'carlos', 'paulo', 'pedro',
    'lucas', 'luiz', 'marcos', 'luis', 'gabriel', 'rafael', 'daniel',
    'marcelo', 'bruno', 'eduardo', 'felipe', 'raimundo', 'rodrigo',
    'manoel', 'manuel', 'fabio', 'fabiano', 'diego', 'diogo', 'leonardo',
    'guilherme', 'gustavo', 'alexandre', 'anderson', 'andre', 'sergio',
    'thiago', 'tiago', 'roberto', 'renato', 'ricardo', 'vinicius',
    'wellington', 'wesley', 'wagner', 'claudio', 'flavio', 'julio',
    'matheus', 'mateus', 'caio', 'igor', 'henrique', 'edson', 'evandro',
    'douglas', 'leandro', 'alan', 'alessandro', 'adriano', 'cesar',
    'cristiano', 'danilo', 'davi', 'david', 'emerson', 'everton',
    'fernando', 'geraldo', 'gilberto', 'heitor', 'hugo', 'jonas',
    'jonathan', 'jorge', 'juliano', 'kleber', 'leandro', 'marcio',
    'mario', 'mauricio', 'nelson', 'nicolas', 'otavio', 'patrick',
    'rafael', 'reginaldo', 'robson', 'rogerio', 'samuel', 'sandro',
    'valdir', 'vitor', 'victor', 'washington', 'welington', 'wilson',
    'yago', 'caique', 'kaique', 'enzo', 'arthur', 'artur', 'bernardo',
    'benjamin', 'benicio', 'theo', 'miguel', 'noah', 'heitor', 'levi',
    'murilo', 'ryan', 'erick', 'erik', 'breno', 'cauã', 'cauan',
    'emanuel', 'ismael', 'ivan', 'joaquim', 'moises', 'nathan', 'samuel',
    'valentin', 'vicente', 'yuri', 'agnaldo', 'ailton', 'alberto',
    'aldo', 'alex', 'amaro', 'ariovaldo', 'armando', 'aroldo', 'augusto',
    'bento', 'celso', 'clovis', 'dario', 'denis', 'dennis', 'edilson',
    'edmilson', 'elias', 'elton', 'emilio', 'fabricio', 'genivaldo',
    'gerson', 'gilson', 'helio', 'ivo', 'jair', 'jefferson', 'jhonatan',
    'joel', 'josimar', 'juninho', 'kaio', 'lauro', 'leonel', 'marlon',
    'nilton', 'nivaldo', 'osvaldo', 'oswaldo', 'railson', 'reinaldo',
    'ronaldo', 'valdemar', 'valter', 'walter',
}

NOMES_FEMININOS = {
    'maria', 'ana', 'francisca', 'antonia', 'adriana', 'juliana',
    'marcia', 'fernanda', 'patricia', 'aline', 'sandra', 'camila',
    'amanda', 'bruna', 'jessica', 'leticia', 'julia', 'luciana',
    'vanessa', 'mariana', 'gabriela', 'valeria', 'natalia', 'renata',
    'monica', 'priscila', 'raquel', 'daniela', 'carla', 'cristina',
    'viviane', 'simone', 'claudia', 'rosa', 'rosangela', 'sonia',
    'tatiana', 'vera', 'silvia', 'sabrina', 'regiane', 'roberta',
    'andreia', 'andrea', 'debora', 'denise', 'elaine', 'eliane',
    'fabiana', 'giovana', 'giovanna', 'helena', 'ines', 'isabela',
    'isabel', 'jaqueline', 'joana', 'karen', 'karina', 'katia',
    'larissa', 'laura', 'lorena', 'luana', 'luiza', 'manuela',
    'marina', 'michele', 'michelle', 'nathalia', 'natasha', 'paula',
    'rafaela', 'rita', 'sara', 'sheila', 'silvana', 'suellen', 'talita',
    'thais', 'thalita', 'vitoria', 'yasmin', 'yara', 'alice', 'beatriz',
    'clara', 'eloa', 'esther', 'heloisa', 'lara', 'liz', 'manoela',
    'melissa', 'sophia', 'sofia', 'valentina', 'agatha', 'alicia',
    'aurora', 'catarina', 'emilly', 'emily', 'giulia', 'livia', 'lívia',
    'melina', 'mirella', 'nicole', 'olivia', 'pietra', 'rebeca',
    'stella', 'ada', 'adelia', 'adelaide', 'aurea', 'benedita',
    'celia', 'conceicao', 'creusa', 'dalva', 'dirce', 'edna', 'elisa',
    'elza', 'erica', 'eunice', 'ivone', 'ivonete', 'jandira', 'joyce',
    'lucia', 'lucimar', 'magali', 'marlene', 'neide', 'nilza', 'norma',
    'odete', 'penha', 'raimunda', 'rejane', 'rosana', 'rosely',
    'rosilene', 'selma', 'solange', 'tania', 'teresa', 'terezinha',
    'valentina', 'vania', 'vilma', 'zilda', 'zuleide',
}

# Terminações comuns só entram em jogo se o nome não estiver nas listas
# acima -- é um fallback fraco (existem várias exceções em português:
# "Luca", "Guilherme", "Nicolas" etc. não terminam previsivelmente),
# por isso a lista de exceções conhecidas abaixo.
_EXCECOES_TERMINACAO_A = {
    'luca', 'joshua', 'noah', 'ezra', 'elisha', 'joaquim',
}


def _normalizar(texto):
    """minúsculas, sem acento, sem espaço nas pontas."""
    if not texto:
        return ''
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return sem_acento.strip().lower()


def inferir_genero_por_nome(nome_completo):
    """
    Tenta inferir 'M' ou 'F' a partir do primeiro nome. Retorna None
    quando não há confiança suficiente (nome ausente, unissex, fora das
    listas e sem terminação característica).
    """
    if not nome_completo:
        return None

    primeiro_nome = _normalizar(nome_completo).split(' ')[0]
    if not primeiro_nome:
        return None

    if primeiro_nome in NOMES_MASCULINOS:
        return 'M'
    if primeiro_nome in NOMES_FEMININOS:
        return 'F'

    # Fallback fraco por terminação -- só pra nomes fora das listas.
    if primeiro_nome.endswith('a') and primeiro_nome not in _EXCECOES_TERMINACAO_A:
        return 'F'
    if primeiro_nome.endswith(('o', 'r', 'im', 'el')):
        return 'M'

    return None


def resolver_genero(user):
    """
    Resolve o gênero a usar para personalizar mensagens: prioriza o
    campo explícito do usuário (`user.genero`) e só cai na heurística
    por nome se ele não tiver preenchido.
    """
    if getattr(user, 'genero', None) in ('M', 'F'):
        return user.genero
    return inferir_genero_por_nome(getattr(user, 'nome_completo', None))
