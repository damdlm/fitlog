"""Correções de nov/2026.

1) Cadastro (mobile): Termos de Uso e Política de Privacidade abrem em modal
   por cima do formulário -- antes abriam outra página e, no celular, não
   havia como voltar sem perder o que já tinha sido digitado.
2) Ficha: depois de reordenar os exercícios na tela, o modal "Editar treino"
   abria com a ordem antiga (mapa gravado só no carregamento da página) e, ao
   adicionar um exercício e salvar, a ordem antiga era gravada por cima da nova.
"""
from pathlib import Path

from tests.integration.test_routes.test_lote6d import _ficha, _sem_catalogo
from tests.integration.test_routes.test_observacao_exercicio_treino import _login

RAIZ = Path(__file__).resolve().parents[3]


def _ler(caminho):
    return (RAIZ / caminho).read_text(encoding='utf-8')


class TestTermosEmModalNoCadastro:
    def test_links_do_cadastro_abrem_no_modal_e_seguem_funcionando_sem_js(self, client):
        html = client.get('/auth/register').get_data(as_text=True)
        # sem JS o link continua abrindo a página pública em outra aba
        assert 'href="/privacidade/termos" target="_blank" rel="noopener" data-doc-legal="Termos de Uso"' in html
        assert 'href="/privacidade/" target="_blank" rel="noopener" data-doc-legal="Política de Privacidade"' in html
        assert 'id="modalDocLegal"' in html and 'id="modalDocLegalCorpo"' in html
        assert 'js/auth-register-docs.js' in html

    def test_modal_fica_fora_do_formulario(self, client):
        html = client.get('/auth/register').get_data(as_text=True)
        # um modal dentro do <form> mandaria seus botões junto no envio
        fim_form = html.index('</form>')
        assert html.index('id="modalDocLegal"') > fim_form

    def test_paginas_publicas_tem_o_formato_que_o_modal_le(self, client):
        # o JS pega ".card-body" e o título em ".card-header h4"
        for url in ('/privacidade/', '/privacidade/termos'):
            resp = client.get(url)
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert 'class="card-body"' in html
            assert '<div class="card-header' in html and '<h4' in html

    def test_js_so_abre_no_modal_as_duas_paginas_legais(self):
        js = _ler('static/js/auth-register-docs.js')
        assert "querySelector('.card-body')" in js
        assert r"/^\/privacidade\/(termos)?\/?$/" in js
        # outros links de dentro do texto nunca navegam a página do cadastro
        assert "a.target = '_blank'" in js
        # falhou a busca: volta a abrir a página em nova aba
        assert "window.open(href, '_blank', 'noopener')" in js


class TestOrdemDoTreinoNoModalDeEdicao:
    def test_lista_de_exercicios_informa_o_treino_versao_id(self, client, app):
        _uid, vid, tid = _ficha(app, 'ord_lista')
        _login(client, 'ord_lista')
        with _sem_catalogo():
            html = client.get(f'/aluno/versao/{vid}').get_data(as_text=True)
        assert f'class="ct-ex-list" data-treino-codigo="A" data-treino-versao-id="{tid}"' in html

    def test_js_atualiza_o_mapa_do_modal_ao_arrastar_e_ao_salvar(self):
        js = _ler('static/js/cadastrar-treinos-reordenar.js')
        assert 'function sincronizarMapa(lista)' in js
        assert 'window.CT_TREINO_EXERCICIOS' in js
        assert 'lista.dataset.treinoVersaoId' in js
        # chamado no fim do arraste (mesmo sem "Salvar ordem") e ao salvar
        trecho_on_end = js[js.index('onEnd: function'):js.index('onEnd: function') + 400]
        assert 'sincronizarMapa(lista)' in trecho_on_end
        trecho_salvar = js[js.index('async function salvarOrdem'):js.index('async function salvarOrdem') + 200]
        assert 'sincronizarMapa(lista)' in trecho_salvar

    def test_modal_le_a_ordem_do_mesmo_mapa(self):
        # se esse contrato mudar, o ajuste acima deixa de valer
        js = _ler('static/js/cadastrar-treinos.js')
        assert "const mapa = window.CT_TREINO_EXERCICIOS || {};" in js
        assert "const idsOrdem = mapa[treinoVersaoId] || [];" in js