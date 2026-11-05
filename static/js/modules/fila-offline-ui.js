/**
 * Fila offline de treinos -- parte de tela (só nas páginas, nunca no SW).
 * Depende de fila-offline.js (FitLogFilaOffline).
 *
 * - Aviso flutuante: "sem internet", "N treino(s) aguardando envio",
 *   "entre para enviar", "treino não aceito" (com Tentar de novo/Descartar).
 * - Envio automático: ao abrir a página, quando a internet volta, quando
 *   o app volta para a tela e a cada 60s enquanto houver pendência.
 *   É o caminho que funciona em qualquer aparelho (o iPhone não tem
 *   Background Sync); o Background Sync do Android é só um extra.
 * - Logout: apaga a fila (avisa antes se houver treino não enviado).
 */
(function () {
    'use strict';

    var Fila = window.FitLogFilaOffline;
    if (!Fila) return;

    var INTERVALO_MS = 60000;
    var TEMPO_ATE_COMPACTAR_MS = 6000;
    var compacto = false;
    var timerCompacto = null;

    function meta(nome) {
        var el = document.querySelector('meta[name="' + nome + '"]');
        return el ? el.getAttribute('content') : '';
    }

    var userId = meta('fitlog-user-id');
    var enviando = false;
    var timer = null;
    var el = null;

    function toast(msg, tipo, duracao) {
        if (window.FitLogUtils && typeof window.FitLogUtils.showToast === 'function') {
            window.FitLogUtils.showToast(msg, tipo || 'info', duracao || 5000);
        }
    }

    function formatarData(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
        return m ? m[3] + '/' + m[2] : '';
    }

    function descreverItem(item) {
        var partes = [];
        if (item.resumo && item.resumo.treino) partes.push(item.resumo.treino);
        var d = formatarData(item.resumo && item.resumo.data);
        if (d) partes.push(d);
        return partes.join(' · ');
    }

    function garantirElemento() {
        if (el) return el;
        el = document.createElement('div');
        el.id = 'filaOfflineAviso';
        el.className = 'fila-offline-aviso';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.hidden = true;
        document.body.appendChild(el);
        el.addEventListener('click', function (e) {
            if (el.classList.contains('fila-offline-compacto')) {
                // Ícone de "sem internet": expande de novo e volta a
                // encolher depois de alguns segundos.
                compacto = false;
                atualizar();
                return;
            }
            var botao = e.target.closest('[data-fila-acao]');
            if (!botao) return;
            var acao = botao.getAttribute('data-fila-acao');
            if (acao === 'enviar') {
                enviar({ incluirRecusados: true, manual: true });
            } else if (acao === 'descartar') {
                var id = botao.getAttribute('data-fila-id');
                var confirmar = window.confirm('Descartar este treino? Ele não foi salvo na sua conta e será apagado do aparelho.');
                if (confirmar) Fila.remover(id).then(atualizar);
            } else if (acao === 'login') {
                window.location.href = '/auth/login?next=' + encodeURIComponent(window.location.pathname);
            }
        });
        return el;
    }

    function render(itens) {
        var aviso = garantirElemento();
        var offline = navigator.onLine === false;
        var recusado = itens.filter(function (i) { return i.status === Fila.RECUSADO; })[0];
        var precisaLogin = itens.some(function (i) { return i.status === Fila.PRECISA_LOGIN; });
        var n = itens.length;
        var html = '';
        var estado = '';

        if (recusado) {
            estado = 'erro';
            html = '<i class="bi bi-exclamation-triangle-fill"></i>' +
                '<span class="fila-offline-texto"><strong>Treino não aceito</strong>' +
                (descreverItem(recusado) ? ' (' + escapar(descreverItem(recusado)) + ')' : '') +
                (recusado.motivo ? ': ' + escapar(recusado.motivo) : '') + '</span>' +
                '<span class="fila-offline-acoes">' +
                '<button type="button" data-fila-acao="enviar">Tentar de novo</button>' +
                '<button type="button" data-fila-acao="descartar" data-fila-id="' + escapar(recusado.id) + '">Descartar</button>' +
                '</span>';
        } else if (n > 0 && !userId) {
            estado = 'pendente';
            html = '<i class="bi bi-cloud-arrow-up-fill"></i>' +
                '<span class="fila-offline-texto">' + rotuloQtd(n) + ' no aparelho. Entre na sua conta para enviar.</span>' +
                '<span class="fila-offline-acoes"><button type="button" data-fila-acao="login">Entrar</button></span>';
        } else if (n > 0) {
            estado = 'pendente';
            var texto;
            if (enviando) texto = 'Enviando ' + (n === 1 ? 'treino salvo no aparelho...' : n + ' treinos salvos no aparelho...');
            else if (precisaLogin) texto = rotuloQtd(n) + ' no aparelho. Entre de novo na sua conta para enviar.';
            else if (offline) texto = rotuloQtd(n) + ' no aparelho. Será enviado quando a internet voltar.';
            else texto = rotuloQtd(n) + ' no aparelho, aguardando envio.';
            html = '<i class="bi ' + (enviando ? 'bi-arrow-repeat fila-offline-girando' : 'bi-cloud-arrow-up-fill') + '"></i>' +
                '<span class="fila-offline-texto">' + texto + '</span>';
            if (!enviando && !offline) {
                html += '<span class="fila-offline-acoes"><button type="button" data-fila-acao="' +
                    (precisaLogin ? 'login">Entrar' : 'enviar">Enviar agora') + '</button></span>';
            }
        } else if (offline) {
            estado = 'offline';
            // Na tela de registro o que importa é saber que dá para seguir
            // o treino e salvar; nas outras, que a tela pode não abrir.
            var noTreino = !!document.getElementById('registroForm');
            html = '<i class="bi bi-wifi-off"></i><span class="fila-offline-texto">' +
                (noTreino
                    ? '<strong>Sem internet.</strong> Pode continuar o treino: ao salvar, ele fica guardado no aparelho e é enviado quando a conexão voltar.'
                    : '<strong>Sem internet.</strong> Algumas telas podem não abrir até a conexão voltar.') +
                '</span>';
        }

        // "Sem internet" sem treino pendente encolhe para um ícone depois de
        // alguns segundos: na academia sem sinal ele ficaria o treino inteiro
        // por cima dos exercícios. Tocar no ícone mostra o texto de novo.
        if (estado !== 'offline') {
            compacto = false;
            clearTimeout(timerCompacto);
            timerCompacto = null;
        } else if (!compacto && !timerCompacto) {
            timerCompacto = setTimeout(function () {
                timerCompacto = null;
                compacto = true;
                if (el && el.getAttribute('data-estado') === 'offline') el.classList.add('fila-offline-compacto');
                posicionar();
            }, TEMPO_ATE_COMPACTAR_MS);
        }

        aviso.innerHTML = html;
        aviso.setAttribute('data-estado', estado);
        aviso.classList.toggle('fila-offline-compacto', estado === 'offline' && compacto);
        aviso.setAttribute('aria-label', estado === 'offline' && compacto ? 'Sem internet. Toque para ver detalhes.' : '');
        if (!(estado === 'offline' && compacto)) aviso.removeAttribute('aria-label');
        aviso.hidden = !html;
        document.documentElement.classList.toggle('fila-offline-visivel', !!html);
        posicionar();
    }

    // No modo treino (registrar_treino.html) o rodapé com o cronômetro de
    // descanso tem altura variável (1 ou 2 linhas, flutuante ou não): mede
    // onde ele começa para o aviso ficar logo acima, sem cobrir os botões.
    function posicionar() {
        if (!el || el.hidden) return;
        var rodape = document.getElementById('modoTreinoFooter');
        var altura = 0;
        if (document.body.classList.contains('fl-modo-treino-ativo') && rodape && rodape.offsetParent !== null) {
            var r = rodape.getBoundingClientRect();
            if (r.height > 0) altura = Math.max(0, window.innerHeight - r.top);
        }
        if (altura) el.style.setProperty('--fila-offline-rodape', altura + 'px');
        else el.style.removeProperty('--fila-offline-rodape');
    }

    // Entrar/sair do modo treino troca a classe do <body>; o rodapé também
    // muda de altura (cronômetro vira flutuante, presets aparecem).
    if (window.MutationObserver) {
        new MutationObserver(posicionar).observe(document.body || document.documentElement, {
            attributes: true, attributeFilter: ['class']
        });
    }
    window.addEventListener('resize', posicionar);
    document.addEventListener('DOMContentLoaded', function () {
        var rodape = document.getElementById('modoTreinoFooter');
        if (rodape && window.ResizeObserver) new ResizeObserver(posicionar).observe(rodape);
    });

    function rotuloQtd(n) {
        return n === 1 ? '1 treino salvo' : n + ' treinos salvos';
    }

    function escapar(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function itensVisiveis() {
        // Logado: só os próprios treinos. Deslogado: tudo (para avisar
        // que há treino esperando login -- sem mostrar de quem é).
        return userId ? Fila.listarDoUsuario(userId) : Fila.listar();
    }

    function atualizar() {
        return itensVisiveis().then(function (itens) {
            render(itens);
            agendar(itens.length > 0);
            return itens;
        });
    }

    function agendar(temPendencia) {
        if (timer) { clearInterval(timer); timer = null; }
        if (temPendencia && userId) {
            timer = setInterval(function () { enviar(); }, INTERVALO_MS);
        }
    }

    function enviar(opcoes) {
        opcoes = opcoes || {};
        if (enviando) return Promise.resolve();
        if (!userId) return atualizar();
        if (navigator.onLine === false && !opcoes.manual) return atualizar();
        return Fila.listarDoUsuario(userId).then(function (itens) {
            if (!itens.length) return atualizar();
            enviando = true;
            render(itens);
            return Fila.enviarTodos({
                userId: userId,
                csrfToken: meta('csrf-token'),
                incluirRecusados: !!opcoes.incluirRecusados
            }).then(function (r) {
                enviando = false;
                if (r && r.enviados && r.enviados.length) {
                    var desc = r.enviados.length === 1 ? descreverItem(r.enviados[0]) : '';
                    toast(r.enviados.length === 1
                        ? 'Treino enviado para a sua conta' + (desc ? ' (' + desc + ')' : '') + '.'
                        : r.enviados.length + ' treinos enviados para a sua conta.', 'success', 5000);
                } else if (opcoes.manual && r && r.semRede) {
                    toast('Ainda sem conexão. O treino continua salvo no aparelho.', 'warning', 5000);
                }
                return atualizar();
            }, function () {
                enviando = false;
                return atualizar();
            });
        });
    }

    /**
     * Chamado pela tela de registro quando o salvamento falha por rede.
     * Resolve com true se o treino ficou guardado no aparelho.
     */
    function guardarTreino(form, resumo) {
        if (!userId) return Promise.resolve(false);
        return Fila.adicionar({
            url: form.action || window.location.href,
            campos: Fila.camposDoFormData(new FormData(form)),
            userId: userId,
            resumo: resumo
        }).then(function () {
            registrarSync();
            atualizar();
            return true;
        }, function () {
            return false;
        });
    }

    function registrarSync() {
        if (!('serviceWorker' in navigator)) return;
        navigator.serviceWorker.ready.then(function (reg) {
            if (reg.sync && typeof reg.sync.register === 'function') {
                return reg.sync.register(Fila.TAG_SYNC);
            }
        }).catch(function () { /* sem Background Sync (iPhone/Firefox): o envio fica com esta página */ });
    }

    // Logout: apaga a fila do aparelho (aparelho compartilhado). Avisa
    // antes se houver treino ainda não enviado.
    document.addEventListener('click', function (e) {
        var link = e.target.closest('a[href$="/auth/logout"]');
        if (!link) return;
        e.preventDefault();
        var destino = link.href;
        Fila.listar().then(function (itens) {
            if (itens.length) {
                var ok = window.confirm(
                    (itens.length === 1 ? 'Há 1 treino salvo no aparelho que ainda não foi enviado.'
                        : 'Há ' + itens.length + ' treinos salvos no aparelho que ainda não foram enviados.') +
                    ' Se sair agora, ele' + (itens.length === 1 ? ' será apagado' : 's serão apagados') + '. Sair mesmo assim?');
                if (!ok) return;
            }
            return Fila.limpar().then(function () { window.location.href = destino; });
        }, function () { window.location.href = destino; });
    }, true);

    // O SW avisa quando o Background Sync enviou algo com a página aberta
    // em segundo plano.
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('message', function (e) {
            if (e.data && e.data.tipo === 'fila-offline-atualizada') atualizar();
        });
    }

    window.addEventListener('online', function () { enviar(); });
    window.addEventListener('offline', atualizar);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) enviar();
    });

    Fila.ui = { atualizar: atualizar, enviar: enviar, guardarTreino: guardarTreino };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { enviar(); });
    } else {
        enviar();
    }
})();