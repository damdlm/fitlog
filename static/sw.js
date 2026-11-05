// Service Worker mínimo do FitLog.
//
// Propositalmente NÃO faz cache agressivo: a aplicação é dinâmica
// (login, CSRF token, dados de treino), então cachear respostas
// poderia servir páginas desatualizadas ou quebrar o CSRF.
// Funções: satisfazer o requisito do navegador para "Instalar app",
// servir a página offline quando a navegação falha e enviar a fila
// offline de treinos via Background Sync (Android/Chrome -- ver
// static/js/modules/fila-offline.js).

importScripts('/static/js/modules/fila-offline.js');

const CACHE_NAME = 'fitlog-shell-v4'; // bump pra forçar re-precache (v3: fila offline; v4: offline.html sem zoom)

// Só os assets realmente estáticos (não mudam por usuário/sessão)
const SHELL_ASSETS = [
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/images/logo.png',
    '/static/offline.html',
    // Usado pela offline.html para mostrar os treinos guardados no aparelho.
    '/static/js/modules/fila-offline.js',
];

const OFFLINE_URL = '/static/offline.html';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            // cache: 'reload' -- busca do servidor, nunca do cache HTTP do
            // navegador; senão uma versão nova (ex: offline.html) podia
            // entrar no cache novo ainda com o conteúdo antigo.
            .then((cache) => cache.addAll(SHELL_ASSETS.map((url) => new Request(url, { cache: 'reload' }))))
            .catch(() => {}) // não trava a instalação se algum asset falhar
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    // Nunca intercepta métodos de escrita (POST/PUT/PATCH/DELETE) --
    // login, salvar treino, qualquer coisa protegida por CSRF passa
    // direto pro navegador, sem o Service Worker no meio. Isso é
    // puramente defensivo: mesmo que o passthrough abaixo tecnicamente
    // desse o mesmo resultado, uma ação sensível nunca deveria depender
    // de o SW "deixar passar" corretamente.
    if (event.request.method !== 'GET') {
        return;
    }

    const url = new URL(event.request.url);

    // Requisições de terceiros (CDNs externos: cdn.jsdelivr.net,
    // cdnjs.cloudflare.com etc.) -- NÃO interceptar. Passar tudo por
    // event.respondWith(fetch(...)) mesmo pra recursos cross-origin faz
    // esse fetch "reproxeado" perder a resiliência normal do navegador
    // (retry/conexão reaproveitada); qualquer soluço vira falha definitiva
    // do <script>/<link>, sem chance de recuperação -- foi o que quebrava
    // Chart.js/FullCalendar depois que o service worker passou a existir.
    // Deixando esses requests passarem batido (sem chamar respondWith),
    // o navegador trata a requisição normalmente, como se o SW nem
    // existisse pra ela.
    if (url.origin !== self.location.origin) {
        return;
    }

    // Só intercepta os assets estáticos conhecidos (cache-first).
    // Tudo o resto (páginas, formulários, APIs) vai direto pra rede,
    // sem cache, pra nunca servir conteúdo desatualizado.
    if (SHELL_ASSETS.includes(url.pathname)) {
        // Network-first para o JS da fila (muda a cada deploy e as páginas
        // o pedem com ?v=); cache só como reserva offline. Os demais
        // (ícones, offline.html) seguem cache-first.
        if (url.pathname.endsWith('.js')) {
            event.respondWith(
                fetch(event.request).catch(() =>
                    caches.match(url.pathname).then((cached) => cached || Response.error())
                )
            );
            return;
        }
        event.respondWith(
            caches.match(event.request).then((cached) => cached || fetch(event.request))
        );
        return;
    }

    // Navegação (o usuário abrindo/recarregando uma página, não um
    // fetch de API/asset) -- se a rede falhar (sem internet), em vez
    // de deixar a promise do fetch() rejeitar dentro do respondWith
    // (o que gera o erro "FetchEvent.respondWith received an error"
    // e a tela de erro feia do Safari/Chrome), serve a página offline
    // que ficou cacheada no install.
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    // Passthrough padrão — mantém o comportamento normal de rede
    // pra tudo que não é navegação (chamadas de API, etc.)
    event.respondWith(fetch(event.request));
});

// Background Sync (Android/Chrome): o navegador dispara quando a conexão
// volta, mesmo com o app fechado. No iPhone não existe -- lá a própria
// página envia ao abrir/voltar a internet (fila-offline-ui.js).
// Sem userId/csrfToken: o servidor confere o dono pelo campo
// fila_offline_user_id e o token guardado é o da sessão que registrou.
self.addEventListener('sync', (event) => {
    if (event.tag !== self.FitLogFilaOffline.TAG_SYNC) return;
    event.waitUntil(
        self.FitLogFilaOffline.enviarTodos({}).then((r) => {
            return self.clients.matchAll({ includeUncontrolled: true }).then((clientes) => {
                clientes.forEach((c) => c.postMessage({ tipo: 'fila-offline-atualizada' }));
                // Ainda sem rede: rejeitar faz o navegador tentar de novo mais tarde.
                if (r && r.semRede) throw new Error('sem rede');
            });
        })
    );
});