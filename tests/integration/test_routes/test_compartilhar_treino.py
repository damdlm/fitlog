"""Compartilhar treino (nov/2026): o resumo do treino já gerava a imagem
(Compartilhar, Baixar, WhatsApp). Agora também:

- três estilos para a imagem (Escuro, Laranja, Claro), lembrados no
  aparelho (localStorage "fitlog:share-estilo");
- "Copiar texto do treino", pronto para colar no WhatsApp (também usado
  no link do WhatsApp quando o celular não compartilha arquivo);
- marca "Recorde" no exercício cuja carga passou do maior já registrado
  (data-recorde-carga, calculado antes do treino);
- leitura das séries individuais (modo série a série): carga máxima,
  faixa de repetições e volume somado série por série.
"""
import re

from tests.integration.test_routes.test_valor_suspeito import (
    _criar_exercicio_base, _criar_usuario, _criar_versao_com_treino, _registro,
)
from models import db, VersaoExercicio


def _html(client, app, username):
    with app.app_context():
        user = _criar_usuario(username)
        base = _criar_exercicio_base(f'Supino {username}')
        v, tv = _criar_versao_com_treino(user.id)
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=base.id, ordem=0))
        db.session.commit()
        _registro(user, v, tv, [{'carga': 40, 'repeticoes': 10}], base_id=base.id, dias_atras=3)
        tid = tv.id
    client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123!'})
    return client.get(f'/registrar/registrar-treino?treino={tid}').get_data(as_text=True).replace('\r\n', '\n')


def _script_resumo(html):
    ini = html.index('/* ====== Modal de resumo do treino: montagem do card + compartilhamento ====== */')
    return html[ini:html.index('window.FitLogResumoTreino = { abrir: abrir };', ini)]


class TestEstilos:
    def test_tres_estilos_no_modal(self, client, app):
        html = _html(client, app, 'sh_estilos')
        bloco = html.split('class="share-estilos" role="radiogroup" aria-label="Estilo da imagem"')[1].split('class="resumo-modal-actions"')[0]
        for estilo in ('escuro', 'laranja', 'claro'):
            assert f'role="radio" aria-checked="{"true" if estilo == "escuro" else "false"}" data-share-estilo="{estilo}"' in bloco
        assert '.share-card--laranja {' in html and '.share-card--claro {' in html

    def test_estilo_lembrado_e_fundo_da_imagem(self, client, app):
        js = _script_resumo(_html(client, app, 'sh_estilos_js'))
        assert "const ESTILOS = { escuro: '#1e1e1e', laranja: '#e2711b', claro: '#ffffff' };" in js
        assert "const CHAVE_ESTILO = 'fitlog:share-estilo';" in js
        assert "backgroundColor: ESTILOS[estiloAtual()] || '#1e1e1e'," in js
        # trocar o estilo gera a imagem de novo (a pronta era do estilo anterior)
        troca = js[js.index("document.querySelectorAll('[data-share-estilo]').forEach(function (b) {\n            b.addEventListener"):][:500]
        assert 'imagemPromise = gerarImagemCard();' in troca

    def test_cores_da_imagem_sao_fixas(self, client, app):
        html = _html(client, app, 'sh_fixo')
        bloco = html[html.index('.share-card--laranja {'):html.index('/* Seletor de estilo, abaixo da prévia */')]
        for linha in bloco.splitlines():
            if re.search(r':\s*[^;]*#[0-9a-fA-F]{3,6}\b', linha) and 'var(' not in linha:
                assert 'tema: fixo' in linha, linha


class TestTextoERecorde:
    def test_botao_e_texto_para_whatsapp(self, client, app):
        html = _html(client, app, 'sh_texto')
        assert 'id="btnCopiarTextoResumo"' in html and 'Copiar texto do treino' in html
        js = _script_resumo(html)
        assert 'function textoDoTreino(resumo) {' in js
        assert "FitLogUtils.copyToClipboard(texto)" in js
        assert "' 🏆 recorde'" in js
        # o link do WhatsApp (sem compartilhar arquivo) usa o mesmo texto
        assert 'const texto = encodeURIComponent(textoDoTreino(montarResumoTreino()));' in js

    def test_recorde_compara_com_o_historico_anterior(self, client, app):
        html = _html(client, app, 'sh_recorde')
        assert 'data-recorde-carga="40.0"' in html
        js = _script_resumo(html)
        assert "const rec = parseFloat(row.dataset.recordeCarga);" in js
        assert "return !isNaN(rec) && rec > 0 && typeof carga === 'number' && !isNaN(carga) && carga > rec;" in js
        assert 'share-card-exercicio-tag--recorde' in js

    def test_series_individuais_entram_no_volume(self, client, app):
        js = _script_resumo(_html(client, app, 'sh_series'))
        assert "if (flag && flag.value === 'individual' && box && nSeries) {" in js
        assert 'volumeEx += (isNaN(c) ? 0 : c) * (isNaN(r) ? 0 : r);' in js
        assert "reps: rMin === '' ? '' : (rMin === rMax ? String(rMin) : `${rMin}–${rMax}`)," in js