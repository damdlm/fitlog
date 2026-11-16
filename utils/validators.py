"""Módulo de validações para a aplicação"""

import re

def validar_treino_id(treino_id):
    """
    Valida se o ID do treino é uma letra maiúscula única
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not treino_id:
        return False, "ID do treino é obrigatório"
    
    treino_id = treino_id.strip().upper()
    
    if len(treino_id) != 1:
        return False, "ID deve ter exatamente 1 caractere"
    
    if not treino_id.isalpha():
        return False, "ID deve ser uma letra"
    
    return True, treino_id

def validar_semana(semana):
    """
    Valida se o número da semana é válido (1-52)
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        semana_int = int(semana)
        if semana_int < 1 or semana_int > 52:
            return False, "Semana deve estar entre 1 e 52"
        return True, semana_int
    except (ValueError, TypeError):
        return False, "Semana deve ser um número válido"

def validar_carga(carga):
    """
    Valida se a carga é um número positivo
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        carga_float = float(carga)
        if carga_float < 0:
            return False, "Carga não pode ser negativa"
        if carga_float > 999:
            return False, "Carga muito alta (máx 999kg)"
        return True, carga_float
    except (ValueError, TypeError):
        return False, "Carga deve ser um número válido"

def validar_repeticoes(repeticoes):
    """
    Valida se o número de repetições é um inteiro positivo
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        reps_int = int(repeticoes)
        if reps_int < 0:
            return False, "Repetições não podem ser negativas"
        if reps_int > 100:
            return False, "Número de repetições muito alto (máx 100)"
        return True, reps_int
    except (ValueError, TypeError):
        return False, "Repetições devem ser um número válido"

def validar_num_series(num_series):
    """
    Valida se o número de séries é um inteiro entre 1 e 10
    Retorna (bool, mensagem_erro ou valor validado)
    """
    try:
        series_int = int(num_series)
        if series_int < 1 or series_int > 10:
            return False, "Número de séries deve estar entre 1 e 10"
        return True, series_int
    except (ValueError, TypeError):
        return False, "Número de séries deve ser um número válido"

def validar_periodo(periodo):
    """
    Valida se o período está no formato correto (ex: Janeiro/2024)
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not periodo:
        return False, "Período é obrigatório"
    
    # Padrão: Mês/Ano ou Mês Ano
    padrao = re.match(r'^([A-Za-zçãõáéíóú]+)[/\s]+(\d{4})$', periodo.strip())
    if not padrao:
        return False, "Formato inválido. Use: Mês/Ano (ex: Janeiro/2024)"
    
    return True, periodo.strip()

def validar_email(email):
    """
    Valida formato de email
    Retorna (bool, mensagem_erro ou valor validado)
    """
    if not email:
        return False, "Email é obrigatório"
    
    padrao = re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)
    if not padrao:
        return False, "Email inválido"
    
    return True, email

# Senhas mais usadas (pt-BR e globais) que passariam nas regras de
# tamanho/letra/número. Comparação em minúsculas.
SENHAS_COMUNS = frozenset({
    'senha123', 'senha1234', 'senha12345', 'senha@123', 'senha#123', 'mudar123', 'mudar@123',
    'abc12345', 'abcd1234', 'abc123456', 'qwerty123', 'qwerty1234', 'qwer1234', 'asdf1234',
    'password1', 'password12', 'password123', 'passw0rd', 'p@ssw0rd', 'p@ssword1', 'admin123',
    'admin1234', 'teste123', 'teste1234', 'usuario123', 'brasil123', 'brasil2020', 'brasil2024',
    'brasil2025', 'brasil2026', 'fitlog123', 'fitlog1234', 'treino123', 'treino1234', 'academia1',
    'academia123', 'flamengo1', 'flamengo123', 'corinthians1', 'palmeiras1', 'saopaulo1',
    'gremio123', 'vasco1898', 'iloveyou1', 'iloveyou123', 'welcome1', 'welcome123', 'letmein123',
    'monkey123', 'dragon123', 'master123', 'football1', 'baseball1', 'superman1', 'princesa1',
    'princesa123', 'amor12345', 'meuamor123', 'minhasenha1', 'minhasenha123', 'trocar123',
    'a1b2c3d4', 'a1234567', 'a12345678', 'aa123456', '1q2w3e4r', '1qaz2wsx', '123456789a',
    'a123456789', 'abcdefg1', 'qwertyui1', '12345678a', '1234567a', 'senha2020', 'senha2021',
    'senha2022', 'senha2023', 'senha2024', 'senha2025', 'senha2026',
})


# Senhas sem número que também são óbvias (agora que letra + número não é
# mais exigido para contas comuns). Comparação em minúsculas.
SENHAS_COMUNS_SEM_NUMERO = frozenset({
    'password', 'senhasenha', 'minhasenha', 'senhaforte', 'iloveyou', 'princesa',
    'flamengo', 'corinthians', 'palmeiras', 'saopaulo', 'academia', 'treinando',
    'qwertyui', 'qwertyuiop', 'asdfghjk', 'asdfghjkl', 'zxcvbnm', 'abcdefgh',
    'abcdefghij', 'fitlogfitlog', 'brasilbrasil', 'trocarsenha', 'mudarsenha',
    'bemvindo', 'welcome', 'sunshine', 'football', 'baseball', 'superman',
    'batman', 'starwars', 'pokemon', 'dragonball', 'naruto', 'futebol', 'jesuscristo',
    'deusefiel', 'amorzinho', 'meuamor', 'teamo', 'teamomuito', 'gabriela', 'fernanda',
})

# Sequências de teclado/alfabeto/números: qualquer trecho de 8+ delas
# (ex.: 12345678, 87654321, abcdefgh, qwertyui) é previsível.
_SEQUENCIAS = ('0123456789', 'abcdefghijklmnopqrstuvwxyz', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm')


def _senha_previsivel(senha):
    sl = senha.lower()
    if sl in SENHAS_COMUNS or sl in SENHAS_COMUNS_SEM_NUMERO:
        return True
    if len(set(sl)) <= 2:
        return True
    # Repetição de um bloco curto: 12341234, abcabcab, haha haha...
    for tam in range(1, 5):
        bloco = sl[:tam]
        if bloco and (bloco * (len(sl) // tam + 1))[:len(sl)] == sl:
            return True
    for seq in _SEQUENCIAS:
        if sl in seq or sl in seq[::-1]:
            return True
    return False


# Texto exibido ao usuário (cadastro, troca e recuperação de senha).
REQUISITOS_SENHA = (
    "Pelo menos 8 caracteres",
    "Não ser uma senha óbvia (ex.: 12345678, senha123)",
    "Não conter a parte do e-mail antes do @",
)


def erros_senha(senha, username=None, email=None, rigida=False):
    """Lista TODOS os motivos pelos quais a senha é recusada ([] = válida).

    Regra comum (alunos e professores) segue a recomendação atual (NIST
    SP 800-63B): tamanho mínimo + bloquear senhas óbvias, sem exigir
    "letra e número" (regra de composição que irrita e pouco protege).
    rigida=True (contas admin) mantém as exigências antigas: letra,
    número e não conter o nome de usuário.
    """
    if not senha:
        return ["Senha é obrigatória"]

    erros = []
    if len(senha) < 8:
        erros.append("Senha deve ter pelo menos 8 caracteres")
    if rigida:
        if not re.search(r'[A-Za-z]', senha):
            erros.append("Senha deve conter pelo menos uma letra")
        if not re.search(r'[0-9]', senha):
            erros.append("Senha deve conter pelo menos um número")
    if _senha_previsivel(senha):
        erros.append("Essa senha é muito comum ou previsível. Escolha outra.")
    if rigida and username and len(username) >= 3 and username.lower() in senha.lower():
        erros.append("A senha não pode conter o seu nome de usuário")
    if email and len(email.split('@')[0]) >= 4 and email.split('@')[0].lower() in senha.lower():
        erros.append("A senha não pode conter o seu e-mail")
    return erros


def validar_senha(senha, username=None, email=None, rigida=False):
    """
    Valida se a senha atende aos requisitos mínimos.
    Retorna (bool, mensagem_erro ou valor validado). Em caso de vários
    problemas devolve o primeiro; use erros_senha() para obter todos.
    """
    erros = erros_senha(senha, username=username, email=email, rigida=rigida)
    if erros:
        return False, erros[0]
    return True, senha


# Nome de usuário escolhido/editado pela pessoa: minúsculas, números,
# ponto e sublinhado. Nunca "@" -- o login trata "@" como e-mail.
USERNAME_REGEX = re.compile(r'^[a-z0-9._]{3,30}$')


def validar_username(username):
    """(ok, mensagem) para um nome de usuário novo ou editado."""
    if not username:
        return False, 'Informe um nome de usuário.'
    if not USERNAME_REGEX.match(username):
        return False, ('O nome de usuário deve ter de 3 a 30 caracteres: letras '
                       'minúsculas sem acento, números, ponto ou sublinhado.')
    return True, username


def gerar_username(nome, email, existe):
    """Gera um nome de usuário a partir do NOME (não do e-mail: o usuário
    aparece para outras pessoas, ex.: no ranking, quando não há nome).
    "Maria José Souza" -> "maria.souza"; se ocupado, "maria.souza2", ...
    `existe(candidato) -> bool` consulta a unicidade."""
    import unicodedata

    def limpar(texto):
        texto = unicodedata.normalize('NFKD', texto or '')
        texto = ''.join(c for c in texto if not unicodedata.combining(c)).lower()
        return re.sub(r'[^a-z0-9]+', ' ', texto).split()

    partes = limpar(nome)
    if len(partes) >= 2:
        base = f'{partes[0]}.{partes[-1]}'
    elif partes:
        base = partes[0]
    else:
        base = ''.join(limpar((email or '').split('@')[0])) or 'usuario'
    base = base[:24].strip('.') or 'usuario'
    if len(base) < 3:
        base = (base + 'fit')[:24]

    if not existe(base):
        return base
    for sufixo in range(2, 10000):
        candidato = f'{base}{sufixo}'
        if not existe(candidato):
            return candidato
    import secrets
    return f'{base}{secrets.randbelow(10**6)}'


def corpo_json_objeto():
    """Corpo JSON da requisição como dict -- {} quando ausente, inválido ou
    de outro tipo (ex.: uma lista). Evita 500 (AttributeError em .get) com
    requisições malformadas; a rota responde 400 pela validação normal."""
    from flask import request
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else {}
