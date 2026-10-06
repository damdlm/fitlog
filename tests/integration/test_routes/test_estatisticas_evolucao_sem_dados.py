"""Evolução do Volume sem dados: a mensagem de vazio ocupa o lugar do gráfico
(dentro da caixa de altura fixa), em vez de ficar embaixo de uma caixa em
branco -- senão o card muda de altura a cada troca de filtro/período.

Vale para as duas páginas de estatísticas: a do aluno e a do aluno vista pelo
professor."""
import re

import pytest

TEMPLATES = {
    'aluno': 'templates/aluno/estatisticas.html',
    'professor': 'templates/professor/estatisticas_aluno.html',
}


def _ler(chave):
    with open(TEMPLATES[chave], encoding='utf-8') as arq:
        return arq.read()


@pytest.fixture(params=sorted(TEMPLATES))
def template(request):
    return _ler(request.param)


def test_mensagem_de_vazio_fica_dentro_da_caixa_do_grafico(template):
    wrap = template.split('class="est-chart-wrap"', 1)[1].split('id="toolbarEvolucao"', 1)[0]
    assert 'id="evolucaoChart"' in wrap
    assert 'id="evolucaoVazio"' in wrap


def test_vazio_e_centralizado_sobre_a_caixa_do_grafico(template):
    regra = re.search(r'\.est-chart-wrap > \.est-empty\s*\{(.*?)\}', template, re.S)
    assert regra, 'falta a regra que posiciona o vazio sobre a caixa do gráfico'
    corpo = regra.group(1)
    assert 'position: absolute' in corpo and 'inset: 0' in corpo
    assert 'justify-content: center' in corpo and 'align-items: center' in corpo


def test_js_mostra_o_vazio_como_flex_para_centralizar(template):
    assert "getElementById('evolucaoVazio').style.display = semDados ? 'flex' : 'none'" in template


def test_nenhum_ponto_do_js_mostra_o_vazio_como_block(template):
    # 'block' desfaz a centralização (inclusive no caminho de erro de rede)
    assert not re.search(r"getElementById\('evolucaoVazio'\)\.style\.display\s*=\s*[^;]*'block'", template)