/* ============================================================
   FitLog · Modal de confirmação global (substitui window.confirm)
   ============================================================
   Duas formas de uso:

   1) DECLARATIVA -- em qualquer link ou botão de submit, em vez de
      onclick="return confirm(...)" / onsubmit="return confirm(...)":

        <a href="/rota/perigosa"
           data-confirm-title="Excluir este item?"
           data-confirm-text="Essa ação não pode ser desfeita."
           data-confirm-variant="danger"
           data-confirm-icon="bi-trash"
           data-confirm-label="Excluir">
            ...
        </a>

      Funciona tanto em links (navega/POSTa para o href) quanto em
      botões type="submit" dentro de um <form> (reenvia o form real,
      preservando todos os campos). Por padrão, links são tratados
      como ação POST (constrói um form dinâmico com CSRF) -- use
      data-confirm-method="get" para navegação simples por GET.

   2) PROGRAMÁTICA -- para telas com lógica própria (ex: só perguntar
      se houver alterações não salvas):

        window.FitLogConfirm({
            title: 'Sair sem salvar?',
            text: 'Suas alterações serão perdidas.',
            variant: 'warning',
            icon: 'bi-exclamation-triangle-fill',
            confirmLabel: 'Sair mesmo assim',
            onConfirm: function () { ... }
        });
   ============================================================ */
(function () {
    'use strict';

    function getModalParts() {
        return {
            el: document.getElementById('flConfirmModal'),
            iconWrap: document.getElementById('flConfirmIconWrap'),
            icon: document.getElementById('flConfirmIcon'),
            title: document.getElementById('flConfirmTitle'),
            text: document.getElementById('flConfirmText'),
            btnSim: document.getElementById('flConfirmBtnSim')
        };
    }

    window.FitLogConfirm = function (options) {
        options = options || {};
        var parts = getModalParts();

        if (!parts.el || typeof bootstrap === 'undefined') {
            // Sem Bootstrap/modal disponível por algum motivo -- não trava
            // o usuário, deixa a ação prosseguir direto (mesma rede de
            // segurança que o modal de cancelar treino já usava).
            if (typeof options.onConfirm === 'function') options.onConfirm();
            return;
        }

        var variant = options.variant || 'danger';
        parts.iconWrap.className = 'fl-confirm-icon variant-' + variant;
        parts.icon.className = 'bi ' + (options.icon || 'bi-exclamation-triangle-fill');
        parts.title.textContent = options.title || 'Confirmar ação?';
        parts.text.textContent = options.text || '';
        parts.text.style.display = options.text ? '' : 'none';
        parts.btnSim.textContent = options.confirmLabel || 'Confirmar';
        parts.btnSim.className = 'btn fl-confirm-btn-primary variant-' + variant + ' w-100';

        var modal = bootstrap.Modal.getOrCreateInstance(parts.el);

        // Remove um eventual handler de uma chamada anterior, pra não
        // empilhar callbacks no mesmo botão a cada nova chamada.
        if (parts.btnSim._flHandler) {
            parts.btnSim.removeEventListener('click', parts.btnSim._flHandler);
        }
        var aoConfirmar = function () {
            parts.btnSim.removeEventListener('click', aoConfirmar);
            parts.btnSim._flHandler = null;
            modal.hide();
            if (typeof options.onConfirm === 'function') options.onConfirm();
        };
        parts.btnSim._flHandler = aoConfirmar;
        parts.btnSim.addEventListener('click', aoConfirmar);
        modal.show();
    };

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var input = document.querySelector('input[name="csrf_token"]');
        return input ? input.value : '';
    }

    function prosseguirComForm(form) {
        if (window.FitLogPageTransition) window.FitLogPageTransition.show();
        window.setTimeout(function () {
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }, window.FitLogPageTransition ? window.FitLogPageTransition.NAV_DELAY_MS : 0);
    }

    function prosseguirComUrl(url, method) {
        if (window.FitLogPageTransition) window.FitLogPageTransition.show();
        window.setTimeout(function () {
            if ((method || 'post').toLowerCase() === 'get') {
                window.location.href = url;
                return;
            }
            var form = document.createElement('form');
            form.method = 'POST';
            form.action = url;
            var csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = getCsrfToken();
            form.appendChild(csrfInput);
            document.body.appendChild(form);
            form.submit();
        }, window.FitLogPageTransition ? window.FitLogPageTransition.NAV_DELAY_MS : 0);
    }

    // Gatilhos declarativos: qualquer link ou botão de submit com
    // data-confirm-title mostra o modal estilizado antes de agir -- nunca
    // dispara a ação nem qualquer confirm() nativo direto.
    //
    // Registrado em fase de CAPTURA (terceiro argumento "true") e com
    // stopPropagation() no handler: garante que roda ANTES do listener
    // global de transição de página (page-transition.js, que escuta em
    // fase de bolha). Sem isso, aquele script trataria o clique como uma
    // navegação/envio normal e agendaria a ação sozinho, mostrando a
    // película escura ANTES do usuário decidir no modal.
    document.addEventListener('click', function (evt) {
        var trigger = evt.target.closest('[data-confirm-title]');
        if (!trigger) return;

        evt.preventDefault();
        evt.stopPropagation();

        if (window.bootstrap && bootstrap.Tooltip) {
            var tooltip = bootstrap.Tooltip.getInstance(trigger);
            if (tooltip) tooltip.hide();
        }

        var variant = trigger.dataset.confirmVariant || 'danger';
        var icon = trigger.dataset.confirmIcon || 'bi-exclamation-triangle-fill';
        var title = trigger.dataset.confirmTitle || 'Confirmar ação?';
        var text = trigger.dataset.confirmText || '';
        var label = trigger.dataset.confirmLabel || 'Confirmar';

        var onConfirm;
        if (trigger.tagName === 'A') {
            var href = trigger.getAttribute('href');
            var method = trigger.dataset.confirmMethod || 'post';
            onConfirm = function () { prosseguirComUrl(href, method); };
        } else if (trigger.dataset.confirmUrl) {
            // Botão fora de um <form> próprio (ex: dentro de OUTRO form pai,
            // onde aninhar um <form> real seria HTML inválido) -- a URL de
            // destino vem explícita no atributo, e montamos um form
            // descartável na hora, igual ao caminho usado para links.
            var url = trigger.dataset.confirmUrl;
            var confirmMethod = trigger.dataset.confirmMethod || 'post';
            onConfirm = function () { prosseguirComUrl(url, confirmMethod); };
        } else {
            var form = trigger.form || trigger.closest('form');
            if (!form) return;
            onConfirm = function () { prosseguirComForm(form); };
        }

        window.FitLogConfirm({
            variant: variant,
            icon: icon,
            title: title,
            text: text,
            confirmLabel: label,
            onConfirm: onConfirm
        });
    }, true);
})();
