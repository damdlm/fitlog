"""Tooltip dos gráficos (Chart.js) fecha ao tocar/clicar fora: o comportamento
vem de um script único carregado pelo base.html (vale pra todos os gráficos)."""

SCRIPT = 'js/modules/chart-tooltip-dismiss.js'


def test_base_carrega_o_script_que_fecha_o_tooltip(client):
    html = client.get('/auth/login').data.decode()
    assert SCRIPT in html


def test_script_estatico_e_servido_e_escuta_pointerdown(client):
    resp = client.get('/static/' + SCRIPT)
    try:
        assert resp.status_code == 200
        corpo = resp.data.decode()
    finally:
        resp.close()
    assert "addEventListener('pointerdown'" in corpo
    # consulta os gráficos na hora do toque (cobre os recriados depois)
    assert 'Chart.instances' in corpo


def test_estatisticas_do_aluno_nao_duplica_o_listener(app):
    # o listener específico do gráfico de evolução foi substituído pelo
    # script compartilhado -- não pode voltar a existir um segundo.
    with open('templates/aluno/estatisticas.html', encoding='utf-8') as arq:
        assert "addEventListener('pointerdown'" not in arq.read()