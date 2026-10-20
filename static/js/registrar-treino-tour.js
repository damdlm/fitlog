/**
 * registrar-treino-tour.js -- Product tour da tela "Registrar Treino"
 * (Driver.js, servido localmente em static/vendor/driverjs/).
 *
 * Dois passeios, porque a tela tem dois momentos bem diferentes:
 *   1) "inicio": escolher data e treino (tela sem exercícios carregados).
 *   2) "treino": modo treino em tela cheia (cronômetros, cartões de
 *      exercício, séries, avulso, salvar).
 *
 * Cada passeio abre sozinho só na primeira vez (flag no localStorage,
 * separada por usuário) e pode ser reaberto pelos botões "Tutorial"
 * (#btnTourRegistrarInicio e #btnTourRegistrarTreino).
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Salvar") dispare a ação de verdade durante o tour.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    var CLASSE_MODO_TREINO = 'fl-modo-treino-ativo';

    // ---------- passos ----------
    function passosInicio() {
        return [
            {
                element: '#campoDataTreino',
                popover: {
                    title: 'Data do treino',
                    description: 'Por padrão é hoje. Se esqueceu de registrar um treino, '
                        + 'toque aqui e escolha o dia em que ele aconteceu.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#linhaTreinoSelect',
                popover: {
                    title: 'Escolha o treino',
                    description: 'Toque no treino que você vai fazer. Os exercícios '
                        + 'carregam na hora e o modo treino começa em seguida.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    function passosTreino() {
        return [
            {
                element: '#cronoTreinoDisplay',
                popover: {
                    title: 'Cronômetro do treino',
                    description: 'Mostra há quanto tempo você está treinando. '
                        + 'O tempo total é salvo junto com o treino.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '#top-save-bar .top-save-bar-actions',
                popover: {
                    title: 'Cancelar, pausar e salvar',
                    description: '<b>Pausar</b> para o cronômetro quando você descansar mais. '
                        + '<b>Salvar</b> grava o treino ao terminar. '
                        + '<b>Cancelar</b> descarta tudo o que foi digitado.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '#registroForm .exercise-row',
                popover: {
                    title: 'Um cartão por exercício',
                    description: 'Toque no nome para ver os músculos trabalhados. '
                        + 'Logo abaixo, os campos para registrar o que você fez.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#registroForm .exercise-row .dash-registro-badges',
                popover: {
                    title: 'Valores do último treino',
                    description: 'Estes selos mostram o que você fez <b>da última vez</b> neste exercício: '
                        + 'carga, repetições e séries. Use como referência para evoluir hoje.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '#registroForm .exercise-row .exercicio-valores-grid',
                popover: {
                    title: 'Carga, repetições e séries',
                    description: 'Informe a carga (kg), as repetições e o número de séries. '
                        + 'Se você já treinou esse exercício, os valores do último '
                        + 'treino podem vir preenchidos para você ajustar.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '#registroForm .exercise-row .exercicio-switch-wrap',
                popover: {
                    title: 'Vou treinar hoje?',
                    description: 'Desmarque para pular este exercício. '
                        + 'Exercícios desmarcados não são salvos no treino.',
                    side: 'top',
                    align: 'start'
                }
            },
            {
                element: '#registroForm .exercise-row .btn-marcar-feito',
                popover: {
                    title: 'Marcar como feito',
                    description: 'O cartão fica verde para você saber quais exercícios '
                        + 'já concluiu. É só um lembrete visual e não altera o que é salvo.',
                    side: 'top',
                    align: 'end'
                }
            },
            {
                element: '#registroForm .btn-abrir-series-modal',
                popover: {
                    title: 'Valores diferentes por série',
                    description: 'Usou cargas ou repetições diferentes em cada série? '
                        + 'Toque na seta para lançar uma série por vez.',
                    side: 'left',
                    align: 'center'
                }
            },
            {
                element: '#registroForm .btn-instrucoes-exercicio',
                popover: {
                    title: 'Passo a passo',
                    description: 'Toque no <b>i</b> para ler as instruções de como '
                        + 'executar o exercício. Aparece nos exercícios que têm '
                        + 'instruções cadastradas.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '#registroForm .btn-imagens-exercicio',
                popover: {
                    title: 'Veja o exercício em movimento',
                    description: 'Toque no ícone de imagem para abrir a demonstração em '
                        + 'GIF ou vídeo e conferir a execução antes da série.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '#registroForm .btn-adicionar-avulso',
                popover: {
                    title: 'Exercício avulso',
                    description: 'Aparelho ocupado ou quis trocar algo? Adicione um '
                        + 'exercício só para esta sessão, sem mexer na sua lista de treinos.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '#cronoIntervaloBox',
                popover: {
                    title: 'Descanso entre séries',
                    description: 'Cronômetro regressivo para controlar o intervalo. '
                        + 'Escolha um tempo, inicie e ele avisa quando acabar.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    // Devolve a lista do modo treino ao topo (primeiro exercício): os últimos
    // passos rolam a lista até o fim (avulso, descanso).
    function voltarAoTopoDoModoTreino() {
        var corpo = document.getElementById('modoTreinoBody');
        if (!corpo) return;
        if (typeof corpo.scrollTo === 'function') {
            corpo.scrollTo({ top: 0, behavior: 'auto' });
        } else {
            corpo.scrollTop = 0;
        }
    }

    var tour = window.FlTour.criar({
        tela: 'registrar-treino',
        scriptEl: scriptEl,
        // A rolagem aqui é a do modo treino, não a da janela.
        fasesModal: ['inicio', 'treino'],
        aoEncerrar: function (fase) {
            if (fase === 'treino') voltarAoTopoDoModoTreino();
        },
        passos: { inicio: passosInicio, treino: passosTreino }
    });

    function observarModoTreino() {
        // revelarExercicios() liga a classe no <body> ao entrar no modo
        // treino (depois do toque no play da tela de pré-início, ou ao
        // restaurar um treino salvo).
        function abrir() {
            tour.iniciarAposAtraso('treino', 700, function () {
                return !!document.querySelector('#registroForm .exercise-row');
            });
        }
        if (document.body.classList.contains(CLASSE_MODO_TREINO)) { abrir(); return; }
        var observador = new MutationObserver(function () {
            if (document.body.classList.contains(CLASSE_MODO_TREINO)) {
                observador.disconnect();
                abrir();
            }
        });
        observador.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    function init() {
        tour.ligarBotao('btnTourRegistrarInicio', 'inicio');
        tour.ligarBotao('btnTourRegistrarTreino', 'treino');

        if (document.getElementById('exerciciosCard')) {
            observarModoTreino();
        } else if (!document.getElementById('rtAlertaVazio')
                   && document.getElementById('treinoPicker')) {
            // Tela de escolha (sem treino carregado). Espera o loader e a
            // transição de página terminarem antes de abrir.
            tour.iniciarAposAtraso('inicio', 900);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
