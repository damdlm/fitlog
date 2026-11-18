/**
 * Números dos gráficos (Chart.js) no formato brasileiro.
 *
 * Sem isso, os eixos que o Chart.js formata sozinho usam o padrão
 * americano: "30,000" no eixo de volume se lê como trinta quilos. Com o
 * locale pt-BR, o mesmo valor sai "30.000" e decimais saem com vírgula.
 * Carregar logo depois de vendor/chartjs/chart.umd.min.js, antes de
 * criar qualquer gráfico.
 */
(function () {
    'use strict';
    if (typeof Chart !== 'undefined' && Chart.defaults) {
        Chart.defaults.locale = 'pt-BR';
    }
})();
