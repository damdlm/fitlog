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
    var desligarReposicionamento = null;

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
                        + 'Logo abaixo, os campos para registrar o que você fez.',
                    side: 'bottom',
                    align: 'center'
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

    // ---------- reposicionamento ----------
    // O modo treino rola dentro de um contêiner próprio (não na janela).
    // O Driver.js só recalcula o destaque quando a JANELA rola/redimensiona,
    // e o evento "scroll" não borbulha: sem isso, ao voltar/avançar o
    // destaque fica no lugar antigo. Aqui escutamos a rolagem em qualquer
    // contêiner (fase de captura) e mandamos o Driver.js recalcular.
    function ligarReposicionamento() {
        var pendente = false;

        function agendar(ev) {
            // Rolagem dentro da própria caixa do tour não precisa recalcular.
            if (ev && ev.target && ev.target.closest
                && ev.target.closest('.driver-popover')) return;
            if (pendente) return;
            pendente = true;
            window.requestAnimationFrame(function () {
                pendente = false;
                if (instanciaAtiva) instanciaAtiva.refresh();
            });
        }

        document.addEventListener('scroll', agendar, true);
        window.addEventListener('resize', agendar);
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', agendar);
        }

        return function () {
            document.removeEventListener('scroll', agendar, true);
            window.removeEventListener('resize', agendar);
            if (window.visualViewport) {
                window.visualViewport.removeEventListener('resize', agendar);
            }
        };
    }

    // ---------- rolagem do contêiner ----------
    // O Driver.js só rola até o elemento quando ele sai da JANELA. No modo
    // treino a lista rola dentro de #modoTreinoBody, que termina acima do
    // rodapé do cronômetro: um elemento ainda "dentro da janela", mas
    // cortado por esse contêiner (ex: o botão de exercício avulso, que
    // fica logo abaixo da área visível), era considerado visível e o
    // destaque aparecia por cima do rodapé, apontando para o lugar errado.
    // Aqui rolamos o contêiner por conta própria antes de destacar.
    function ancestralRolavel(el) {
        var p = el.parentElement;
        while (p && p !== document.body && p !== document.documentElement) {
            var oy = window.getComputedStyle(p).overflowY;
            if ((oy === 'auto' || oy === 'scroll') && p.scrollHeight > p.clientHeight) return p;
            p = p.parentElement;
        }
        return null;
    }

    function garantirVisivelNoContainer(el) {
        if (!el || !el.getBoundingClientRect) return;
        var cont = ancestralRolavel(el);
        if (!cont) return;
        var margem = 12;
        var c = cont.getBoundingClientRect();
        var r = el.getBoundingClientRect();
        if (r.top >= c.top + margem && r.bottom <= c.bottom - margem) return;
        // Centraliza o elemento na área visível do contêiner (o navegador
        // limita o scrollTop ao fim da lista, então o último item só encosta
        // embaixo, o que também serve).
        cont.scrollTop += (r.top + r.bottom) / 2 - (c.top + c.bottom) / 2;
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
            // Rolagem instantânea: com "smooth" o Driver.js mede a posição
            // no meio da animação e o destaque aponta para o lugar errado.
            smoothScroll: false,
            showProgress: true,
            progressText: '{{current}} de {{total}}',
            nextBtnText: 'Próximo &rsaquo;',
            prevBtnText: '&lsaquo; Anterior',
            doneBtnText: 'Concluir',
            allowClose: true,
            disableActiveInteraction: true,
            overlayOpacity: 0.6,
            stagePadding: 6,
            stageRadius: 10,
            popoverClass: 'fl-tour',
            // Rola o contêiner do modo treino ANTES de o Driver.js medir o
            // elemento (ver garantirVisivelNoContainer).
            onHighlightStarted: function (el) {
                garantirVisivelNoContainer(el);
            },
            // Segurança extra: confere a posição logo depois de destacar,
            // caso o navegador ainda esteja assentando a rolagem.
            onHighlighted: function () {
                window.setTimeout(function () {
                    if (instanciaAtiva) instanciaAtiva.refresh();
                }, 250);
            },
            onPopoverRender: function (popover, ctx) {
                var atual = ((ctx && ctx.state && ctx.state.activeIndex) || 0) + 1;
                var total = passos.length;

                // No 1º passo "Anterior" não tem para onde voltar: some.
                if (popover.previousButton) {
                    popover.previousButton.style.display = atual === 1 ? 'none' : '';
                }

                // Barra de progresso fina no topo do rodapé.
                if (popover.footer) {
                    var barra = popover.footer.querySelector('.fl-tour-barra');
                    if (!barra) {
                        barra = document.createElement('div');
                        barra.className = 'fl-tour-barra';
                        barra.setAttribute('aria-hidden', 'true');
                        barra.appendChild(document.createElement('span'));
                        popover.footer.insertBefore(barra, popover.footer.firstChild);
                    }
                    barra.firstChild.style.width = Math.round((atual / total) * 100) + '%';
                }
            },
            // Fechar (X, Esc ou clicar fora) também conta como visto:
            // o tour nunca deve voltar a abrir sozinho e atrapalhar.
            onDestroyed: function () {
                marcarVisto(fase);
                instanciaAtiva = null;
                if (desligarReposicionamento) {
                    desligarReposicionamento();
                    desligarReposicionamento = null;
                }
            }
        });
        desligarReposicionamento = ligarReposicionamento();
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