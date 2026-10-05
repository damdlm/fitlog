/**
 * Fecha o tooltip dos gráficos (Chart.js) ao tocar/clicar FORA do gráfico.
 *
 * O Chart.js só escuta eventos do próprio <canvas>: no celular, depois de
 * tocar numa barra o tooltip ficava preso na tela. Este listener único,
 * no documento, vale para TODOS os gráficos da página -- inclusive os
 * criados/recriados depois (troca de filtro, de período etc.), porque
 * consulta Chart.instances na hora do toque em vez de guardar referências.
 *
 * Tocar no próprio gráfico não faz nada aqui (o Chart.js cuida disso).
 */
(function () {
    'use strict';

    function limparTooltips(alvo) {
        // Chart só existe nas páginas que carregam Chart.js.
        if (typeof Chart === 'undefined' || !Chart.instances) return;

        Object.keys(Chart.instances).forEach(function (id) {
            var grafico = Chart.instances[id];
            if (!grafico || !grafico.canvas || !grafico.tooltip) return;
            if (grafico.canvas === alvo) return;
            // Sem tooltip aberto, não há nada pra limpar (evita redesenhar à toa).
            if (!grafico.tooltip.getActiveElements().length) return;

            grafico.setActiveElements([]);
            grafico.tooltip.setActiveElements([], { x: 0, y: 0 });
            grafico.update('none');
        });
    }

    document.addEventListener('pointerdown', function (evento) {
        limparTooltips(evento.target);
    });
})();