/**
 * Gráficos (Chart.js) no formato brasileiro e no tema do app.
 *
 * 1) Números: sem o locale pt-BR, os eixos que o Chart.js formata sozinho
 *    usam o padrão americano ("30,000" no eixo de volume se lê como trinta
 *    quilos). Com ele, "30.000" e decimais com vírgula.
 *
 * 2) Tema escuro (lote 6e): os gráficos são desenhados em canvas, com as
 *    cores escritas no JS de cada tela (cinzas como #6b6b6b nos eixos,
 *    preto em algumas séries). O plugin "fitlogTema" troca, só no escuro,
 *    os cinzas escuros de texto/eixo por claros, as grades pretas
 *    translúcidas por brancas e as séries quase pretas por cinza claro.
 *    Os valores originais ficam guardados e voltam no tema claro. Quando o
 *    tema muda com a página aberta (evento "fitlog:tema", js/tema.js), os
 *    gráficos são redesenhados. O calendário tem as cores dele por tema e
 *    não passa por aqui (opção plugins.fitlogTema === false).
 *
 * Carregar logo depois de vendor/chartjs/chart.umd.min.js, antes de
 * criar qualquer gráfico.
 */
(function () {
    'use strict';
    if (typeof Chart === 'undefined' || !Chart.defaults) return;

    Chart.defaults.locale = 'pt-BR';

    var TEXTO_ESCURO = '#b0b6be';
    var GRADE_ESCURO = 'rgba(255, 255, 255, 0.08)';
    var SERIE_ESCURO = '#d5d9df';
    var DEFAULTS_CLARO = { color: Chart.defaults.color, borderColor: Chart.defaults.borderColor };

    function escuro() {
        return document.documentElement.getAttribute('data-bs-theme') === 'dark';
    }

    function rgb(cor) {
        if (typeof cor !== 'string') return null;
        var c = cor.trim().toLowerCase();
        var m = c.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/);
        if (m) {
            var h = m[1].length === 3 ? m[1].replace(/(.)/g, '$1$1') : m[1];
            return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16), a: 1 };
        }
        m = c.match(/^rgba?\(([^)]+)\)$/);
        if (m) {
            var p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
            return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
        }
        return null;
    }

    function luz(c) {
        function f(v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    }

    function neutra(c) {
        return Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b) <= 24;
    }

    // Cor do claro -> cor do escuro (ou null para manter)
    function paraEscuro(cor, tipo) {
        var c = rgb(cor);
        if (!c || !neutra(c)) return null;
        if (tipo === 'grade') return (c.a < 0.5 && luz(c) < 0.2) ? GRADE_ESCURO : null;
        if (tipo === 'serie') return (c.a >= 0.5 && luz(c) < 0.05) ? SERIE_ESCURO : null;
        return (c.a >= 0.5 && luz(c) < 0.35) ? TEXTO_ESCURO : null;
    }

    // Caminhos das opções com cor, por tipo. Caminhos e não objetos: o
    // Chart.js recria os objetos de escalas a cada update().
    function alvos(cfg) {
        var lista = [];
        var o = cfg.options || {};
        Object.keys(o.scales || {}).forEach(function (k) {
            var s = o.scales[k] || {};
            var base = ['options', 'scales', k];
            if (s.ticks) lista.push([base.concat('ticks', 'color'), 'texto']);
            if (s.title) lista.push([base.concat('title', 'color'), 'texto']);
            if (s.pointLabels) lista.push([base.concat('pointLabels', 'color'), 'texto']);
            if (s.grid) lista.push([base.concat('grid', 'color'), 'grade']);
            if (s.border) lista.push([base.concat('border', 'color'), 'grade']);
        });
        var pl = o.plugins || {};
        if (pl.legend && pl.legend.labels) lista.push([['options', 'plugins', 'legend', 'labels', 'color'], 'texto']);
        if (pl.title) lista.push([['options', 'plugins', 'title', 'color'], 'texto']);
        if (pl.subtitle) lista.push([['options', 'plugins', 'subtitle', 'color'], 'texto']);
        ((cfg.data && cfg.data.datasets) || []).forEach(function (ds, i) {
            ['borderColor', 'backgroundColor', 'pointBackgroundColor', 'pointBorderColor'].forEach(function (p) {
                lista.push([['data', 'datasets', i, p], 'serie']);
            });
        });
        return lista;
    }

    function ler(cfg, caminho) {
        var v = cfg;
        for (var i = 0; i < caminho.length; i++) {
            if (v == null) return undefined;
            v = v[caminho[i]];
        }
        return v;
    }

    function gravar(cfg, caminho, valor) {
        var obj = ler(cfg, caminho.slice(0, -1));
        if (obj && typeof obj === 'object') obj[caminho[caminho.length - 1]] = valor;
    }

    function igual(a, b) {
        return a === b || (Array.isArray(a) && Array.isArray(b) && a.length === b.length
            && a.every(function (x, i) { return x === b[i]; }));
    }

    function aplicar(chart) {
        var cfg = chart.config;
        if (!cfg || (cfg.options && cfg.options.plugins && cfg.options.plugins.fitlogTema === false)) return;
        var originais = chart.$flTemaOriginais || (chart.$flTemaOriginais = []);
        // volta tudo ao original antes de (re)aplicar -- só se a tela não
        // trocou a cor depois (aí vale a da tela)
        originais.forEach(function (item) {
            if (igual(ler(cfg, item[0]), item[2])) gravar(cfg, item[0], item[1]);
        });
        originais.length = 0;
        if (!escuro()) return;
        alvos(cfg).forEach(function (a) {
            var caminho = a[0], tipo = a[1];
            var v = ler(cfg, caminho);
            var novo = null;
            if (Array.isArray(v)) {
                var trocou = false;
                var lista = v.map(function (cor) {
                    var n = paraEscuro(cor, tipo);
                    if (n) trocou = true;
                    return n || cor;
                });
                if (trocou) novo = lista;
            } else {
                novo = paraEscuro(v, tipo);
            }
            if (novo) { originais.push([caminho, v, novo]); gravar(cfg, caminho, novo); }
        });
    }

    function ajustarPadroes() {
        if (escuro()) {
            Chart.defaults.color = TEXTO_ESCURO;
            Chart.defaults.borderColor = GRADE_ESCURO;
        } else {
            Chart.defaults.color = DEFAULTS_CLARO.color;
            Chart.defaults.borderColor = DEFAULTS_CLARO.borderColor;
        }
    }

    ajustarPadroes();
    Chart.register({ id: 'fitlogTema', beforeInit: aplicar, beforeUpdate: function (chart, args) {
        // update() feito por este arquivo já aplicou; demais updates mantêm o tema
        if (!(args && args.mode === 'fitlog-tema')) aplicar(chart);
    } });

    document.addEventListener('fitlog:tema', function () {
        ajustarPadroes();
        Object.keys(Chart.instances || {}).forEach(function (k) {
            var chart = Chart.instances[k];
            aplicar(chart);
            chart.update('fitlog-tema');
        });
    });
})();
