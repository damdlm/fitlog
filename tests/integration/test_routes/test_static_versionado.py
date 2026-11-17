"""Scripts e estilos do layout base sempre com ?v=<mtime> (static_v).

Sem a versão na URL, navegador e Cloudflare guardam o arquivo por 1 dia
(SEND_FILE_MAX_AGE_DEFAULT): depois de um deploy, a página nova chegava
com o fitlog-utils.js antigo (sem FitLogUtils.formatarKg) e os números do
Progresso/calendário ficavam em "—".
"""
import re


def test_layout_base_versiona_todos_os_js_e_css(client):
    html = client.get('/auth/login').get_data(as_text=True)
    locais = re.findall(r'(?:src|href)="(/static/(?:js|css)/[^"]+)"', html)
    assert locais, 'nenhum estático local encontrado'
    sem_versao = [u for u in locais if '?v=' not in u]
    assert sem_versao == []
    assert any('fitlog-utils.js?v=' in u for u in locais)


def test_template_base_nao_usa_url_for_para_js_css():
    with open('templates/base.html', encoding='utf-8') as f:
        base = f.read()
    assert not re.search(r"url_for\('static', filename='(?:js|css)/", base)
