/**
 * Crash Watchdog -- detecta travamentos do FitLog no navegador e
 * tenta se recuperar sozinho (reload), reportando o motivo pro
 * painel /admin/crash-logs.
 *
 * Carregado como o PRIMEIRO <script> de base.html (logo depois do
 * meta csrf-token), de propósito -- pra capturar erro/promise
 * rejeitada mesmo de scripts que carregam depois dele. Autocontido:
 * não depende de FitLogUtils, Bootstrap nem de nenhum outro módulo,
 * porque um travamento pode acontecer ANTES de qualquer um deles
 * terminar de carregar.
 *
 * O que é detectado:
 *  - 'js_error': erro JS não tratado (window.onerror).
 *  - 'promise_rejeitada': promise rejeitada sem .catch().
 *  - 'ui_travada': thread principal bloqueada por tempo demais
 *    (medido via requestAnimationFrame -- se o próximo frame demora
 *    bem mais que o esperado, é porque algo travou o JS no meio do
 *    caminho).
 *  - 'crash_anterior': ao carregar a página, se a aba tinha um
 *    "heartbeat" recente sem um encerramento limpo (pagehide/
 *    beforeunload nunca disparou), é sinal de que o processo morreu
 *    de forma anormal -- ex: o WKWebView do PWA sendo matado pelo
 *    sistema por falta de memória, o cenário real que já causou o
 *    "Um problema ocorreu repetidamente" do Safari neste projeto.
 *
 * Todo reload automático passa por um limite (no máximo 3 recargas a
 * cada 2 minutos, guardado em sessionStorage) pra nunca entrar num
 * loop de reload -- se o limite estourar, mostra um aviso fixo com
 * botão manual em vez de continuar recarregando sozinho.
 */
(function () {
    'use strict';

    var ENDPOINT = '/admin/crash-logs/api/reportar';
    var HB_KEY = 'flcw:hb';
    var URL_KEY = 'flcw:url';
    var CLEAN_KEY = 'flcw:clean';
    var RELOADS_KEY = 'flcw:reloads';

    var FREEZE_REPORT_MS = 6000;   // a partir daqui, já vale registrar
    var FREEZE_RELOAD_MS = 8000;   // a partir daqui, recarrega
    var JANELA_RAJADA_MS = 5000;   // 2+ erros nesse intervalo = recarrega
    var JANELA_RELOADS_MS = 120000; // 2 minutos
    var MAX_RELOADS_NA_JANELA = 3;

    function ss() {
        try { return window.sessionStorage || null; } catch (e) { return null; }
    }

    // =============================================
    // Checagem de crash da sessão anterior (roda uma vez, no boot)
    // =============================================
    (function checarCrashAnterior() {
        var s = ss();
        if (!s) return;
        try {
            var hb = s.getItem(HB_KEY);
            var limpo = s.getItem(CLEAN_KEY);
            if (hb && limpo !== '1') {
                var idadeMs = Date.now() - parseInt(hb, 10);
                // Só conta como crash se o heartbeat for recente (até
                // 10min) -- uma aba esquecida em segundo plano por
                // horas, com os timers suspensos pelo navegador, não é
                // um travamento de verdade.
                if (!isNaN(idadeMs) && idadeMs >= 0 && idadeMs < 10 * 60 * 1000) {
                    var urlAnterior = s.getItem(URL_KEY) || '(desconhecida)';
                    enviarRelato(
                        'crash_anterior',
                        'A sessão anterior encerrou sem finalização limpa (' + Math.round(idadeMs / 1000) + 's atrás), em ' + urlAnterior,
                        null
                    );
                }
            }
        } catch (e) { /* segue sem checagem */ }

        try {
            s.setItem(CLEAN_KEY, '0');
            s.setItem(HB_KEY, String(Date.now()));
            s.setItem(URL_KEY, location.href);
        } catch (e) { /* sessionStorage indisponível -- sem heartbeat, sem quebra */ }
    })();

    function marcarSaidaLimpa() {
        var s = ss();
        if (!s) return;
        try { s.setItem(CLEAN_KEY, '1'); } catch (e) { /* ignora */ }
    }
    window.addEventListener('pagehide', marcarSaidaLimpa);
    window.addEventListener('beforeunload', marcarSaidaLimpa);

    // =============================================
    // Envio do relato (sendBeacon sobrevive ao reload/fechamento;
    // fetch com keepalive como reserva pra navegadores muito antigos)
    // =============================================
    function enviarRelato(tipo, mensagem, detalhes) {
        try {
            var token = '';
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) token = meta.getAttribute('content') || '';

            var fd = new FormData();
            fd.append('tipo', tipo);
            fd.append('mensagem', String(mensagem || '(sem mensagem)').slice(0, 2000));
            if (detalhes) fd.append('detalhes', String(detalhes).slice(0, 8000));
            fd.append('url', location.href);
            fd.append('csrf_token', token);

            if (navigator.sendBeacon) {
                navigator.sendBeacon(ENDPOINT, fd);
            } else if (window.fetch) {
                fetch(ENDPOINT, { method: 'POST', body: fd, keepalive: true, credentials: 'same-origin' }).catch(function () {});
            }
        } catch (e) { /* o relato nunca pode virar um novo erro */ }
    }

    // =============================================
    // Reload com limite (evita loop de reload)
    // =============================================
    function podeRecarregar() {
        var s = ss();
        if (!s) return true; // sem sessionStorage, não dá pra rastrear -- não bloqueia (fail-open)
        try {
            var estado;
            try { estado = JSON.parse(s.getItem(RELOADS_KEY) || 'null'); } catch (e) { estado = null; }
            var agora = Date.now();
            if (!estado || (agora - estado.inicio) > JANELA_RELOADS_MS) {
                estado = { count: 0, inicio: agora };
            }
            if (estado.count >= MAX_RELOADS_NA_JANELA) return false;
            estado.count += 1;
            s.setItem(RELOADS_KEY, JSON.stringify(estado));
            return true;
        } catch (e) { return true; }
    }

    function mostrarOverlay(mensagem) {
        try {
            var overlay = document.createElement('div');
            overlay.setAttribute('id', 'flcw-overlay');
            overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:rgba(255,255,255,0.96);' +
                'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
                'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;padding:24px;';
            overlay.innerHTML =
                '<div style="width:44px;height:44px;border:4px solid #f3d9c4;border-top-color:#F28C33;' +
                'border-radius:50%;animation:flcw-spin 0.8s linear infinite;"></div>' +
                '<div style="margin-top:16px;color:#F28C33;font-weight:600;font-size:1.05rem;">' + mensagem + '</div>' +
                '<style>@keyframes flcw-spin{to{transform:rotate(360deg)}}</style>';
            (document.body || document.documentElement).appendChild(overlay);
        } catch (e) { /* segue sem overlay -- não impede o reload */ }
    }

    function mostrarAvisoPersistente() {
        try {
            if (document.getElementById('flcw-banner')) return;
            var banner = document.createElement('div');
            banner.setAttribute('id', 'flcw-banner');
            banner.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:2147483647;' +
                'background:#2D2D2D;color:#fff;padding:12px 16px;border-radius:10px;' +
                'display:flex;align-items:center;justify-content:space-between;gap:12px;' +
                'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:0.85rem;' +
                'box-shadow:0 6px 20px rgba(0,0,0,0.25);';
            banner.innerHTML =
                '<span>A aplicação encontrou problemas repetidos. Recarregue a página.</span>' +
                '<button type="button" style="background:#F28C33;color:#fff;border:none;border-radius:8px;' +
                'padding:6px 14px;font-weight:600;white-space:nowrap;">Recarregar</button>';
            banner.querySelector('button').addEventListener('click', function () {
                location.reload();
            });
            (document.body || document.documentElement).appendChild(banner);
        } catch (e) { /* nada a fazer */ }
    }

    function recarregar() {
        if (!podeRecarregar()) {
            mostrarAvisoPersistente();
            return;
        }
        mostrarOverlay('Ops! Tivemos um problema. Atualizando...');
        setTimeout(function () { location.reload(); }, 700);
    }

    // =============================================
    // Erros JS não tratados / promises rejeitadas
    // =============================================
    function extrairInfo(valor) {
        if (valor instanceof Error) {
            return { mensagem: valor.message, detalhes: valor.stack || null };
        }
        if (typeof valor === 'string') {
            return { mensagem: valor, detalhes: null };
        }
        try {
            return { mensagem: JSON.stringify(valor).slice(0, 500), detalhes: null };
        } catch (e) {
            return { mensagem: String(valor), detalhes: null };
        }
    }

    var errosRecentes = [];
    function registrarErroEDecidir(tipo, mensagem, detalhes) {
        enviarRelato(tipo, mensagem, detalhes);
        var agora = Date.now();
        errosRecentes.push(agora);
        errosRecentes = errosRecentes.filter(function (t) { return (agora - t) < JANELA_RAJADA_MS; });
        // 2+ erros não tratados em poucos segundos = app provavelmente
        // travada num estado ruim -- um reload limpo tende a ajudar
        // mais do que continuar tentando renderizar em cima do erro.
        if (errosRecentes.length >= 2) {
            recarregar();
        }
    }

    window.addEventListener('error', function (evt) {
        // Ignora "Script error." sem detalhe -- tipicamente scripts de
        // terceiro/extensão de navegador carregados cross-origin, sem
        // nenhuma informação útil pra diagnosticar ou agir.
        if (!evt || (evt.message === 'Script error.' && !evt.filename)) return;
        var info = evt.error
            ? extrairInfo(evt.error)
            : {
                mensagem: evt.message || 'Erro desconhecido',
                detalhes: evt.filename ? (evt.filename + ':' + evt.lineno + ':' + evt.colno) : null
            };
        registrarErroEDecidir('js_error', info.mensagem, info.detalhes);
    });

    window.addEventListener('unhandledrejection', function (evt) {
        var info = extrairInfo(evt && evt.reason);
        registrarErroEDecidir('promise_rejeitada', info.mensagem, info.detalhes);
    });

    // =============================================
    // Detector de UI travada (thread principal bloqueada)
    // =============================================
    var ultimoFrame = performance.now();
    var ultimaEscritaHeartbeat = 0;

    // Ao voltar de segundo plano, o "gap" entre frames é só o tempo
    // que a aba passou oculta (rAF pausa quando a aba não está
    // visível) -- não é um travamento de verdade, então reseta a
    // referência em vez de medir esse intervalo.
    document.addEventListener('visibilitychange', function () {
        ultimoFrame = performance.now();
    });

    function tick(agora) {
        var gap = agora - ultimoFrame;
        ultimoFrame = agora;

        if (!document.hidden && gap > FREEZE_REPORT_MS) {
            var mensagem = 'UI travada por ' + Math.round(gap) + 'ms';
            enviarRelato('ui_travada', mensagem, null);
            if (gap > FREEZE_RELOAD_MS) {
                recarregar();
            }
        }

        var agoraMs = Date.now();
        if (agoraMs - ultimaEscritaHeartbeat > 1000) {
            ultimaEscritaHeartbeat = agoraMs;
            var s = ss();
            if (s) {
                try {
                    s.setItem(HB_KEY, String(agoraMs));
                    s.setItem(URL_KEY, location.href);
                } catch (e) { /* ignora */ }
            }
        }

        window.requestAnimationFrame(tick);
    }
    window.requestAnimationFrame(tick);
})();
