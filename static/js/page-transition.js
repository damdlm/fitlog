/* ============================================================
   FitLog · Feedback de clique + transição de página com película
   ============================================================
   - Todo clique em botão/link relevante mostra um efeito de "ripple"
     imediato, para o usuário confirmar que o clique foi registrado.
   - Ao navegar para outra página do próprio app (link interno ou
     submit de formulário), uma película escura com um loader em
     forma de átomo é exibida por 2s antes da página seguinte
     carregar de fato.
   ============================================================ */
(function () {
    'use strict';

    var OVERLAY_ID = 'flPageTransitionOverlay';
    var NAV_DELAY_MS = 1300;
    // Atraso antes da própria película começar a aparecer quando o clique
    // parte do menu mobile (barra inferior / painel "Mais") -- dá tempo do
    // usuário ver o feedback de ripple no botão antes da tela escurecer.
    var MENU_MOBILE_DELAY_MS = 300;

    function createOverlay() {
        var existing = document.getElementById(OVERLAY_ID);
        if (existing) return existing;

        var overlay = document.createElement('div');
        overlay.id = OVERLAY_ID;
        overlay.className = 'fl-loader-overlay';
        overlay.setAttribute('role', 'status');
        overlay.setAttribute('aria-label', 'Carregando');
        overlay.innerHTML =
            '<div class="fl-atom" aria-hidden="true">' +
            '<div class="fl-dot-orbit"></div>' +
            '<div class="fl-dot-orbit"></div>' +
            '<div class="fl-dot-orbit"></div>' +
            '<div class="fl-dot-orbit"></div>' +
            '</div>';
        document.body.appendChild(overlay);
        return overlay;
    }

    function showOverlay() {
        var overlay = createOverlay();
        // força reflow para garantir que a transição de opacidade rode
        // mesmo se a película já tiver sido criada/escondida antes.
        void overlay.offsetWidth;
        overlay.classList.add('fl-loader-visible');
    }

    function hideOverlay() {
        var overlay = document.getElementById(OVERLAY_ID);
        if (overlay) overlay.classList.remove('fl-loader-visible');
    }

    function isMobileMenuTarget(el) {
        return !!el.closest('.bottom-nav, .mais-sheet');
    }

    function addRipple(el, evt) {
        if (!el || el.disabled) return;
        var rect = el.getBoundingClientRect();
        var size = Math.max(rect.width, rect.height);
        var ripple = document.createElement('span');
        ripple.className = 'fl-ripple';
        ripple.style.width = ripple.style.height = size + 'px';

        var originX = (typeof evt.clientX === 'number' && evt.clientX !== 0)
            ? evt.clientX - rect.left
            : rect.width / 2;
        var originY = (typeof evt.clientY === 'number' && evt.clientY !== 0)
            ? evt.clientY - rect.top
            : rect.height / 2;

        ripple.style.left = (originX - size / 2) + 'px';
        ripple.style.top = (originY - size / 2) + 'px';

        el.appendChild(ripple);
        ripple.addEventListener('animationend', function () {
            ripple.remove();
        });
    }

    function getClickFeedbackTarget(el) {
        return el.closest('.btn, button, .nav-link, .list-group-item-action, [data-fl-click-feedback]');
    }

    function isInternalNavigableLink(link) {
        if (!link) return false;
        var href = link.getAttribute('href');
        if (!href) return false;
        if (href.charAt(0) === '#') return false;
        if (href.indexOf('mailto:') === 0 || href.indexOf('tel:') === 0 || href.indexOf('javascript:') === 0) return false;
        if (link.target && link.target !== '_self') return false;
        if (link.hasAttribute('download')) return false;
        if (link.dataset.flNoTransition !== undefined) return false;
        if (link.getAttribute('data-bs-toggle') || link.getAttribute('data-bs-dismiss')) return false;

        try {
            var url = new URL(href, window.location.href);
            return url.origin === window.location.origin;
        } catch (e) {
            return false;
        }
    }

    function navegarComTransicao(href, atrasoInicial) {
        window.setTimeout(function () {
            showOverlay();
            window.setTimeout(function () {
                window.location.href = href;
            }, NAV_DELAY_MS);
        }, atrasoInicial || 0);
    }

    document.addEventListener('click', function (evt) {
        var feedbackTarget = getClickFeedbackTarget(evt.target);
        if (feedbackTarget) {
            addRipple(feedbackTarget, evt);
        }

        // Navegação por link interno
        var link = evt.target.closest('a[href]');
        if (link && isInternalNavigableLink(link)) {
            evt.preventDefault();
            var href = link.getAttribute('href');
            // Nos botões do menu mobile (barra inferior / painel "Mais"),
            // espera 0,3s antes de a película de transição começar a
            // aparecer, para o ripple do clique ficar visível primeiro.
            var atrasoInicial = isMobileMenuTarget(link) ? MENU_MOBILE_DELAY_MS : 0;

            // Gancho opcional: uma página pode registrar
            // window.FitLogBeforeNavigate para interceptar a navegação
            // antes dela acontecer (ex: avisar que um treino em
            // andamento será perdido). Retornando false, ela assume a
            // responsabilidade de chamar "prosseguir" quando o usuário
            // confirmar -- a navegação normal não acontece agora.
            if (typeof window.FitLogBeforeNavigate === 'function') {
                var podeSeguir = window.FitLogBeforeNavigate(href, function () {
                    navegarComTransicao(href, atrasoInicial);
                });
                if (podeSeguir === false) return;
            }

            navegarComTransicao(href, atrasoInicial);
            return;
        }

        // Envio de formulário (botão type="submit")
        var submitBtn = evt.target.closest('button[type="submit"], input[type="submit"]');
        if (submitBtn && submitBtn.dataset.flNoTransition === undefined) {
            var form = submitBtn.form || submitBtn.closest('form');
            if (form && (typeof form.checkValidity !== 'function' || form.checkValidity())) {
                evt.preventDefault();
                showOverlay();
                window.setTimeout(function () {
                    if (typeof form.requestSubmit === 'function') {
                        form.requestSubmit(submitBtn);
                    } else {
                        form.submit();
                    }
                }, NAV_DELAY_MS);
            }
        }
    }, false);

    // Garante que a película não fique visível se o usuário voltar
    // pelo histórico do navegador (bfcache).
    window.addEventListener('pageshow', function () {
        hideOverlay();
    });

    // Expõe show/hide para outras telas chamarem a mesma película em
    // transições que não são navegação de página (ex: entrar no modo
    // treino em tela cheia ao clicar em "Iniciar treino").
    window.FitLogPageTransition = {
        show: showOverlay,
        hide: hideOverlay,
        NAV_DELAY_MS: NAV_DELAY_MS
    };
})();