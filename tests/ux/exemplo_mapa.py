"""Exemplo de simulação: mapa muscular da Ana nos três cenários.

    python -m tests.ux.exemplo_mapa
"""
from tests.ux.harness import Sessao

for cenario in ('cel', 'escuro', 'desk'):
    with Sessao(cenario) as s:
        pg = s.entrar('ana')
        pg.goto(s.url('/aluno/estatisticas'))
        pg.wait_for_selector('#mapaMuscular .mm-r')
        print(cenario, '| séries:', s.texto(pg, '#mapaMuscular .mm-painel')[:80])
        pg.click('#mapaMuscular .mm-aba[data-aba="recuperacao"]')
        print(cenario, '| recuperação:', s.texto(pg, '#mapaMuscular .mm-painel')[:80])
        print(cenario, '| largura', s.largura(pg), '| erros', s.erros(pg))
