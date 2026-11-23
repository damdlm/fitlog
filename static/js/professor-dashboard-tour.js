/**
 * professor-dashboard-tour.js -- Tour guiado do Painel do professor
 * (templates/professor/dashboard.html). Usa o motor static/js/fl-tour-core.js
 * (Driver.js local) e o tema css/registrar-treino-tour.css.
 *
 * Passeio único: saudação, indicadores, "o que precisa da sua atenção"
 * (alertas por aluno), última atividade, gráfico de 30 dias e ações
 * rápidas. Blocos que não aparecem (ex: sem alunos) ficam de fora.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    // Em telas estreitas os cartões ficam altos demais para destacar
    // inteiros e ainda sobrar espaço para o balão: destaca só o título.
    var compacto = window.innerWidth < 768;
    function alvo(cartao) {
        return compacto ? cartao + ' .pd-card-title' : cartao;
    }

    function passos() {
        return [
            {
                element: '.dash-hero',
                popover: {
                    title: 'Seu painel',
                    description: 'Um resumo do que merece a sua atenção hoje, para você começar o dia sabendo por onde ir.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: compacto ? '#pdIndicadores .pd-stat' : '#pdIndicadores',
                popover: {
                    title: 'Indicadores',
                    description: 'Quatro números: <b>alunos ativos</b>, quem <b>treinou hoje</b>, a <b>aderência</b> '
                        + '(média de dias treinados nos últimos 30) e quem está <b>sem treinar</b> há 7 dias ou mais.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: alvo('#pdAtencao'),
                popover: {
                    title: 'O que precisa da sua atenção',
                    description: 'Um alerta por aluno: <b>sem treinar</b> há 7+ dias, <b>abaixo do ritmo</b> de costume, '
                        + '<b>ficha para revisar</b> (60+ dias) e <b>recordes</b> da semana para parabenizar. '
                        + 'Filtre por tipo, aja direto pelo aluno (ou pelo WhatsApp) e marque <b>Visto</b>: '
                        + 'o alerta some e só volta se a situação mudar.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: alvo('#pdAtividade'),
                popover: {
                    title: 'Última atividade',
                    description: 'Os treinos mais recentes registrados pelos seus alunos.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: compacto ? '#graficoTreinos30d' : '#pdGrafico',
                popover: {
                    title: 'Treinos nos últimos 30 dias',
                    description: 'Quantos treinos os seus alunos registraram por dia.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: alvo('#pdAcoesRapidas'),
                popover: {
                    title: 'Ações rápidas',
                    description: 'Adicione um aluno, abra a lista dos seus alunos ou responda às solicitações de vínculo.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'professor-painel',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourPainel', 'pagina');
        if (document.querySelector('.dash-hero')) {
            tour.iniciarAposAtraso('pagina', 1300);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
