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
        // Com foto salva o círculo é o da posição; sem foto, é o de iniciais.
        var preview = document.getElementById('ppPosicaoCirculo') ||
                      document.getElementById('ppFotoPreview');
        var botaoEnviar = document.getElementById('ppFotoEnviar');
        var ajuda = document.getElementById('ppFotoAjuda');
        var imgPosicao = document.getElementById('ppPosicaoImg');
        var formPosicao = document.getElementById('ppPosicaoForm');
        if (!input || !preview) return;

        var srcOriginal = imgPosicao ? imgPosicao.getAttribute('src') : null;
        var posicaoOriginal = imgPosicao ? imgPosicao.style.objectPosition : '';

        // Volta o círculo para a foto já salva (arquivo removido/inválido).
        function restaurarFotoSalva() {
            if (!imgPosicao) return;
            imgPosicao.setAttribute('src', srcOriginal);
            imgPosicao.style.objectPosition = posicaoOriginal;
            preview.classList.remove('epp-pendente');
            if (formPosicao) formPosicao.classList.remove('d-none');
        }

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
                restaurarFotoSalva();
                mostrarAjuda(textoAjudaOriginal, false);
                return;
            }

            // Avisa na hora, em vez de só descobrir o erro depois do envio.
            if (TIPOS_OK.indexOf(arquivo.type) === -1) {
                input.value = '';
                if (botaoEnviar) botaoEnviar.classList.add('d-none');
                restaurarFotoSalva();
                mostrarAjuda('Formato não aceito. Use JPG, PNG ou WEBP.', true);
                return;
            }
            if (arquivo.size > TAMANHO_MAX) {
                input.value = '';
                if (botaoEnviar) botaoEnviar.classList.add('d-none');
                restaurarFotoSalva();
                mostrarAjuda('A imagem passa de 4MB. Escolha uma menor.', true);
                return;
            }

            var leitor = new FileReader();
            leitor.onload = function (e) {
                if (imgPosicao) {
                    // Prévia da foto nova, centralizada; a posição só pode
                    // ser ajustada depois do envio.
                    imgPosicao.setAttribute('src', e.target.result);
                    imgPosicao.style.objectPosition = '50% 50%';
                    preview.classList.add('epp-pendente');
                    if (formPosicao) formPosicao.classList.add('d-none');
                } else {
                    preview.innerHTML = '<img src="' + e.target.result + '" alt="Prévia da foto">';
                }
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
        // Campos de 2 linhas visuais que não aceitam Enter (ex: frase de impacto)
        document.querySelectorAll('[data-sem-quebra]').forEach(function (campo) {
            campo.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') e.preventDefault();
            });
            campo.addEventListener('input', function () {
                if (/[\r\n]/.test(campo.value)) {
                    campo.value = campo.value.replace(/[\r\n]+/g, ' ');
                }
            });
        });

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
            if (circulo.classList.contains('epp-pendente')) return;
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
            if (circulo.classList.contains('epp-pendente')) return;
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

    // =========================================================
    // ESPECIALIDADES (tooltip com a descrição ao clicar + contador)
    // =========================================================
    function initEspecialidades() {
        var checkboxes = document.querySelectorAll('.epp-chip-option input[type="checkbox"]');
        if (!checkboxes.length) return;

        var contador = document.getElementById('ppEspContador');
        var temBootstrap = window.bootstrap && window.bootstrap.Tooltip;
        var tooltips = [];
        var aberto = null;
        var timer = null;

        function atualizarContador() {
            if (!contador) return;
            var total = document.querySelectorAll('.epp-chip-option input:checked').length;
            contador.textContent = total === 0
                ? ''
                : total + (total === 1 ? ' selecionada' : ' selecionadas');
        }

        function esconderAberto() {
            clearTimeout(timer);
            if (aberto) {
                aberto.hide();
                aberto = null;
            }
        }

        checkboxes.forEach(function (checkbox) {
            var rotulo = checkbox.parentNode.querySelector('label');
            var tooltip = null;
            if (temBootstrap && rotulo) {
                // Manual: abre ao clicar (também por teclado, via "change")
                // e fecha sozinho, em vez do hover padrão do Bootstrap.
                tooltip = new window.bootstrap.Tooltip(rotulo, {
                    title: rotulo.dataset.descricao || '',
                    trigger: 'manual',
                    placement: 'top',
                    customClass: 'epp-tooltip',
                    container: 'body'
                });
                tooltips.push(tooltip);
            }

            checkbox.addEventListener('change', function () {
                atualizarContador();
                if (!tooltip) return;
                esconderAberto();
                tooltip.show();
                aberto = tooltip;
                timer = setTimeout(esconderAberto, 4500);
            });
        });

        // Clique fora de qualquer especialidade fecha o tooltip.
        document.addEventListener('click', function (e) {
            if (!e.target.closest('.epp-chip-option')) esconderAberto();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') esconderAberto();
        });

        atualizarContador();
    }

    // =========================================================
    // COPIAR LINK DA PÁGINA PÚBLICA
    // =========================================================
    function initCopiarLink() {
        var btn = document.getElementById('eppCopiarLink');
        if (!btn) return;
        btn.addEventListener('click', async function () {
            try {
                await FitLogUtils.copyToClipboard(btn.dataset.url);
                FitLogUtils.showToast('Link copiado!', 'success');
            } catch (err) {
                FitLogUtils.showToast('Não foi possível copiar o link.', 'danger');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initShareButton();
        initFotoPreview();
        initContadores();
        initEstiloPagina();
        initPosicaoFoto();
        initEspecialidades();
        initCopiarLink();
    });
})();