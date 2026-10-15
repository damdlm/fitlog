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

    var lib = window.driver && window.driver.js;
    if (!lib || typeof lib.driver !== 'function') return;

    var scriptEl = document.currentScript;
    var usuarioId = (scriptEl && scriptEl.getAttribute('data-user-id')) || 'anon';
    var PREFIXO_STORAGE = 'fitlog:tour:registrar-treino:v1:' + usuarioId + ':';
    var CLASSE_MODO_TREINO = 'fl-modo-treino-ativo';

    var instanciaAtiva = null;

    // ---------- localStorage (nunca pode quebrar a tela) ----------
    function jaViu(fase) {
        try {
            return window.localStorage.getItem(PREFIXO_STORAGE + fase) === '1';
        } catch (e) {
            // Sem storage não dá pra lembrar: melhor não abrir sozinho
            // a cada visita. O botão "Tutorial" continua funcionando.
            return true;
        }
    }

    function marcarVisto(fase) {
        try {
            window.localStorage.setItem(PREFIXO_STORAGE + fase, '1');
        } catch (e) { /* storage cheio/indisponível -- ignora */ }
    }

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
                        + 'Quando houver imagem ou passo a passo, os ícones ao lado '
                        + 'do nome abrem a demonstração.',
                    side: 'bottom',
                    align: 'center'
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

    // Só entram no passeio os passos cujo elemento existe e está visível
    // (ex: o botão "avulso" só existe com treino selecionado).
    function filtrarVisiveis(passos) {
        return passos.filter(function (passo) {
            var el = document.querySelector(passo.element);
            return el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
        });
    }

    // ---------- execução ----------
    function iniciar(fase) {
        if (instanciaAtiva) return;

        var passos = filtrarVisiveis(fase === 'inicio' ? passosInicio() : passosTreino());
        if (!passos.length) return;

        var reduzirMovimento = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        instanciaAtiva = lib.driver({
            steps: passos,
            animate: !reduzirMovimento,
            smoothScroll: !reduzirMovimento,
            showProgress: true,
            progressText: '{{current}} de {{total}}',
            nextBtnText: 'Próximo',
            prevBtnText: 'Anterior',
            doneBtnText: 'Concluir',
            allowClose: true,
            disableActiveInteraction: true,
            overlayOpacity: 0.6,
            stagePadding: 6,
            stageRadius: 10,
            popoverClass: 'fl-tour',
            // Fechar (X, Esc ou clicar fora) também conta como visto:
            // o tour nunca deve voltar a abrir sozinho e atrapalhar.
            onDestroyed: function () {
                marcarVisto(fase);
                instanciaAtiva = null;
            }
        });
        instanciaAtiva.drive();
    }

    function iniciarAposAtraso(fase, atrasoMs) {
        window.setTimeout(function () {
            if (!jaViu(fase)) iniciar(fase);
        }, atrasoMs);
    }

    // ---------- gatilhos ----------
    function ligarBotoes() {
        var btnInicio = document.getElementById('btnTourRegistrarInicio');
        var btnTreino = document.getElementById('btnTourRegistrarTreino');
        if (btnInicio) btnInicio.addEventListener('click', function () { iniciar('inicio'); });
        if (btnTreino) btnTreino.addEventListener('click', function () { iniciar('treino'); });
    }

    function observarModoTreino() {
        // revelarExercicios() liga a classe no <body> ao entrar no modo
        // treino (depois do toque no play da tela de pré-início, ou ao
        // restaurar um treino salvo).
        if (document.body.classList.contains(CLASSE_MODO_TREINO)) {
            iniciarAposAtraso('treino', 700);
            return;
        }
        var observador = new MutationObserver(function () {
            if (document.body.classList.contains(CLASSE_MODO_TREINO)) {
                observador.disconnect();
                iniciarAposAtraso('treino', 700);
            }
        });
        observador.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    function init() {
        ligarBotoes();

        var temExercicios = !!document.getElementById('exerciciosCard');
        if (temExercicios) {
            observarModoTreino();
        } else if (!document.getElementById('rtAlertaVazio')
                   && document.getElementById('treinoPicker')) {
            // Tela de escolha (sem treino carregado). Espera o loader e a
            // transição de página terminarem antes de abrir.
            iniciarAposAtraso('inicio', 900);
        }
    }

    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();
