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
    // ESTILO DA PÁGINA (mostra a descrição do estilo escolhido)
    // =========================================================
    function initEstiloPagina() {
        var select = document.getElementById('ppEstiloPagina');
        var descricao = document.getElementById('ppEstiloDescricao');
        if (!select || !descricao) return;

        function atualizar() {
            var opcao = select.options[select.selectedIndex];
            descricao.textContent = opcao ? (opcao.dataset.descricao || '') : '';
        }
        select.addEventListener('change', atualizar);
        atualizar();
    }

    // =========================================================
    // POSIÇÃO DA FOTO (arrastar dentro do círculo)
    // =========================================================
    // A foto usa object-fit: cover, então só "sobra" imagem no eixo
    // maior; arrastar move o enquadramento (object-position, em %).
    // Arrastar a foto para a direita revela a parte esquerda, ou seja,
    // o percentual diminui -- por isso o sinal negativo abaixo.
    function initPosicaoFoto() {
        var circulo = document.getElementById('ppPosicaoCirculo');
        var img = document.getElementById('ppPosicaoImg');
        var inputX = document.getElementById('ppFotoPosX');
        var inputY = document.getElementById('ppFotoPosY');
        var botaoCentralizar = document.getElementById('ppPosicaoCentralizar');
        if (!circulo || !img || !inputX || !inputY) return;

        var x = parseFloat(inputX.value);
        var y = parseFloat(inputY.value);
        if (isNaN(x)) x = 50;
        if (isNaN(y)) y = 50;

        function limitar(v) { return Math.max(0, Math.min(100, v)); }

        function aplicar() {
            x = limitar(x);
            y = limitar(y);
            img.style.objectPosition = x + '% ' + y + '%';
            inputX.value = Math.round(x);
            inputY.value = Math.round(y);
            circulo.setAttribute('aria-valuetext', Math.round(x) + '% horizontal, ' + Math.round(y) + '% vertical');
        }

        // Quanto da imagem ultrapassa o círculo em cada eixo (px).
        function sobra() {
            var caixaL = circulo.clientWidth;
            var caixaA = circulo.clientHeight;
            var nl = img.naturalWidth || caixaL;
            var na = img.naturalHeight || caixaA;
            var escala = Math.max(caixaL / nl, caixaA / na);
            return {
                x: Math.max(0, nl * escala - caixaL),
                y: Math.max(0, na * escala - caixaA)
            };
        }

        var arrastando = false;
        var inicio = null;

        circulo.addEventListener('pointerdown', function (e) {
            arrastando = true;
            inicio = { px: e.clientX, py: e.clientY, x: x, y: y, sobra: sobra() };
            circulo.classList.add('epp-arrastando');
            if (circulo.setPointerCapture) circulo.setPointerCapture(e.pointerId);
            e.preventDefault();
        });

        circulo.addEventListener('pointermove', function (e) {
            if (!arrastando || !inicio) return;
            var dx = e.clientX - inicio.px;
            var dy = e.clientY - inicio.py;
            if (inicio.sobra.x > 0) x = inicio.x - (dx / inicio.sobra.x) * 100;
            if (inicio.sobra.y > 0) y = inicio.y - (dy / inicio.sobra.y) * 100;
            aplicar();
        });

        function soltar(e) {
            if (!arrastando) return;
            arrastando = false;
            inicio = null;
            circulo.classList.remove('epp-arrastando');
            if (e && circulo.releasePointerCapture && circulo.hasPointerCapture &&
                circulo.hasPointerCapture(e.pointerId)) {
                circulo.releasePointerCapture(e.pointerId);
            }
        }
        circulo.addEventListener('pointerup', soltar);
        circulo.addEventListener('pointercancel', soltar);

        // Teclado: setas ajustam de 2 em 2 pontos percentuais.
        circulo.addEventListener('keydown', function (e) {
            var passo = 2;
            var s = sobra();
            if (e.key === 'ArrowLeft' && s.x > 0) x += passo;
            else if (e.key === 'ArrowRight' && s.x > 0) x -= passo;
            else if (e.key === 'ArrowUp' && s.y > 0) y += passo;
            else if (e.key === 'ArrowDown' && s.y > 0) y -= passo;
            else return;
            e.preventDefault();
            aplicar();
        });

        if (botaoCentralizar) {
            botaoCentralizar.addEventListener('click', function () {
                x = 50;
                y = 50;
                aplicar();
            });
        }

        aplicar();
    }

    document.addEventListener('DOMContentLoaded', function () {
        initShareButton();
        initFotoPreview();
        initContadores();
        initEstiloPagina();
        initPosicaoFoto();
    });
})();