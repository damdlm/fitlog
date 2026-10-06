"""Evolução do Volume sem dados: o estado vazio é ENXUTO. Sem gráfico, somem a
caixa do gráfico (altura fixa de 190-300px), os botões "Por semana/Por treino"
e a legenda -- sobra só uma linha de aviso, mantendo no topo do card os filtros
de treino e de período. (Antes só o canvas sumia e o card ficava do mesmo
tamanho de quando tinha dados, só que vazio.)

Vale para as duas páginas de estatísticas: a do aluno e a do aluno vista pelo
professor. São testes sobre o template (o comportamento é JavaScript)."""
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


def test_aviso_de_vazio_fica_fora_da_caixa_de_altura_fixa(template):
    # Dentro da caixa ele herdaria os 190-300px de altura.
    wrap = template.split('class="est-chart-wrap"', 1)[1].split('id="evolucaoVazio"', 1)[0]
    assert 'id="evolucaoChart"' in wrap
    assert '</div>' in wrap  # a caixa já fechou antes do aviso


def _funcao_carregar_evolucao(template):
    # só o trecho do gráfico de evolução (a página tem outros gráficos que
    # escondem o próprio canvas, o que é correto para eles)
    return template.split('function carregarEvolucao', 1)[1].split('new Chart(', 1)[0]


def test_sem_dados_esconde_a_caixa_do_grafico_e_nao_so_o_canvas(template):
    trecho = _funcao_carregar_evolucao(template)
    assert "canvas.parentElement.style.display = semDados ? 'none' : ''" in trecho
    assert "canvas.style.display = semDados" not in trecho


def test_sem_dados_esconde_os_botoes_de_modo_e_a_legenda(template):
    assert "getElementById('toolbarEvolucao').style.display = semDados ? 'none' : ''" in _funcao_carregar_evolucao(template)


def test_com_dados_o_aviso_volta_a_ficar_escondido(template):
    assert "getElementById('evolucaoVazio').style.display = semDados ? 'block' : 'none'" in template


def test_aviso_e_uma_linha_compacta_sem_o_icone_grande(template):
    regra = re.search(r'#evolucaoVazio\s*\{(.*?)\}', template, re.S)
    assert regra, 'falta a regra que compacta o aviso do gráfico vazio'
    padding = re.search(r'padding:\s*(\d+)px', regra.group(1))
    assert padding and int(padding.group(1)) <= 16, 'padding vertical grande demais'
    icone = re.search(r'#evolucaoVazio i\s*\{(.*?)\}', template, re.S)
    assert icone, 'falta a regra do ícone do aviso'
    assert 'display: inline-block' in icone.group(1)
    tamanho = re.search(r'font-size:\s*([\d.]+)rem', icone.group(1))
    assert tamanho and float(tamanho.group(1)) <= 1.2, 'ícone grande demais'


def test_erro_de_rede_no_painel_do_professor_tambem_fica_enxuto():
    html = _ler('professor')
    marca = "getElementById('evolucaoChart').parentElement.style.display = 'none'"
    assert marca in html
    # a linha que esconde a legenda/botões vem logo depois, no mesmo catch
    assert "getElementById('toolbarEvolucao').style.display = 'none'" in html.split(marca, 1)[1][:200]