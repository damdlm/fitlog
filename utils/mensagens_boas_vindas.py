# -*- coding: utf-8 -*-
"""
Mensagens de boas-vindas exibidas no login, sorteadas aleatoriamente e
separadas por gênero (ver utils/genero_utils.py:resolver_genero).

`{nome}` é substituído pelo nome de exibição do usuário (nome_completo
ou username). Sempre existe uma lista NEUTRA -- usada sempre que não dá
pra resolver o gênero com confiança (campo vazio + heurística de nome
sem match), então nunca falta mensagem por causa disso.
"""
import random

MENSAGENS_MASCULINO = [
    "E aí, meu chapa!",
    "Fala, patrão!",
    "Salve, chefe!",
    "E aí, brabo!",
    "Salve, meu nobre!",
    "E aí, cidadão!",
    "Fala, mestre!",
    "E aí, fenômeno!",
    "Salve, monstro!",
    "Fala, frango!",
    "E aí, patrãozinho!",
    "Fala, meu rei!",
    "Opa, fala comandante!",
    "Salve, magnata!",
    "Fala, lenda!",
]

MENSAGENS_FEMININO = [
    "E aí, gata!",
    "Salve, rainha!",
    "Opa, a diva chegou!",
    "Oii, poderosa!",
    "E aí, musa!",
    "Fala, linda!",
    "Oii, maravilhosa!",
    "Salve, princesa!",
    "Fala, bonita!",
    "E ai, marombinha!",
    "Salve, patroa!",
    "Fala, diva!",
    "Oii gata!",
    "Fala, musa!",
    "Salve, poderosa!",
    "Fala, mulher de milhões!",
    "Salve, diva suprema!",
    "Fala, obra-prima!",
    "Salve, lindeza problemática!",
]

MENSAGENS_NEUTRO = [
    "Fala, criatura!",
    "E aí, lenda!",
    "Fala, fera!",
    "E aí, máquina!",
    "Salve, fenômeno!",
    "Fala, gigante!",
    "Opa, lenda!",
]


def gerar_mensagem_boas_vindas(nome, genero):
    """
    Sorteia uma mensagem de boas-vindas para `nome`, usando a lista
    correspondente a `genero` ('M', 'F' ou qualquer outra coisa/None
    para a lista neutra).
    """
    if genero == 'M':
        lista = MENSAGENS_MASCULINO
    elif genero == 'F':
        lista = MENSAGENS_FEMININO
    else:
        lista = MENSAGENS_NEUTRO

    return random.choice(lista).format(nome=nome)
