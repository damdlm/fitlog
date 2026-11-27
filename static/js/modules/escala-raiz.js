/**
 * Escala raiz quadrada das barras de carga média do gráfico "Evolução do
 * Volume" (Estatísticas do aluno e a mesma tela vista pelo professor).
 *
 * No filtro "Todos" cada treino tem a sua barra, e o treino de perna (leg
 * press a 200 kg) deixava o de braço (rosca a 15 kg) quase invisível. A raiz
 * aproxima as alturas sem perder a ordem, e ao contrário do log aceita o zero
 * (treino não feito no período). O eixo continua escrito em kg de verdade
 * (marcas "redondas": 0, 20, 50, 100, 200...) e o toque na barra mostra o
 * valor real -- só a altura é comprimida.
 *
 * Uso (ver templates/aluno/estatisticas.html):
 *   FitlogEscalaRaiz.comprimir(datasetsBarras);           // antes do new Chart
 *   y: FitlogEscalaRaiz.eixo(datasetsBarras, { ... })     // opções do eixo
 *   FitlogEscalaRaiz.valor(context)                       // texto do tooltip
 */
(function () {
    'use strict';

    const MARCAS = [0, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 125, 150, 200, 250,
        300, 400, 500, 750, 1000, 1500, 2000];
    const numero = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

    // Guarda os kg reais e troca a altura das barras pela raiz.
    function comprimir(datasets) {
        datasets.forEach(function (ds) {
            ds.valoresReais = ds.data.slice();
            ds.data = ds.data.map(function (v) { return v > 0 ? Math.sqrt(v) : 0; });
        });
    }

    // Marcas do eixo em kg: do 0 até a primeira marca redonda acima do maior
    // valor, espaçadas igualmente NA ALTURA (por isso as de baixo são mais
    // próximas em kg), no máximo `limite` marcas.
    function marcas(maxReal, limite) {
        let topo = MARCAS.find(function (m) { return m >= maxReal; });
        if (topo === undefined) topo = Math.ceil(maxReal / 500) * 500;
        const passo = Math.sqrt(topo) / Math.max(2, limite - 1) * 0.8;
        const escolhidas = [topo];
        let ultima = Math.sqrt(topo);
        MARCAS.filter(function (m) { return m > 0 && m < topo; }).reverse().forEach(function (m) {
            const r = Math.sqrt(m);
            if (ultima - r >= passo && r >= passo) {
                escolhidas.push(m);
                ultima = r;
            }
        });
        escolhidas.push(0);
        return escolhidas.reverse();
    }

    // Opções do eixo das barras. Sem datasets comprimidos, devolve as
    // opções como vieram (eixo linear de sempre).
    function eixo(datasets, opcoes) {
        if (!datasets) return opcoes;
        const reais = [].concat.apply([], datasets.map(function (d) { return d.valoresReais || []; }));
        const maxReal = Math.max.apply(null, [0].concat(reais));
        if (!(maxReal > 0)) return opcoes;
        const lista = marcas(maxReal, (opcoes.ticks && opcoes.ticks.maxTicksLimit) || 6);
        const ticks = Object.assign({}, opcoes.ticks, {
            callback: function (v) { return numero.format(Math.round(v * v)); }
        });
        delete ticks.maxTicksLimit;
        return Object.assign({}, opcoes, {
            min: 0,
            max: Math.sqrt(lista[lista.length - 1]),
            ticks: ticks,
            afterBuildTicks: function (escala) {
                escala.ticks = lista.map(function (m) { return { value: Math.sqrt(m) }; });
            }
        });
    }

    // Valor do tooltip: o kg real da barra comprimida.
    function valor(context) {
        const reais = context.dataset.valoresReais;
        return reais ? numero.format(reais[context.dataIndex]) : context.formattedValue;
    }

    window.FitlogEscalaRaiz = { comprimir: comprimir, eixo: eixo, valor: valor, marcas: marcas };
})();