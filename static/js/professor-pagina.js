(function () {
    'use strict';

    // =========================================================
    // BOTÃO COMPARTILHAR (Web Share API com fallback pra copiar link)
    // =========================================================
    function initShareButton() {
        var btn = document.getElementById('ppShareBtn');
        if (!btn) return;

        btn.addEventListener('click', async function () {
            var url = btn.dataset.url;
            var titulo = btn.dataset.titulo || 'FitLog';

            if (navigator.share) {
                try {
                    await navigator.share({ title: titulo, url: url });
                    return;
                } catch (err) {
                    // Usuário cancelou o share nativo -- não é erro, não faz nada.
                    if (err && err.name === 'AbortError') return;
                }
            }

            try {
                await FitLogUtils.copyToClipboard(url);
                FitLogUtils.showToast('Link copiado!', 'success');
            } catch (err) {
                FitLogUtils.showToast('Não foi possível copiar o link.', 'danger');
            }
        });
    }

    // =========================================================
    // PREVIEW DA FOTO ANTES DE ENVIAR
    // =========================================================
    function initFotoPreview() {
        var input = document.getElementById('ppFotoInput');
        var preview = document.getElementById('ppFotoPreview');
        var botaoEnviar = document.getElementById('ppFotoEnviar');
        var ajuda = document.getElementById('ppFotoAjuda');
        if (!input || !preview) return;

        var TIPOS_OK = ['image/jpeg', 'image/png', 'image/webp'];
        var TAMANHO_MAX = 4 * 1024 * 1024; // mesmo limite do backend (4MB)
        var textoAjudaOriginal = ajuda ? ajuda.textContent : '';

        function mostrarAjuda(texto, erro) {
            if (!ajuda) return;
            ajuda.textContent = texto;
            ajuda.classList.toggle('epp-ajuda-erro', !!erro);
        }

        input.addEventListener('change', function () {
            var arquivo = input.files && input.files[0];
            if (!arquivo) {
                if (botaoEnviar) botaoEnviar.classList.add('d-none');
                mostrarAjuda(textoAjudaOriginal, false);
                return;
            }

            // Avisa na hora, em vez de só descobrir o erro depois do envio.
            if (TIPOS_OK.indexOf(arquivo.type) === -1) {
                input.value = '';
                if (botaoEnviar) botaoEnviar.classList.add('d-none');
                mostrarAjuda('Formato não aceito. Use JPG, PNG ou WEBP.', true);
                return;
            }
            if (arquivo.size > TAMANHO_MAX) {
                input.value = '';
                if (botaoEnviar) botaoEnviar.classList.add('d-none');
                mostrarAjuda('A imagem passa de 4MB. Escolha uma menor.', true);
                return;
            }

            var leitor = new FileReader();
            leitor.onload = function (e) {
                preview.innerHTML = '<img src="' + e.target.result + '" alt="Prévia da foto">';
            };
            leitor.readAsDataURL(arquivo);

            mostrarAjuda(arquivo.name, false);
            if (botaoEnviar) botaoEnviar.classList.remove('d-none');
        });
    }

    // =========================================================
    // CONTADOR DE CARACTERES (bio/tagline)
    // =========================================================
    function initContadores() {
        document.querySelectorAll('[data-contador-max]').forEach(function (campo) {
            var max = parseInt(campo.dataset.contadorMax, 10);
            var contador = document.getElementById(campo.dataset.contadorAlvo);
            if (!contador) return;

            function atualizar() {
                contador.textContent = campo.value.length + ' / ' + max;
            }
            campo.addEventListener('input', atualizar);
            atualizar();
        });
    }

    // =========================================================
    // MODAL "VER MINHA PÁGINA" -- recarrega o iframe toda vez que o
    // modal abre, pra sempre refletir o que acabou de ser salvo.
    // =========================================================
    function initVerPaginaModal() {
        var modal = document.getElementById('ppVerPaginaModal');
        var frame = document.getElementById('ppVerPaginaFrame');
        if (!modal || !frame) return;

        modal.addEventListener('show.bs.modal', function () {
            if (frame.dataset.src) {
                // Recarrega a cada abertura (não só na primeira vez) --
                // é assim que o professor confere se o que acabou de
                // salvar realmente já está na página pública. O "_"
                // evita que o navegador reaproveite uma versão antiga
                // do iframe guardada em cache/back-forward-cache.
                frame.src = frame.dataset.src + '&_=' + Date.now();
            }
        });

        modal.addEventListener('hidden.bs.modal', function () {
            frame.src = 'about:blank';
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initShareButton();
        initFotoPreview();
        initContadores();
        initVerPaginaModal();
    });
})();