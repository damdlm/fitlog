/**
 * cadastrar-treinos-tour.js -- Product tour da tela "Cadastrar Treinos"
 * (Driver.js, servido localmente em static/vendor/driverjs/; o tema vem
 * de css/registrar-treino-tour.css, compartilhado com o tour de Registrar).
 *
 * Três passeios, um por momento da tela:
 *   1) "semversao": ainda não existe versão (formulário "Comece uma nova versão").
 *   2) "lista": versão em edição (resumo, cartões de treino, adicionar).
 *   3) "modal": janela de montar/editar o treino (nome, busca, exercícios).
 *
 * Cada passeio abre sozinho só na primeira vez (flag no localStorage,
 * separada por usuário) e pode ser reaberto pelos botões "Tutorial"
 * (#btnTourCadastrarSemVersao, #btnTourCadastrarLista, #btnTourCadastrarModal).
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Excluir", "Salvar treino") dispare a ação de verdade no tour.
 */
(function () {
    'use strict';

    var lib = window.driver && window.driver.js;
    if (!lib || typeof lib.driver !== 'function') return;

    var scriptEl = document.currentScript;
    var usuarioId = (scriptEl && scriptEl.getAttribute('data-user-id')) || 'anon';
    var PREFIXO_STORAGE = 'fitlog:tour:cadastrar-treinos:v1:' + usuarioId + ':';

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
    function passosSemVersao() {
        return [
            {
                element: '#descricao',
                popover: {
                    title: 'Dê um nome à versão',
                    description: 'Uma versão é uma fase do seu treino (ex: "Hipertrofia - Agosto"). '
                        + 'Ela guarda seus treinos A, B, C... enquanto estiver valendo.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#validade_meses',
                popover: {
                    title: 'Validade (opcional)',
                    description: 'Se quiser, informe por quantos meses a versão vale e o FitLog '
                        + 'avisa quando estiver perto de vencer. Em branco, ela não tem prazo.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '.ct-empty-form button[type="submit"]',
                popover: {
                    title: 'Criar e começar',
                    description: 'A data de início é hoje. Depois de criar, você monta os '
                        + 'treinos e escolhe os exercícios de cada um.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    function passosLista() {
        return [
            {
                element: '.ct-hero',
                popover: {
                    title: 'Sua versão em edição',
                    description: 'Aqui está o resumo: início, quantos treinos e quantos '
                        + 'exercícios já foram cadastrados. Toque em <b>Editar</b> para mudar o nome '
                        + 'ou finalizar a versão.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '.ct-treino-card',
                popover: {
                    title: 'Um cartão por treino',
                    description: 'Cada treino (A, B, C...) mostra o nome, quantos exercícios '
                        + 'tem e a lista deles. Treino sem exercício aparece em vermelho.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '.ct-treino-card .ct-btn-editar-exercicios',
                popover: {
                    title: 'Editar o treino',
                    description: 'Abre a janela para mudar o nome do treino e marcar ou '
                        + 'desmarcar exercícios.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '.ct-treino-card .ct-btn-excluir-treino',
                popover: {
                    title: 'Excluir o treino',
                    description: 'Remove o treino e seus exercícios desta versão. '
                        + 'O app pede confirmação antes de apagar.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '.ct-treino-card .ct-ex-toolbar',
                popover: {
                    title: 'Reordene os exercícios',
                    description: 'Segure a alça <b>&#8942;&#8942;</b> de um exercício e arraste para '
                        + 'mudar a ordem. Depois toque em <b>Salvar ordem</b>.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-add-treino-btn',
                popover: {
                    title: 'Adicionar treino',
                    description: 'Cria o próximo treino da versão (B, C...). '
                        + 'O contador mostra quantos você já tem e o limite.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    function passosModal() {
        return [
            {
                element: '#ctInputNome',
                popover: {
                    title: 'Nome do treino',
                    description: 'Dê um nome que facilite achar depois, como "Peito e tríceps".',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#etvSearchWrap',
                popover: {
                    title: 'Buscar exercício',
                    description: 'Digite parte do nome (ou um apelido) para filtrar a lista.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#modalExercicios .etv-btn-novo',
                popover: {
                    title: 'Não achou? Crie o seu',
                    description: 'Cadastre um exercício personalizado e ele entra na lista '
                        + 'para você marcar.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '#etvGrid .etv-card',
                popover: {
                    title: 'Marque os exercícios',
                    description: 'Toque no cartão para incluir o exercício no treino. '
                        + 'Toque de novo para tirar.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '#etvGrid .etv-obs-toggle',
                popover: {
                    title: 'Observação',
                    description: 'Quer lembrar de algo, como "pegada fechada"? '
                        + 'Abra e escreva uma observação curta para este exercício.',
                    side: 'top',
                    align: 'start'
                }
            },
            {
                element: '#etvGrid .etv-video-btn:not([disabled])',
                popover: {
                    title: 'Veja a execução',
                    description: 'O botão de play abre a demonstração em GIF ou vídeo '
                        + 'do exercício.',
                    side: 'left',
                    align: 'center'
                }
            },
            {
                element: '#modalExercicios .etv-footer-bar',
                popover: {
                    title: 'Salvar o treino',
                    description: 'Acompanhe quantos exercícios marcou e toque em <b>Salvar treino</b> '
                        + 'para gravar. <b>Cancelar</b> descarta as mudanças.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    var PASSOS = {
        semversao: passosSemVersao,
        lista: passosLista,
        modal: passosModal
    };

    // Só entram no passeio os passos cujo elemento existe e está visível
    // (ex: sem treinos ainda, não há cartão para mostrar).
    function filtrarVisiveis(passos) {
        return passos.filter(function (passo) {
            var el = document.querySelector(passo.element);
            return el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
        });
    }

    // ---------- reposicionamento ----------
    // A lista de exercícios do modal rola dentro de um contêiner próprio e
    // o evento "scroll" não borbulha: sem isso o destaque ficaria no lugar
    // antigo. Escutamos a rolagem em qualquer contêiner (fase de captura)
    // e mandamos o Driver.js recalcular.
    function ligarReposicionamento() {
        var pendente = false;

        function agendar(ev) {
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
    // O Driver.js só rola até o elemento quando ele sai da JANELA. Dentro
    // do modal a lista rola em .etv-scroll/.modal-body: um elemento cortado
    // por esse contêiner contaria como visível. Rolamos o contêiner antes.
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
        cont.scrollTop += (r.top + r.bottom) / 2 - (c.top + c.bottom) / 2;
    }

    // ---------- execução ----------
    function iniciar(fase) {
        if (instanciaAtiva || !PASSOS[fase]) return;

        var passos = filtrarVisiveis(PASSOS[fase]());
        if (!passos.length) return;

        var reduzirMovimento = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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
            onHighlightStarted: function (el) {
                garantirVisivelNoContainer(el);
            },
            onHighlighted: function () {
                window.setTimeout(function () {
                    if (instanciaAtiva) instanciaAtiva.refresh();
                }, 250);
            },
            onPopoverRender: function (popover, ctx) {
                var atual = ((ctx && ctx.state && ctx.state.activeIndex) || 0) + 1;
                var total = passos.length;

                if (popover.previousButton) {
                    popover.previousButton.style.display = atual === 1 ? 'none' : '';
                }

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
    function ligarBotao(id, fase) {
        var btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', function () { iniciar(fase); });
    }

    function init() {
        ligarBotao('btnTourCadastrarSemVersao', 'semversao');
        ligarBotao('btnTourCadastrarLista', 'lista');
        ligarBotao('btnTourCadastrarModal', 'modal');

        var modal = document.getElementById('modalExercicios');

        if (modal) {
            // Primeira vez que abre a janela de montar o treino: o passeio
            // do modal abre sozinho (depois que a animação do modal acaba).
            modal.addEventListener('shown.bs.modal', function () {
                iniciarAposAtraso('modal', 350);
            });
            // Fechar o modal com o passeio aberto: encerra o passeio.
            modal.addEventListener('hide.bs.modal', function () {
                if (instanciaAtiva) {
                    try { instanciaAtiva.destroy(); } catch (e) { /* já destruído */ }
                }
            });
        }

        if (document.getElementById('descricao')
            && document.querySelector('.ct-empty-form')) {
            iniciarAposAtraso('semversao', 900);
        } else if (document.querySelector('.ct-hero')) {
            // Espera o loader e a transição de página terminarem.
            iniciarAposAtraso('lista', 900);
        }
    }

    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();