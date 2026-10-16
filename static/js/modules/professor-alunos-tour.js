/**
 * professor-alunos-tour.js -- Product tour da tela "Gerenciar Alunos"
 * (professor). Driver.js servido localmente em static/vendor/driverjs/;
 * o tema vem de css/registrar-treino-tour.css (compartilhado com os
 * outros tours do app).
 *
 * Abre sozinho só na primeira vez (flag no localStorage, separada por
 * usuário) e pode ser reaberto pelo botão "Tutorial" (#btnTourProfessorAlunos).
 *
 * A tela tem duas versões da lista (tabela no desktop, cartões no
 * celular) e só uma fica visível por vez. Por isso os passos sobre o
 * aluno procuram o primeiro elemento VISÍVEL de cada seletor.
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Novo Aluno") dispare a ação de verdade durante o tour.
 */
(function () {
    'use strict';

    var lib = window.driver && window.driver.js;
    if (!lib || typeof lib.driver !== 'function') return;

    var scriptEl = document.currentScript;
    var usuarioId = (scriptEl && scriptEl.getAttribute('data-user-id')) || 'anon';
    var CHAVE_STORAGE = 'fitlog:tour:professor-alunos:v1:' + usuarioId;

    var instanciaAtiva = null;
    var rolagemInicial = 0;

    // ---------- localStorage (nunca pode quebrar a tela) ----------
    function jaViu() {
        try {
            return window.localStorage.getItem(CHAVE_STORAGE) === '1';
        } catch (e) {
            // Sem storage não dá pra lembrar: melhor não abrir sozinho
            // a cada visita. O botão "Tutorial" continua funcionando.
            return true;
        }
    }

    function marcarVisto() {
        try {
            window.localStorage.setItem(CHAVE_STORAGE, '1');
        } catch (e) { /* storage cheio/indisponível -- ignora */ }
    }

    // ---------- helpers de DOM ----------
    function visivel(el) {
        return !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
    }

    // Primeiro elemento VISÍVEL do seletor (tabela no desktop, cartão no
    // celular) -- ou null, e o passo é descartado.
    function primeiroVisivel(seletor) {
        var lista = document.querySelectorAll(seletor);
        for (var i = 0; i < lista.length; i++) {
            if (visivel(lista[i])) return lista[i];
        }
        return null;
    }

    // ---------- passos ----------
    function montarPassos() {
        var temAlunos = !!document.querySelector('.ga-aluno-item');
        var passos = [
            {
                element: primeiroVisivel('#gaAlertaSolicitacoes'),
                popover: {
                    title: 'Pedidos de vínculo',
                    description: 'Este aviso aparece quando algum aluno pediu para ser seu aluno. '
                        + 'Toque em <b>Ver solicitações</b> para aceitar ou recusar.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: primeiroVisivel('#gaBusca'),
                popover: {
                    title: 'Encontre um aluno',
                    description: 'Digite o nome, o usuário ou o e-mail e toque em <b>Filtrar</b>. '
                        + 'Útil quando a lista começa a crescer.',
                    side: 'bottom',
                    align: 'center'
                }
            }
        ];

        if (temAlunos) {
            passos.push(
                {
                    element: primeiroVisivel('.ga-aluno-item'),
                    popover: {
                        title: 'Seus alunos',
                        description: 'Cada aluno vinculado a você aparece aqui, em ordem alfabética, '
                            + 'com contato e a data em que o vínculo começou.',
                        side: 'top',
                        align: 'center'
                    }
                },
                {
                    element: primeiroVisivel('.ga-registros'),
                    popover: {
                        title: 'Treinos registrados',
                        description: 'Quantos treinos o aluno já registrou. Dá para ver de relance '
                            + 'quem está treinando e quem sumiu.',
                        side: 'top',
                        align: 'center'
                    }
                },
                {
                    element: primeiroVisivel('.ga-btn-ver'),
                    popover: {
                        title: 'Abrir o aluno',
                        description: 'Abre a ficha dele: versões de treino, estatísticas, calendário '
                            + 'e o que ele registrou.',
                        side: 'top',
                        align: 'end'
                    }
                },
                {
                    element: primeiroVisivel('.ga-btn-editar'),
                    popover: {
                        title: 'Editar, desativar e reativar',
                        description: 'Ações de administrador: corrigir os dados do aluno e '
                            + 'desativar ou reativar o acesso dele.',
                        side: 'top',
                        align: 'center'
                    }
                }
            );
        }

        passos.push(
            {
                element: primeiroVisivel('#gaBtnSolicitacoes'),
                popover: {
                    title: 'Solicitações',
                    description: 'Reúne os pedidos de alunos que querem treinar com você. '
                        + 'O número vermelho mostra quantos estão esperando resposta.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: primeiroVisivel('#gaBtnNovoAluno'),
                popover: {
                    title: 'Cadastrar um aluno novo',
                    description: 'Cria o acesso do aluno e já vincula a você. '
                        + 'Respeita o limite de alunos do seu plano.',
                    side: 'top',
                    align: 'center'
                }
            }
        );

        // Só entram os passos cujo elemento existe e está visível
        // (ex: sem solicitações pendentes, o aviso não existe).
        return passos.filter(function (p) { return !!p.element; });
    }

    // ---------- execução ----------
    function iniciar() {
        if (instanciaAtiva) return;

        var passos = montarPassos();
        if (!passos.length) return;

        var reduzirMovimento = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Os passos do fim da página rolam a janela. Guarda onde o usuário
        // estava para devolver ao terminar.
        rolagemInicial = window.pageYOffset || 0;

        instanciaAtiva = lib.driver({
            steps: passos,
            animate: !reduzirMovimento,
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
            // Confere a posição logo depois de destacar, caso o navegador
            // ainda esteja assentando a rolagem.
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
                marcarVisto();
                instanciaAtiva = null;
                window.scrollTo(0, rolagemInicial);
            }
        });
        instanciaAtiva.drive();
    }

    // ---------- gatilhos ----------
    function init() {
        var btn = document.getElementById('btnTourProfessorAlunos');
        if (btn) btn.addEventListener('click', iniciar);

        // Espera o loader e a transição de página terminarem antes de abrir.
        if (document.getElementById('gaBusca')) {
            window.setTimeout(function () {
                if (!jaViu()) iniciar();
            }, 900);
        }
    }

    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();