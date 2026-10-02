/**
 * Sino de notificações -- polling simples (sem push, ver static/sw.js).
 *
 * Busca /api/notificacoes a cada 45s + na carga da página, atualiza o
 * badge de contagem e o conteúdo do dropdown do navbar. O polling PAUSA
 * com a aba oculta (retoma ao voltar), nunca roda duas buscas ao mesmo
 * tempo ou em menos de 10s, e respeita o 429 do rate limit esperando o
 * Retry-After (ou 5 min) em vez de insistir. CSRF é
 * adicionado automaticamente pelo interceptor global (ver
 * static/js/modules/csrf.js) -- não precisa fazer nada extra aqui.
 */
(function () {
    'use strict';

    const POLL_INTERVAL_MS = 45000;
    const MIN_GAP_MS = 10000;                // troca rápida de abas / cliques seguidos
    const BACKOFF_PADRAO_MS = 5 * 60 * 1000; // 429 sem Retry-After

    const badge = document.getElementById('notifBellBadge');
    const list = document.getElementById('notifDropdownList');
    const emptyState = document.getElementById('notifDropdownEmpty');
    const marcarTodasBtn = document.getElementById('notifMarcarTodasLink');
    const dropdownToggle = document.getElementById('notificacoesDropdownToggle');

    // Se o sino não está nesta página (usuário não logado), não faz nada.
    if (!badge || !list || !dropdownToggle) {
        return;
    }

    function iconePorTipo(tipo) {
        switch (tipo) {
            case 'treino_finalizado':
                return 'bi-check-circle';
            case 'treino_excluido':
            case 'versao_excluida':
                return 'bi-trash';
            case 'treino_adicionado':
                return 'bi-plus-circle';
            case 'versao_finalizada':
                return 'bi-flag';
            case 'versao_expirando':
                return 'bi-hourglass-split';
            default:
                return 'bi-pencil-square';
        }
    }

    function escapeHtml(texto) {
        const div = document.createElement('div');
        div.textContent = texto == null ? '' : texto;
        return div.innerHTML;
    }

    function renderizarLista(notificacoes) {
        list.innerHTML = '';

        if (!notificacoes || notificacoes.length === 0) {
            const vazio = document.createElement('div');
            vazio.className = 'notif-dropdown-empty';
            vazio.id = 'notifDropdownEmpty';
            vazio.textContent = 'Nenhuma notificação por aqui ainda.';
            list.appendChild(vazio);
            return;
        }

        notificacoes.forEach(function (n) {
            const item = document.createElement('a');
            item.href = n.url || '#';
            item.className = 'notif-dropdown-item' + (n.lida ? '' : ' notif-unread');
            item.setAttribute('data-notificacao-id', n.id);

            item.innerHTML =
                '<span class="notif-dropdown-icon"><i class="bi ' + iconePorTipo(n.tipo) + '"></i></span>' +
                '<span class="notif-dropdown-body">' +
                    '<span class="notif-dropdown-title">' + escapeHtml(n.titulo) + '</span>' +
                    '<span class="notif-dropdown-msg">' + escapeHtml(n.mensagem) + '</span>' +
                    '<span class="notif-dropdown-time">' +
                        escapeHtml(n.created_at) +
                        (n.ocorrencias > 1 ? ' · <span class="notif-dropdown-count">' + n.ocorrencias + 'x</span>' : '') +
                    '</span>' +
                '</span>' +
                (n.lida ? '' : '<span class="notif-dropdown-dot"></span>');

            if (!n.lida) {
                item.addEventListener('click', function () {
                    marcarComoLida(n.id);
                });
            }

            list.appendChild(item);
        });
    }

    function atualizarBadge(naoLidas) {
        if (naoLidas > 0) {
            badge.textContent = naoLidas > 99 ? '99+' : String(naoLidas);
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }

    let timer = null;
    let emAndamento = false;
    let ultimaBusca = 0;
    let proximoPermitido = 0; // só > 0 enquanto estamos em backoff por 429

    function agendar(ms) {
        clearTimeout(timer);
        timer = null;
        // Aba oculta: não faz polling. O visibilitychange retoma ao voltar.
        if (document.hidden) return;
        timer = setTimeout(function () { buscarNotificacoes(false); }, ms);
    }

    // `forcar` = ação do usuário (abrir o dropdown, marcar como lida): ignora
    // o intervalo mínimo e o backoff, mas nunca roda duas buscas ao mesmo tempo.
    function buscarNotificacoes(forcar) {
        if (emAndamento) return;
        if (!forcar && document.hidden) return; // defesa: timer disparou com a aba já oculta
        const agora = Date.now();
        if (!forcar && (agora < proximoPermitido || agora - ultimaBusca < MIN_GAP_MS)) {
            agendar(Math.max(POLL_INTERVAL_MS, proximoPermitido - agora));
            return;
        }
        emAndamento = true;
        ultimaBusca = agora;
        fetch('/api/notificacoes', { method: 'GET' })
            .then(function (resp) {
                if (resp.status === 429) {
                    const segundos = parseInt(resp.headers.get('Retry-After'), 10);
                    proximoPermitido = Date.now() + (segundos > 0 ? segundos * 1000 : BACKOFF_PADRAO_MS);
                    throw new Error('Rate limit nas notificações');
                }
                if (!resp.ok) throw new Error('Falha ao buscar notificações');
                proximoPermitido = 0;
                return resp.json();
            })
            .then(function (data) {
                atualizarBadge(data.nao_lidas || 0);
                renderizarLista(data.notificacoes || []);
            })
            .catch(function () {
                // Falha silenciosa -- não interromper a navegação por causa
                // do sino (ver mesma filosofia do sw.js: nunca travar o app).
            })
            .then(function () {
                emAndamento = false;
                agendar(Math.max(POLL_INTERVAL_MS, proximoPermitido - Date.now()));
            });
    }

    function marcarComoLida(id) {
        fetch('/api/notificacoes/' + id + '/marcar-lida', { method: 'POST' })
            .then(function () { buscarNotificacoes(true); })
            .catch(function () {});
    }

    if (marcarTodasBtn) {
        marcarTodasBtn.addEventListener('click', function () {
            fetch('/api/notificacoes/marcar-todas-lidas', { method: 'POST' })
                .then(function () { buscarNotificacoes(true); })
                .catch(function () {});
        });
    }

    // Atualiza também sempre que o dropdown é aberto (mais responsivo do
    // que esperar o próximo ciclo de polling).
    dropdownToggle.addEventListener('click', function () { buscarNotificacoes(true); });

    // Aba escondida para o polling; ao voltar, atualiza na hora (respeitando
    // o intervalo mínimo e o backoff) e retoma o ciclo.
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            clearTimeout(timer);
            timer = null;
        } else {
            buscarNotificacoes(false);
        }
    });

    buscarNotificacoes(true);
})();