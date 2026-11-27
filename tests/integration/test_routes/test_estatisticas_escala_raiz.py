"""Evolução do Volume, filtro "Todos": barras de carga média em escala raiz,
para o treino de perna (200 kg) não esmagar o de braço (15 kg). Eixo e
tooltip continuam em kg reais. Vale para a página do aluno e a do professor."""
import json
import shutil
import subprocess

import pytest

JS = 'static/js/modules/escala-raiz.js'
TEMPLATES = ['templates/aluno/estatisticas.html', 'templates/professor/estatisticas_aluno.html']


def _ler(caminho):
    with open(caminho, encoding='utf-8') as arq:
        return arq.read()


@pytest.mark.parametrize('caminho', TEMPLATES)
def test_grafico_usa_a_escala_so_no_todos(caminho):
    html = _ler(caminho)
    assert "static_v('js/modules/escala-raiz.js')" in html
    # o módulo carrega depois do Chart.js e antes de ser usado
    assert html.index('chart.umd.min.js') < html.index('escala-raiz.js') < html.index('FitlogEscalaRaiz.comprimir')
    assert "const escalaRaiz = treinoEvolucao === 'todos' && datasetsBarras.length > 1;" in html
    assert 'if (escalaRaiz) {' in html and 'FitlogEscalaRaiz.comprimir(datasetsBarras);' in html
    assert 'y: FitlogEscalaRaiz.eixo(escalaRaiz && datasetsBarras, {' in html
    assert '${FitlogEscalaRaiz.valor(context)}' in html  # tooltip em kg reais
    # a linha de volume (y1) continua linear
    y1 = html.split('y1: {', 1)[1].split('}', 1)[0]
    assert 'FitlogEscalaRaiz' not in y1


def _node(codigo):
    if not shutil.which('node'):
        pytest.skip('node não instalado')
    script = "global.window = {}; require('./" + JS + "'); const E = window.FitlogEscalaRaiz;" + codigo
    return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)


def test_comprime_guarda_o_real_e_aceita_zero():
    ds = _node("const d = [{data: [225, 16, 0]}]; E.comprimir(d);"
               "console.log(JSON.stringify([d[0].data, d[0].valoresReais,"
               " E.valor({dataset: d[0], dataIndex: 1, formattedValue: 'x'}),"
               " E.valor({dataset: {}, dataIndex: 0, formattedValue: '12,5'})]))")
    assert ds == [[15, 4, 0], [225, 16, 0], '16', '12,5']


def test_marcas_do_eixo_em_kg_redondos():
    marcas = _node("console.log(JSON.stringify([E.marcas(210, 5), E.marcas(18, 5), E.marcas(2600, 5)]))")
    assert marcas == [[0, 30, 75, 150, 250], [0, 5, 10, 20], [0, 250, 750, 1500, 3000]]


def test_eixo_sem_barras_comprimidas_fica_como_veio():
    r = _node("const o = {beginAtZero: true, ticks: {maxTicksLimit: 5}};"
              "const d = [{data: [210, 15]}]; E.comprimir(d); const e = E.eixo(d, o);"
              "console.log(JSON.stringify([E.eixo(false, o) === o, e.min, e.max * e.max,"
              " e.ticks.callback(Math.sqrt(75)), 'maxTicksLimit' in e.ticks]))")
    assert r == [True, 0, 250, '75', False]