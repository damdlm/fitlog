/**
 * professor-solicitacoes-tour.js -- Tour guiado das Solicitações de vínculo
 * (templates/professor/solicitacoes.html). Usa o motor static/js/fl-tour-core.js.
 *
 * Com solicitações: mostra o cartão do aluno e os botões Aprovar/Recusar.
 * Sem solicitações: explica o que aparecerá ali. Só lê o DOM; os botões
 * ficam sem ação durante o tour (disableActiveInteraction).
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    function passos() {
        return [
            {
                element: '.sv-aluno-info',
                popover: {
                    title: 'Quem pediu vínculo',
                    description: 'Cada cartão é um aluno que quer treinar com você: nome, usuário e a situação <b>Pendente</b>.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.sv-meta',
                popover: {
                    title: 'Dados do pedido',
                    description: 'E-mail do aluno e quando ele fez a solicitação.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.sv-acoes .btn-success',
                popover: {
                    title: 'Aprovar',
                    description: 'Aceita o aluno. Ele passa para a sua lista de <b>Meus alunos</b> e você já pode montar o treino dele.',
                    side: 'top', align: 'start'
                }
            },
            {
                element: '.sv-acoes .btn-outline-danger',
                popover: {
                    title: 'Recusar',
                    description: 'Recusa o pedido. O app sempre pede confirmação antes.',
                    side: 'top', align: 'end'
                }
            },
            {
                element: '#svVazio h5',
                popover: {
                    title: 'Nenhuma solicitação por enquanto',
                    description: 'Quando um aluno pedir vínculo com você, o pedido aparece aqui para aprovar ou recusar. '
                        + 'O número vermelho no menu avisa quando houver novidades.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#svVoltar',
                popover: {
                    title: 'Voltar',
                    description: 'Volta para a lista dos seus alunos.',
                    side: 'bottom', align: 'end'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'professor-solicitacoes',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourSolicitacoes', 'pagina');
        tour.iniciarAposAtraso('pagina', 1000);
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
