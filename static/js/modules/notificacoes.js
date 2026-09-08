/**
 * Sino de notificações -- polling simples (sem push, ver static/sw.js).
 *
 * Busca /api/notificacoes a cada 30s + na carga da página, atualiza o
 * badge de contagem e o conteúdo do dropdown do navbar. CSRF é
 * adicionado automaticamente pelo interceptor global (ver
 * static/js/modules/csrf.js) -- não precisa fazer nada extra aqui.
 */
(function () {
    'use strict';

    const POLL_INTERVAL_MS = 30000;

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
                    '<span class="notif-dropdown-time">' + escapeHtml(n.created_at) + '</span>' +
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

    function buscarNotificacoes() {
        fetch('/api/notificacoes', { method: 'GET' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('Falha ao buscar notificações');
                return resp.json();
            })
            .then(function (data) {
                atualizarBadge(data.nao_lidas || 0);
                renderizarLista(data.notificacoes || []);
            })
            .catch(function () {
                // Falha silenciosa -- não interromper a navegação por causa
                // do sino (ver mesma filosofia do sw.js: nunca travar o app).
            });
    }

    function marcarComoLida(id) {
        fetch('/api/notificacoes/' + id + '/marcar-lida', { method: 'POST' })
            .then(function () { buscarNotificacoes(); })
            .catch(function () {});
    }

    if (marcarTodasBtn) {
        marcarTodasBtn.addEventListener('click', function () {
            fetch('/api/notificacoes/marcar-todas-lidas', { method: 'POST' })
                .then(function () { buscarNotificacoes(); })
                .catch(function () {});
        });
    }

    // Atualiza também sempre que o dropdown é aberto (mais responsivo do
    // que esperar o próximo ciclo de polling).
    dropdownToggle.addEventListener('click', buscarNotificacoes);

    buscarNotificacoes();
    setInterval(buscarNotificacoes, POLL_INTERVAL_MS);
})();
