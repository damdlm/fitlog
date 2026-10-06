/**
 * professor-pagina-ajuste.js
 * ---------------------------------------------------------------
 * Mantém o pôster da página pública do professor EXATAMENTE em 9:16
 * (formato de Stories), em qualquer um dos estilos, mesmo quando o
 * conteúdo é grande (avaliação + "Sobre mim" longo + especialidades).
 *
 * Sem este script o CSS (min-height em base.css) só garante o MÍNIMO
 * de 9:16: o pôster cresce quando o conteúdo não cabe, e cada estilo
 * cresce um pouco diferente, então as páginas deixavam de ter o mesmo
 * tamanho. Aqui o conteúdo é reduzido na medida certa (zoom nos blocos
 * do pôster) até caber na altura 9:16.
 *
 * - Só reduz quando precisa; com pouco conteúdo nada muda.
 * - Limite de redução (FIT_MIN): abaixo disso o texto ficaria pequeno
 *   demais e o pôster volta a crescer em vez de ficar ilegível.
 * - Roda ao carregar, quando as fontes terminam de carregar e quando a
 *   largura muda. Também é chamado pelo gerador de imagem
 *   (professor-pagina-imagem.js) antes de capturar.
 * ---------------------------------------------------------------
 */
(function () {
    'use strict';

    var FIT_MIN = 0.6;   // não reduz o conteúdo a menos de 60%
    var PASSOS = 10;     // iterações da busca (precisão ~0,05%)

    // Só os blocos que ocupam espaço no fluxo do pôster; as decorações
    // (pinceladas, pontos, barras) são absolutas e ficam como estão.
    function blocosDoFluxo(poster) {
        return Array.prototype.filter.call(poster.children, function (filho) {
            var estilo = window.getComputedStyle(filho);
            return estilo.position !== 'absolute' &&
                   estilo.position !== 'fixed' &&
                   estilo.display !== 'none';
        });
    }

    function aplicarZoom(blocos, z) {
        blocos.forEach(function (bloco) {
            if (z >= 0.999) bloco.style.removeProperty('zoom');
            else bloco.style.zoom = String(z);
        });
    }

    // O pôster "cabe" quando a altura dele é no máximo a que o 9:16 pede
    // PARA A LARGURA QUE ELE TEM NESSE MOMENTO. A largura é medida a cada
    // tentativa (e não uma vez só) porque, com barra de rolagem clássica,
    // conteúdo alto faz a barra aparecer e estreita a página uns 15px; se
    // a meta fosse calculada com a largura "apertada", o conteúdo seria
    // reduzido além do necessário.
    function cabe(poster, folga) {
        var largura = poster.getBoundingClientRect().width;
        return poster.offsetHeight <= largura * 16 / 9 + folga;
    }

    function ajustar() {
        var poster = document.querySelector('.pp-poster');
        if (!poster) return 1;

        var blocos = blocosDoFluxo(poster);
        aplicarZoom(blocos, 1);

        if (cabe(poster, 1)) {
            poster.setAttribute('data-pp-fit', '1');
            return 1;
        }

        // Maior zoom em que o conteúdo ainda cabe em 9:16 (busca binária).
        var baixo = FIT_MIN;
        var alto = 1;
        var melhor = FIT_MIN;
        for (var i = 0; i < PASSOS; i++) {
            var meio = (baixo + alto) / 2;
            aplicarZoom(blocos, meio);
            if (cabe(poster, 0.5)) {
                melhor = meio;
                baixo = meio;
            } else {
                alto = meio;
            }
        }
        aplicarZoom(blocos, melhor);
        poster.setAttribute('data-pp-fit', melhor.toFixed(3));
        return melhor;
    }

    window.ppAjustarPoster = ajustar;

    function iniciar() {
        ajustar();

        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(ajustar);
        }
        window.addEventListener('load', ajustar);

        // Largura mudou (girar o celular, abrir o modal, redimensionar).
        var poster = document.querySelector('.pp-poster');
        var larguraAnterior = poster ? poster.getBoundingClientRect().width : 0;
        var agendado = null;
        function aoRedimensionar() {
            if (!poster) return;
            var largura = poster.getBoundingClientRect().width;
            if (Math.abs(largura - larguraAnterior) < 0.5) return;
            larguraAnterior = largura;
            clearTimeout(agendado);
            agendado = setTimeout(ajustar, 60);
        }
        if (window.ResizeObserver && poster && poster.parentElement) {
            new ResizeObserver(aoRedimensionar).observe(poster.parentElement);
        } else {
            window.addEventListener('resize', aoRedimensionar);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();