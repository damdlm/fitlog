/**
 * professor-estatisticas-aluno-tour.js -- Tour guiado da tela de Estatísticas
 * de um aluno, vista pelo professor (templates/professor/estatisticas_aluno.html).
 * Usa o motor static/js/fl-tour-core.js (Driver.js local) e o tema
 * css/registrar-treino-tour.css.
 *
 * Passeio único ("pagina"): cabeçalho, filtro de período, resumo, volume e
 * ranking por músculo, desempenho por treino (com a versão) e evolução do
 * volume. Seções sem dados ficam de fora (o motor ignora passos cujo
 * elemento não está visível).
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    function passos() {
        return [
            {
                element: '.est-hero',
                popover: {
                    title: 'Estatísticas do aluno',
                    description: 'Aqui você acompanha a evolução do aluno: o <b>grupo muscular que mais treina</b> '
                        + 'aparece ao lado do nome. <b>Voltar</b> leva para a ficha dele.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#estFiltroPeriodo',
                popover: {
                    title: 'Escolha o período',
                    description: 'Informe a <b>data inicial e final</b> e toque em <b>Filtrar</b>. '
                        + 'O resumo, os gráficos por músculo e o ranking abaixo seguem esse período '
                        + '(abre com o mês atual).',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.est-stats-row',
                popover: {
                    title: 'Resumo do período',
                    description: '<b>Volume total</b> (kg levantados), <b>exercícios</b> e <b>registros</b> '
                        + 'feitos pelo aluno no período escolhido.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.card:has(#muscleChart) .card-header',
                popover: {
                    title: 'Volume por músculo',
                    description: 'Como o volume do aluno se divide entre os grupos musculares. '
                        + 'Ajuda a ver o que está sendo pouco trabalhado.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '.card:has(.est-ranking-item) .card-header',
                popover: {
                    title: 'Ranking por músculo',
                    description: 'Os mesmos grupos em ordem, do mais ao menos trabalhado, '
                        + 'com o volume e o número de registros de cada um.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '#estDesempenhoTreino .card-header',
                popover: {
                    title: 'Desempenho por treino',
                    description: 'Abaixo, um cartão por treino (A, B, C...) com exercícios, registros e volume. '
                        + 'No seletor <b>Versão</b> você escolhe a versão do treino (abre com a ativa) '
                        + 'ou todas; o período do filtro de cima é mantido.',
                    side: 'bottom', align: 'start'
                }
            },
            {
                element: '#filtrosEvolucao',
                popover: {
                    title: 'Evolução do volume',
                    description: 'Veja o volume de <b>todos</b> os treinos juntos ou só de um deles (A, B, C...).',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#filtroPeriodoEvolucao',
                popover: {
                    title: 'Período do gráfico',
                    description: 'Este gráfico tem o seu próprio período, separado do filtro do topo.',
                    side: 'bottom', align: 'start'
                }
            },
            {
                element: '#toolbarEvolucao',
                popover: {
                    title: 'Agrupar por semana ou por treino',
                    description: 'Alterne a forma de ver o gráfico: somando por semana ou treino a treino.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'professor-estatisticas-aluno',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourProfEstatisticas', 'pagina');
        if (document.querySelector('.est-hero')) {
            // Espera o loader/transição e os gráficos carregarem.
            tour.iniciarAposAtraso('pagina', 1600);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
