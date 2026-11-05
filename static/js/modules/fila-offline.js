/**
 * Fila offline de treinos -- núcleo (sem DOM).
 *
 * Carregado em DOIS lugares:
 *   - nas páginas (base.html, offline.html), via <script>;
 *   - no service worker (sw.js), via importScripts(), para o Background
 *     Sync do Android/Chrome conseguir enviar com o app fechado.
 * Por isso não toca em `window`/`document`: usa só `self`, IndexedDB,
 * fetch e FormData, que existem nos dois contextos.
 *
 * Fluxo: o salvamento do treino falha por falta de rede -> o formulário
 * inteiro (pares nome/valor) vai para o IndexedDB -> é reenviado
 * quando a internet volta / o app é aberto / o Background Sync dispara.
 * O servidor substitui a sessão do mesmo treino+data
 * (RegistroService.salvar_registros), então reenviar não duplica.
 *
 * Segurança em aparelho compartilhado: cada item guarda o id do usuário
 * que registrou, e o formulário leva o campo `fila_offline_user_id`. O
 * servidor recusa se quem estiver logado na hora do envio for outra
 * pessoa (routes/register_routes.py:salvar_registro). A fila também é
 * apagada no logout (fila-offline-ui.js).
 */
(function (root) {
    'use strict';

    var DB_NOME = 'fitlog-fila-offline';
    var DB_VERSAO = 1;
    var STORE = 'treinos';
    var TAG_SYNC = 'fitlog-fila-treinos';
    var VALIDADE_MS = 14 * 24 * 60 * 60 * 1000; // 14 dias: depois disso o item é descartado
    var TIMEOUT_ENVIO_MS = 25000;

    // Status de um item na fila
    var PENDENTE = 'pendente';         // aguardando rede (ou erro temporário do servidor)
    var PRECISA_LOGIN = 'precisa_login'; // sessão caiu: só envia depois de entrar de novo
    var RECUSADO = 'recusado';         // servidor recusou (validação): precisa de decisão do usuário

    function abrirDb() {
        return new Promise(function (resolve, reject) {
            if (!root.indexedDB) {
                reject(new Error('IndexedDB indisponível'));
                return;
            }
            var req = root.indexedDB.open(DB_NOME, DB_VERSAO);
            req.onupgradeneeded = function () {
                var db = req.result;
                if (!db.objectStoreNames.contains(STORE)) {
                    db.createObjectStore(STORE, { keyPath: 'id' });
                }
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function transacao(modo, fn) {
        return abrirDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, modo);
                var store = tx.objectStore(STORE);
                var resultado;
                Promise.resolve(fn(store)).then(function (r) { resultado = r; });
                tx.oncomplete = function () { db.close(); resolve(resultado); };
                tx.onerror = function () { db.close(); reject(tx.error); };
                tx.onabort = function () { db.close(); reject(tx.error); };
            });
        });
    }

    function requisicao(req) {
        return new Promise(function (resolve, reject) {
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function valorCampo(campos, nome) {
        for (var i = 0; i < campos.length; i++) {
            if (campos[i][0] === nome) return campos[i][1];
        }
        return '';
    }

    /**
     * Converte um FormData em lista de pares [nome, valor] (só texto --
     * o formulário de treino não tem arquivo). Lista, e não objeto, porque
     * há campos repetidos (ex: avulso_exercicios[]).
     */
    function camposDoFormData(formData) {
        var campos = [];
        formData.forEach(function (valor, nome) {
            if (typeof valor === 'string') campos.push([nome, valor]);
        });
        return campos;
    }

    /**
     * Guarda um treino na fila. Se já existir um item do mesmo usuário,
     * treino e data, ele é substituído (o último salvamento vale -- igual
     * ao servidor).
     *
     * @param {Object} dados {url, campos, userId, resumo: {treino, data}}
     * @returns {Promise<Object>} o item salvo
     */
    function adicionar(dados) {
        var campos = (dados.campos || []).filter(function (par) {
            return par[0] !== 'fila_offline_user_id';
        });
        campos.push(['fila_offline_user_id', String(dados.userId)]);

        var treino = valorCampo(campos, 'treino');
        var data = valorCampo(campos, 'data');
        var item = {
            id: [dados.userId, treino, data].join('|'),
            url: dados.url,
            campos: campos,
            userId: String(dados.userId),
            resumo: dados.resumo || { treino: '', data: data },
            criadoEm: Date.now(),
            tentativas: 0,
            status: PENDENTE,
            motivo: ''
        };
        return transacao('readwrite', function (store) {
            store.put(item);
        }).then(function () { return item; });
    }

    function listar() {
        return transacao('readonly', function (store) {
            return requisicao(store.getAll());
        }).then(function (itens) {
            itens = itens || [];
            var agora = Date.now();
            var validos = itens.filter(function (i) { return agora - i.criadoEm < VALIDADE_MS; });
            var vencidos = itens.filter(function (i) { return agora - i.criadoEm >= VALIDADE_MS; });
            if (vencidos.length) {
                transacao('readwrite', function (store) {
                    vencidos.forEach(function (i) { store.delete(i.id); });
                }).catch(function () {});
            }
            validos.sort(function (a, b) { return a.criadoEm - b.criadoEm; });
            return validos;
        }).catch(function () { return []; });
    }

    function listarDoUsuario(userId) {
        return listar().then(function (itens) {
            return itens.filter(function (i) { return i.userId === String(userId); });
        });
    }

    function salvarItem(item) {
        return transacao('readwrite', function (store) { store.put(item); });
    }

    function remover(id) {
        return transacao('readwrite', function (store) { store.delete(id); });
    }

    function limpar() {
        return transacao('readwrite', function (store) { store.clear(); }).catch(function () {});
    }

    /** Tenta extrair o texto do aviso (flash) de erro do HTML devolvido. */
    function extrairMotivo(html) {
        var m = /<div[^>]*id=["']flash-messages["'][\s\S]*?alert-(?:danger|warning)[^>]*>([\s\S]*?)<\/div>/i.exec(html || '');
        if (!m) return '';
        var entidades = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&#34;': '"' };
        return m[1]
            .replace(/<[^>]+>/g, ' ')
            .replace(/&(amp|lt|gt|quot|#39|#34);/g, function (e) { return entidades[e]; })
            .replace(/\s+/g, ' ')
            .trim();
    }

    function fetchComTimeout(url, opcoes, ms) {
        if (typeof AbortController === 'undefined') return fetch(url, opcoes);
        var controller = new AbortController();
        var timer = setTimeout(function () { controller.abort(); }, ms);
        opcoes.signal = controller.signal;
        return fetch(url, opcoes).then(function (r) {
            clearTimeout(timer);
            return r;
        }, function (e) {
            clearTimeout(timer);
            throw e;
        });
    }

    /**
     * Envia um item. Resolve com {resultado: 'enviado'|'rede'|PRECISA_LOGIN|RECUSADO|'tentar_depois'}.
     * Nunca rejeita.
     */
    function enviarItem(item, csrfToken) {
        var fd = new FormData();
        item.campos.forEach(function (par) {
            // O token da página atual vale mais que o guardado: se a
            // sessão foi renovada (login de novo), o antigo não serve.
            if (par[0] === 'csrf_token' && csrfToken) return;
            fd.append(par[0], par[1]);
        });
        if (csrfToken) fd.append('csrf_token', csrfToken);

        return fetchComTimeout(item.url, {
            method: 'POST',
            body: fd,
            credentials: 'same-origin'
        }, TIMEOUT_ENVIO_MS).then(function (resp) {
            var url = resp.url || '';
            // Ordem importa: o redirect para o login leva
            // ?next=/registrar-treino na própria URL.
            if (url.indexOf('/auth/login') !== -1) {
                return { resultado: PRECISA_LOGIN };
            }
            if (resp.status === 429 || resp.status >= 500) {
                return { resultado: 'tentar_depois' };
            }
            if (resp.ok && url.indexOf('/registrar-treino') === -1) {
                return { resultado: 'enviado' };
            }
            return resp.text().then(function (html) {
                var motivo = extrairMotivo(html);
                if (!motivo && resp.status === 400) {
                    motivo = 'A sessão de segurança expirou. Toque em "Tentar de novo".';
                }
                return { resultado: RECUSADO, motivo: motivo };
            }, function () {
                return { resultado: RECUSADO, motivo: '' };
            });
        }, function () {
            return { resultado: 'rede' };
        });
    }

    function comLock(fn) {
        // Página e service worker podem tentar enviar ao mesmo tempo. O
        // servidor aguenta (substitui a sessão), mas o lock evita POST
        // duplicado à toa. Web Locks existe no Chrome e no Safari 15.4+;
        // sem ele, segue sem lock.
        var locks = root.navigator && root.navigator.locks;
        if (locks && typeof locks.request === 'function') {
            return locks.request('fitlog-fila-offline-envio', { ifAvailable: true }, function (lock) {
                if (!lock) return { ocupado: true, enviados: [], restantes: null };
                return fn();
            });
        }
        return fn();
    }

    /**
     * Envia os itens pendentes.
     *
     * @param {Object} opcoes
     *   userId: só envia os itens desse usuário (página). Omitido no SW:
     *           o servidor confere o dono pelo campo fila_offline_user_id.
     *   csrfToken: token da página atual (omitido no SW).
     *   incluirRecusados: reenviar também os recusados (botão "Tentar de novo").
     * @returns {Promise<{enviados: Array, restantes: number}>}
     */
    function enviarTodos(opcoes) {
        opcoes = opcoes || {};
        return comLock(function () {
            return listar().then(function (itens) {
                var alvo = itens.filter(function (i) {
                    if (opcoes.userId != null && i.userId !== String(opcoes.userId)) return false;
                    if (i.status === RECUSADO && !opcoes.incluirRecusados) return false;
                    // Sem token novo (SW), um item que já pediu login continua esperando.
                    if (i.status === PRECISA_LOGIN && !opcoes.csrfToken) return false;
                    return true;
                });
                var enviados = [];
                var semRede = false;

                return alvo.reduce(function (cadeia, item) {
                    return cadeia.then(function () {
                        if (semRede) return;
                        return enviarItem(item, opcoes.csrfToken).then(function (r) {
                            if (r.resultado === 'enviado') {
                                enviados.push(item);
                                return remover(item.id);
                            }
                            if (r.resultado === 'rede') {
                                semRede = true; // não adianta tentar os próximos agora
                                return;
                            }
                            item.tentativas += 1;
                            if (r.resultado === PRECISA_LOGIN) {
                                item.status = PRECISA_LOGIN;
                            } else if (r.resultado === RECUSADO) {
                                item.status = RECUSADO;
                                item.motivo = r.motivo || '';
                            } else {
                                item.status = PENDENTE;
                            }
                            return salvarItem(item);
                        });
                    });
                }, Promise.resolve()).then(function () {
                    return listar().then(function (resto) {
                        return { enviados: enviados, restantes: resto.length, semRede: semRede };
                    });
                });
            });
        });
    }

    root.FitLogFilaOffline = {
        TAG_SYNC: TAG_SYNC,
        PENDENTE: PENDENTE,
        PRECISA_LOGIN: PRECISA_LOGIN,
        RECUSADO: RECUSADO,
        camposDoFormData: camposDoFormData,
        adicionar: adicionar,
        listar: listar,
        listarDoUsuario: listarDoUsuario,
        remover: remover,
        limpar: limpar,
        enviarTodos: enviarTodos,
        _extrairMotivo: extrairMotivo
    };
})(typeof self !== 'undefined' ? self : this);
