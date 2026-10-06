"""Evolução do Volume sem dados -- vale para as duas páginas de estatísticas
(a do aluno e a do aluno vista pelo professor).

Comportamento: sem dados, o JS esconde a CAIXA do gráfico (.est-chart-wrap, de
altura fixa), não só o canvas, e mostra um aviso compacto (#evolucaoVazio).
Com dados de novo, a caixa volta ANTES de o gráfico ser recriado (o Chart.js
mede o tamanho do contêiner na criação: num contêiner escondido sairia 0x0).
"""
import re
from html.parser import HTMLParser

import pytest

TEMPLATES = {
    'aluno': 'templates/aluno/estatisticas.html',
    'professor': 'templates/professor/estatisticas_aluno.html',
}

_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
         'meta', 'param', 'source', 'track', 'wbr'}


def _ler(chave):
    with open(TEMPLATES[chave], encoding='utf-8') as arq:
        return arq.read()


@pytest.fixture(params=sorted(TEMPLATES))
def template(request):
    return _ler(request.param)


class _Ancestrais(HTMLParser):
    """Guarda, para o elemento com o id pedido, as classes de todos os ancestrais."""

    def __init__(self, id_alvo):
        super().__init__()
        self.id_alvo = id_alvo
        self.pilha = []
        self.ancestrais = None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get('id') == self.id_alvo and self.ancestrais is None:
            self.ancestrais = [c for _, cls in self.pilha for c in cls]
        if tag not in _VOID:
            self.pilha.append((tag, (d.get('class') or '').split()))

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break


def test_aviso_de_vazio_fica_fora_da_caixa_que_e_escondida(template):
    # Se o aviso estivesse DENTRO de .est-chart-wrap, esconder a caixa
    # esconderia o aviso junto e o card ficaria sem nada.
    p = _Ancestrais('evolucaoVazio')
    p.feed(template)
    assert p.ancestrais is not None, 'falta o elemento #evolucaoVazio'
    assert 'est-chart-wrap' not in p.ancestrais


def test_sem_dados_esconde_a_caixa_do_grafico_e_nao_so_o_canvas(template):
    assert "canvas.parentElement.style.display = semDados ? 'none' : ''" in template
    assert "getElementById('evolucaoVazio').style.display = semDados ? 'block' : 'none'" in template


def test_caixa_volta_a_aparecer_antes_de_recriar_o_grafico(template):
    mostrar = template.index("canvas.parentElement.style.display = semDados ? 'none' : ''")
    criar = template.index('evolucaoChart = new Chart(')
    assert mostrar < criar


def test_aviso_de_vazio_e_compacto(template):
    regra = re.search(r'#evolucaoVazio\s*\{(.*?)\}', template, re.S)
    assert regra, 'falta a regra que compacta o aviso de vazio'
    # menos padding que o .est-empty padrão (40px 20px)
    assert 'padding: 18px 10px' in regra.group(1)


def test_erro_de_rede_na_pagina_do_professor_tambem_esconde_a_caixa():
    html = _ler('professor')
    assert "getElementById('evolucaoChart').parentElement.style.display = 'none'" in html
    assert "getElementById('evolucaoVazio').style.display = 'block'" in html