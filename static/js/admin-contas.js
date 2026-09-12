(function () {
    'use strict';

    var form = document.getElementById('contas-filtros-form');
    var tbody = document.getElementById('contas-tbody');
    var badgeWrap = document.getElementById('contas-badge-wrap');
    var badgeNumero = document.getElementById('contas-badge-numero');
    if (!form || !tbody) return;

    var buscaInput = document.getElementById('contas-filtro-busca');
    var abortController = null;
    var requestSeq = 0;

    function initPopovers() {
        tbody.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
            new bootstrap.Popover(el, { html: true, trigger: 'focus', placement: 'bottom' });
        });
    }

    function atualizarBadge(total) {
        badgeNumero.textContent = total;
        badgeWrap.style.display = total > 0 ? '' : 'none';
    }

    function atualizarUrl(params) {
        var url = new URL(window.location.href);
        url.search = '';
        params.forEach(function (value, key) {
            if (value) url.searchParams.set(key, value);
        });
        window.history.replaceState(null, '', url);
    }

    function carregar() {
        var params = new URLSearchParams(new FormData(form));
        var meuSeq = ++requestSeq;

        if (abortController) abortController.abort();
        abortController = new AbortController();

        fetch(window.CONTAS_API_URL + '?' + params.toString(), {
            headers: { 'Accept': 'application/json' },
            signal: abortController.signal,
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                // uma resposta antiga pode voltar depois de uma mais nova
                // (rede lenta) -- ignora se não for a última pedida
                if (meuSeq !== requestSeq) return;
                tbody.innerHTML = data.html;
                atualizarBadge(data.total_inadimplentes);
                initPopovers();
                atualizarUrl(params);
            })
            .catch(function (err) {
                if (err.name !== 'AbortError') {
                    console.error('Erro ao filtrar contas:', err);
                }
            });
    }

    function debounce(fn, ms) {
        var timer = null;
        return function () {
            clearTimeout(timer);
            timer = setTimeout(fn, ms);
        };
    }

    var carregarComDebounce = debounce(carregar, 350);

    if (buscaInput) {
        buscaInput.addEventListener('input', carregarComDebounce);
    }
    form.querySelectorAll('select[name]').forEach(function (select) {
        select.addEventListener('change', carregar);
    });
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        carregar();
    });

    initPopovers();
})();