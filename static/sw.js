// Service Worker mínimo do FitLog.
//
// Propositalmente NÃO faz cache agressivo: a aplicação é dinâmica
// (login, CSRF token, dados de treino), então cachear respostas
// poderia servir páginas desatualizadas ou quebrar o CSRF.
// A única função dele aqui é satisfazer o requisito do navegador
// para permitir "Instalar app" / adicionar à tela inicial.

const CACHE_NAME = 'fitlog-shell-v1';

// Só os assets realmente estáticos (não mudam por usuário/sessão)
const SHELL_ASSETS = [
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/images/logo.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(SHELL_ASSETS))
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
    // Só intercepta os assets estáticos conhecidos (cache-first).
    // Tudo o resto (páginas, formulários, APIs) vai direto pra rede,
    // sem cache, pra nunca servir conteúdo desatualizado.
    const url = new URL(event.request.url);

    if (SHELL_ASSETS.includes(url.pathname)) {
        event.respondWith(
            caches.match(event.request).then((cached) => cached || fetch(event.request))
        );
        return;
    }

    // Passthrough padrão — mantém o comportamento normal de rede
    event.respondWith(fetch(event.request));
});
