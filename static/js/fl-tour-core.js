/**
 * fl-tour-core.js -- Motor compartilhado dos tours guiados (Driver.js) das
 * telas de calendário, estatísticas, início e painel do professor.
 * Segue o mesmo comportamento dos tours de registrar/cadastrar treino:
 * abre sozinho só na primeira vez (flag no localStorage por usuário),
 * pode ser reaberto pelo botão "Tutorial", filtra passos cujo elemento não
 * está visível, rola o contêiner certo, devolve a rolagem da página ao
 * terminar e nunca altera nenhum fluxo da tela (disableActiveInteraction).
 *
 * Uso: FlTour.criar({ tela, scriptEl, passos: { fase: function () { return [...]; } } })
 * devolve { iniciar(fase), iniciarAposAtraso(fase, ms, pronto), ligarBotao(id, fase),
 *           destruir(), ativo() }.
 * Cada passo é um passo do Driver.js; "element" pode ser uma lista de
 * seletores (usa o primeiro visível) e "visivelSe" um teste opcional.
 */
(function () {
    'use strict';

    var lib = window.driver && window.driver.js;
    if (!lib || typeof lib.driver !== 'function') return;

    function visivel(el) {
        return !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
    }

    // Aceita "seletor" ou ["seletor1", "seletor2"] e devolve o 1º elemento visível.
    function primeiroVisivel(seletores) {
        var lista = Array.isArray(seletores) ? seletores : [seletores];
        for (var i = 0; i < lista.length; i++) {
            var todos = document.querySelectorAll(lista[i]);
            for (var j = 0; j < todos.length; j++) {
                if (visivel(todos[j])) return todos[j];
            }
        }
        return null;
    }

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

    function criar(cfg) {
        var scriptEl = cfg.scriptEl;
        var usuarioId = (scriptEl && scriptEl.getAttribute('data-user-id')) || 'anon';
        var prefixo = 'fitlog:tour:' + cfg.tela + ':v1:' + usuarioId + ':';
        var instanciaAtiva = null;
        var desligarReposicionamento = null;
        var rolagemInicial = 0;

        function jaViu(fase) {
            try {
                return window.localStorage.getItem(prefixo + fase) === '1';
            } catch (e) {
                // Sem storage não dá pra lembrar: não abre sozinho.
                return true;
            }
        }

        function marcarVisto(fase) {
            try { window.localStorage.setItem(prefixo + fase, '1'); } catch (e) { /* ignora */ }
        }

        function resolverPassos(fase) {
            var fabrica = cfg.passos[fase];
            if (!fabrica) return [];
            var saida = [];
            fabrica().forEach(function (passo) {
                if (passo.visivelSe && !passo.visivelSe()) return;
                var el = primeiroVisivel(passo.element);
                if (!el) return;
                var copia = {};
                Object.keys(passo).forEach(function (k) { copia[k] = passo[k]; });
                copia.element = el;
                delete copia.visivelSe;
                saida.push(copia);
            });
            return saida;
        }

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
            if (window.visualViewport) window.visualViewport.addEventListener('resize', agendar);
            return function () {
                document.removeEventListener('scroll', agendar, true);
                window.removeEventListener('resize', agendar);
                if (window.visualViewport) window.visualViewport.removeEventListener('resize', agendar);
            };
        }

        function iniciar(fase) {
            if (instanciaAtiva) return;
            var passos = resolverPassos(fase);
            if (!passos.length) return;

            rolagemInicial = window.pageYOffset || 0;
            var reduzir = window.matchMedia
                && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            var restaurarRolagem = !(cfg.fasesModal && cfg.fasesModal.indexOf(fase) !== -1);

            instanciaAtiva = lib.driver({
                steps: passos,
                animate: !reduzir,
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
                onHighlightStarted: function (el) { garantirVisivelNoContainer(el); },
                onHighlighted: function (el) {
                    // O Driver.js pode mexer na rolagem do contêiner depois de
                    // onHighlightStarted (ex: janela com a lista grande); refaz.
                    garantirVisivelNoContainer(el);
                    // Dois recálculos: gráficos e imagens podem mudar a
                    // altura da página logo depois da rolagem.
                    [250, 800].forEach(function (ms) {
                        window.setTimeout(function () {
                            if (!instanciaAtiva) return;
                            garantirVisivelNoContainer(el);
                            instanciaAtiva.refresh();
                        }, ms);
                    });
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
                onDestroyed: function () {
                    marcarVisto(fase);
                    instanciaAtiva = null;
                    if (cfg.aoEncerrar) cfg.aoEncerrar(fase);
                    if (restaurarRolagem) window.scrollTo(0, rolagemInicial);
                    if (desligarReposicionamento) {
                        desligarReposicionamento();
                        desligarReposicionamento = null;
                    }
                }
            });
            if (cfg.aoIniciar) cfg.aoIniciar(fase);
            desligarReposicionamento = ligarReposicionamento();
            instanciaAtiva.drive();
        }

        // Espera "ms" e, se houver o teste "pronto", continua esperando (até
        // 8 s) o conteúdo existir antes de abrir: em rede lenta o passo não é
        // mais pulado por um atraso fixo curto demais.
        function iniciarAposAtraso(fase, ms, pronto) {
            window.setTimeout(function () {
                if (jaViu(fase)) return;
                if (!pronto) { iniciar(fase); return; }
                var limite = Date.now() + 8000;
                (function verificar() {
                    var ok = false;
                    try { ok = !!pronto(); } catch (e) { ok = false; }
                    if (ok || Date.now() >= limite) { if (!jaViu(fase)) iniciar(fase); return; }
                    window.setTimeout(verificar, 150);
                })();
            }, ms);
        }

        function ligarBotao(id, fase) {
            var btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', function () { iniciar(fase); });
        }

        function destruir() {
            if (instanciaAtiva) {
                try { instanciaAtiva.destroy(); } catch (e) { /* já destruído */ }
            }
        }

        return {
            iniciar: iniciar,
            iniciarAposAtraso: iniciarAposAtraso,
            ligarBotao: ligarBotao,
            destruir: destruir,
            ativo: function () { return !!instanciaAtiva; }
        };
    }

    window.FlTour = { criar: criar, visivel: visivel };
})();