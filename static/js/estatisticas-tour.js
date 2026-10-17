/**
 * estatisticas-tour.js -- Tour guiado da tela de Estatísticas do aluno
 * (templates/aluno/estatisticas.html). Usa o motor static/js/fl-tour-core.js
 * (Driver.js local) e o tema css/registrar-treino-tour.css.
 *
 * Passeio único ("pagina"): resumo/compartilhar, filtro de período,
 * indicadores, recordes, progressão de força (1RM), volume por músculo,
 * evolução do volume e atividade. Seções sem dados ficam de fora
 * (o motor ignora passos cujo elemento não está visível).
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
                    title: 'Resumo da sua evolução',
                    description: 'Aqui aparece o <b>grupo muscular que você mais treinou</b>. '
                        + 'O botão <b>Compartilhar</b> gera uma imagem com o seu resumo.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#barraPeriodo',
                popover: {
                    title: 'Escolha o período',
                    description: 'Este filtro vale para as seções de baixo: 7 dias, 30 dias e outros intervalos, '
                        + 'ou um período <b>personalizado</b> com data inicial e final.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#kpiRow',
                popover: {
                    title: 'Indicadores',
                    description: '<b>Volume</b> (kg levantados), <b>treinos</b> e <b>séries</b> do período. '
                        + 'A setinha compara com o período anterior: se subiu, caiu ou ficou igual.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#recordesPessoais',
                popover: {
                    title: 'Recordes pessoais',
                    description: 'Suas maiores cargas por exercício no período. Deslize para o lado para ver mais.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#seletor1RM',
                popover: {
                    title: 'Escolha o exercício',
                    description: 'Selecione o exercício para acompanhar a sua <b>força</b> ao longo do tempo.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#rmChart',
                popover: {
                    title: 'Progressão de força (1RM)',
                    description: 'O <b>1RM estimado</b> é a carga máxima que você aguentaria levantar uma vez, '
                        + 'calculada a partir das suas séries. Se a linha sobe, você está ficando mais forte.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '#volumeMusculo .card-header',
                popover: {
                    title: 'Volume por músculo',
                    description: 'Mostra como o seu volume se divide entre os grupos musculares, '
                        + 'em gráfico e em ranking. Ajuda a ver o que está sendo pouco trabalhado.',
                    side: 'top', align: 'center'
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
            },
            {
                element: ['#tempoTreinoConteudo .est-tempo-stats-grid', '#tempoTreinoConteudo'],
                popover: {
                    title: 'Atividade',
                    description: 'Treinos, séries e repetições do período, a <b>duração média</b> dos treinos '
                        + 'e em qual parte do dia você costuma treinar.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'estatisticas',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourEstatisticas', 'pagina');
        if (document.querySelector('.est-hero')) {
            // Espera o loader/transição e os gráficos carregarem.
            tour.iniciarAposAtraso('pagina', 1600);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
