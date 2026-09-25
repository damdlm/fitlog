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
        if (!input || !preview) return;

        input.addEventListener('change', function () {
            var arquivo = input.files && input.files[0];
            if (!arquivo) return;
            var leitor = new FileReader();
            leitor.onload = function (e) {
                preview.innerHTML = '<img src="' + e.target.result + '" alt="Prévia da foto">';
            };
            leitor.readAsDataURL(arquivo);
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

    document.addEventListener('DOMContentLoaded', function () {
        initShareButton();
        initFotoPreview();
        initContadores();
    });
})();
