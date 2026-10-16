/**
 * ver-versao-tour.js -- Product tour da tela de uma VERSÃO de treino
 * (templates/aluno/ver_versao.html). A mesma tela é usada pelo aluno
 * (nas próprias versões) e pelo professor (editando a versão de um aluno),
 * por isso o texto muda conforme data-contexto="professor" no <script>.
 * Driver.js servido localmente em static/vendor/driverjs/; o tema vem de
 * css/registrar-treino-tour.css (compartilhado com os outros tours).
 *
 * Dois passeios, um por momento da tela:
 *   1) "lista": resumo da versão e cartões de treino. Os passos mudam
 *      se a versão está ATIVA (editável) ou FINALIZADA (só Clonar/Excluir).
 *   2) "modal": janela de montar/editar o treino (nome, busca, exercícios).
 *
 * Cada passeio abre sozinho só na primeira vez (flag no localStorage,
 * separada por usuário) e pode ser reaberto pelos botões "Tutorial"
 * (#btnTourVersaoLista e #btnTourVersaoModal).
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
    var PREFIXO_STORAGE = 'fitlog:tour:ver-versao:v1:' + usuarioId + ':';
    // Professor editando a versão de um aluno (texto em 3ª pessoa).
    var doProfessor = (scriptEl && scriptEl.getAttribute('data-contexto')) === 'professor';

    var instanciaAtiva = null;
    var desligarReposicionamento = null;
    var rolagemInicial = 0;

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
    function passosLista() {
        return [
            {
                element: '.ct-hero',
                popover: {
                    title: 'Resumo da versão',
                    description: 'Uma versão é uma fase do treino ' + (doProfessor ? 'do aluno' : 'que você segue')
                        + '. Aqui ficam o nome, se está <b>Ativa</b> ou <b>Finalizada</b>, o início, '
                        + 'quantos treinos e quantos exercícios ela tem.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '.ct-hero-desc-edit',
                popover: {
                    title: 'Editar a versão',
                    description: 'Muda o nome da versão e permite <b>finalizá-la</b> quando essa fase '
                        + 'acabar. Finalizada, ela vira histórico e pode ser clonada.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-hero-actions .btn-outline-primary',
                popover: {
                    title: 'Clonar a versão',
                    description: 'Cria uma nova versão ativa com os mesmos treinos e exercícios. '
                        + 'Só dá para clonar se não houver outra versão ativa ' + (doProfessor ? 'para o aluno.' : 'no momento.'),
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-hero-actions .btn-outline-danger',
                popover: {
                    title: 'Excluir a versão',
                    description: 'Só é possível se nenhum treino dela já foi registrado. '
                        + 'O app pede confirmação antes de apagar.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                // Só o cabeçalho do cartão: o cartão inteiro cresce com a
                // lista de exercícios e passaria da altura da tela.
                element: '.ct-treino-card .ct-treino-top',
                popover: {
                    title: 'Um cartão por treino',
                    description: 'Cada treino (A, B, C...) mostra o nome e quantos exercícios '
                        + 'tem, com a lista deles logo abaixo. Treino sem exercício '
                        + 'aparece em vermelho.',
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
                    description: 'Remove o treino e seus exercícios desta versão, com confirmação. '
                        + 'Se o treino já foi registrado alguma vez, a remoção é bloqueada '
                        + 'para não perder o histórico.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '.ct-treino-card .ct-ex-drag-handle',
                popover: {
                    title: 'Reordene os exercícios',
                    description: 'Segure esta alça e arraste o exercício para mudar a ordem. '
                        + 'Quando mexer, aparece o botão <b>Salvar ordem</b>.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-add-treino-btn',
                popover: {
                    title: 'Adicionar treino',
                    description: 'Cria o próximo treino da versão (B, C...). '
                        + 'O contador mostra quantos já existem e o limite.',
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

        // Os passos rolam a página (ex: "Adicionar treino" fica no fim da
        // lista). Guarda onde o usuário estava para devolver ao terminar.
        rolagemInicial = window.pageYOffset || 0;

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
                if (fase !== 'modal') window.scrollTo(0, rolagemInicial);
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
        ligarBotao('btnTourVersaoLista', 'lista');
        ligarBotao('btnTourVersaoModal', 'modal');

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

        if (document.querySelector('.ct-hero')) {
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