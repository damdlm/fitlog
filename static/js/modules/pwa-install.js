/**
 * InstallManager — controlador único da experiência de instalação do PWA.
 *
 * Segue o mesmo padrão dos outros módulos (IIFE + objeto exposto em
 * window), ver static/js/modules/csrf.js e exercicio-imagens.js.
 *
 * Responsável por:
 *  - detectar plataforma (iOS / Android / Desktop / Safari / Chromium);
 *  - detectar se o app já está instalado (display-mode / navigator.standalone);
 *  - capturar o evento `beforeinstallprompt` (Android/Desktop) e expor um
 *    botão próprio do FitLog em vez do prompt automático do navegador;
 *  - mostrar um tutorial visual no iOS/iPadOS (não suporta prompt nativo);
 *  - controlar a frequência dos avisos via localStorage;
 *  - alimentar o item fixo "Instalar aplicativo" no menu do usuário.
 *
 * Não depende de bibliotecas externas -- só JS nativo, para não adicionar
 * peso desnecessário só por causa dessa funcionalidade.
 */
const InstallManager = (function () {
    'use strict';

    // Chave única no localStorage. Guarda um JSON: { installed, dismissedAt }
    const STORAGE_KEY = 'fitlog_pwa_install_v1';

    // Depois que o usuário fecha o aviso, quantos dias esperar antes de
    // voltar a sugerir a instalação.
    const DISMISS_COOLDOWN_DAYS = 7;

    // Espera um pouco antes de sugerir a instalação automaticamente, pra
    // não interromper a primeira coisa que o usuário for fazer na página.
    const AUTO_SHOW_DELAY_MS = 4000;

    let deferredPrompt = null;   // evento beforeinstallprompt guardado
    let platform = null;         // resultado de detectPlatform()
    let bannerEl = null;         // elemento do banner/bottom-sheet Android/Desktop
    let iosSheetEl = null;       // elemento do tutorial iOS
    let menuItemEl = null;       // <li> "Instalar aplicativo" no dropdown
    let autoShowTimer = null;
    let initialized = false;

    // ---------------------------------------------------------------
    // Armazenamento (localStorage) -- tudo centralizado aqui, sem
    // valores/chaves soltos pelo resto do código.
    // ---------------------------------------------------------------

    function readState() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (e) {
            return {};
        }
    }

    function writeState(patch) {
        try {
            const state = Object.assign(readState(), patch);
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            // localStorage indisponível (modo privado, quota etc.) -- não
            // trava a funcionalidade, só perde a memória entre visitas.
        }
    }

    /**
     * Decide se o aviso automático (banner/bottom-sheet) pode aparecer
     * agora. Não afeta o item do menu, que fica disponível sempre que a
     * instalação for possível.
     */
    function shouldShowInstallPrompt() {
        if (isAppInstalled()) return false;

        const state = readState();
        if (state.installed) return false;

        if (state.dismissedAt) {
            const diasDesdeDispensa = (Date.now() - state.dismissedAt) / (1000 * 60 * 60 * 24);
            if (diasDesdeDispensa < DISMISS_COOLDOWN_DAYS) return false;
        }

        return true;
    }

    // ---------------------------------------------------------------
    // Detecção de ambiente
    // ---------------------------------------------------------------

    /**
     * true se o FitLog já estiver rodando como app instalado (janela
     * standalone). Cobre Android/Desktop (display-mode) e iOS
     * (navigator.standalone, API específica da Apple).
     */
    function isAppInstalled() {
        try {
            if (window.matchMedia && (
                window.matchMedia('(display-mode: standalone)').matches ||
                window.matchMedia('(display-mode: window-controls-overlay)').matches
            )) {
                return true;
            }
            if (window.navigator && window.navigator.standalone === true) {
                return true;
            }
        } catch (e) {
            // matchMedia indisponível em navegador muito antigo -- ignora
        }
        return false;
    }

    /**
     * Identifica plataforma/navegador. Combina user-agent com detecção de
     * recursos (touch, maxTouchPoints) para cobrir o caso do iPadOS 13+,
     * que se identifica como "MacIntel" no user-agent.
     */
    function detectPlatform() {
        const ua = window.navigator.userAgent || window.navigator.vendor || '';

        const isIOSPorUA = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
        const isIPadOSComoMac = window.navigator.platform === 'MacIntel'
            && typeof window.navigator.maxTouchPoints === 'number'
            && window.navigator.maxTouchPoints > 1;
        const isIOS = isIOSPorUA || isIPadOSComoMac;

        const isAndroid = /Android/.test(ua);

        // Safari "de verdade": tem "Safari" no UA mas não é Chrome/Chromium/
        // Android (esses navegadores também incluem "Safari" no UA por
        // compatibilidade).
        const isSafari = /Safari/.test(ua) && !/Chrome|Chromium|CriOS|Android|Edg|OPR/.test(ua);

        const isChromium = /Chrome|Chromium|CriOS|Edg|OPR/.test(ua) && !isSafari;

        const isDesktop = !isIOS && !isAndroid;

        return { isIOS, isAndroid, isDesktop, isSafari, isChromium };
    }

    // ---------------------------------------------------------------
    // Construção da UI (banner Android/Desktop + tutorial iOS)
    // Os elementos são criados uma única vez e reaproveitados.
    // ---------------------------------------------------------------

    function garantirBanner() {
        if (bannerEl) return bannerEl;

        const el = document.createElement('div');
        el.id = 'pwaInstallBanner';
        el.className = 'pwa-install-sheet';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-label', 'Instalar aplicativo FitLog');
        el.innerHTML = `
            <div class="pwa-install-sheet-content">
                <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                <div class="pwa-install-text">
                    <strong>Instalar FitLog</strong>
                    <span>Acesse seus treinos direto da tela inicial, mais rápido e sem precisar do navegador.</span>
                </div>
                <div class="pwa-install-actions">
                    <button type="button" class="btn-pwa-dismiss" aria-label="Fechar">Agora não</button>
                    <button type="button" class="btn-pwa-install">Instalar</button>
                </div>
            </div>
        `;
        document.body.appendChild(el);

        el.querySelector('.btn-pwa-install').addEventListener('click', handleInstall);
        el.querySelector('.btn-pwa-dismiss').addEventListener('click', handleDismiss);

        bannerEl = el;
        return el;
    }

    function garantirTutorialIOS() {
        if (iosSheetEl) return iosSheetEl;

        const el = document.createElement('div');
        el.id = 'pwaIosSheet';
        el.className = 'pwa-install-sheet pwa-ios-sheet';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-label', 'Como instalar o FitLog no iPhone/iPad');
        el.innerHTML = `
            <div class="pwa-install-sheet-content pwa-ios-sheet-content">
                <button type="button" class="btn-pwa-close" aria-label="Fechar">&times;</button>
                <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                <strong>📲 Instale o FitLog</strong>
                <p>Para instalar este aplicativo no seu iPhone ou iPad:</p>
                <ol class="pwa-ios-steps">
                    <li><i class="bi bi-box-arrow-up"></i> Toque em <strong>Compartilhar</strong></li>
                    <li><i class="bi bi-plus-square"></i> Selecione <strong>"Adicionar à Tela de Início"</strong></li>
                </ol>
                <button type="button" class="btn-pwa-install btn-pwa-entendi">Entendi</button>
            </div>
        `;
        document.body.appendChild(el);

        el.querySelector('.btn-pwa-close').addEventListener('click', handleDismiss);
        el.querySelector('.btn-pwa-entendi').addEventListener('click', handleDismiss);

        iosSheetEl = el;
        return el;
    }

    function showInstallButton() {
        if (!platform.isIOS) {
            garantirBanner().classList.add('is-visible');
        }
    }

    function hideInstallButton() {
        if (bannerEl) bannerEl.classList.remove('is-visible');
    }

    function showIOSInstructions() {
        garantirTutorialIOS().classList.add('is-visible');
    }

    function hideIOSInstructions() {
        if (iosSheetEl) iosSheetEl.classList.remove('is-visible');
    }

    // ---------------------------------------------------------------
    // Item fixo no menu ("Instalar aplicativo")
    // ---------------------------------------------------------------

    function atualizarVisibilidadeMenu() {
        if (!menuItemEl) return;
        const disponivel = !isAppInstalled() && (!!deferredPrompt || platform.isIOS);
        menuItemEl.style.display = disponivel ? '' : 'none';
    }

    function ligarMenuItem() {
        menuItemEl = document.getElementById('pwaMenuInstallItem');
        if (!menuItemEl) return;

        const link = menuItemEl.querySelector('a, button');
        if (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                handleInstall();
            });
        }
        atualizarVisibilidadeMenu();
    }

    // ---------------------------------------------------------------
    // Ações
    // ---------------------------------------------------------------

    function handleInstall() {
        hideInstallButton();

        if (deferredPrompt) {
            const promptCapturado = deferredPrompt;
            deferredPrompt = null;

            promptCapturado.prompt();
            promptCapturado.userChoice
                .then(function (resultado) {
                    if (resultado && resultado.outcome === 'accepted') {
                        writeState({ installed: true });
                    } else {
                        writeState({ dismissedAt: Date.now() });
                    }
                    atualizarVisibilidadeMenu();
                })
                .catch(function () {
                    // Sem suporte a userChoice ou prompt cancelado -- não faz nada além
                    // de já ter escondido o banner.
                });
            return;
        }

        if (platform.isIOS) {
            showIOSInstructions();
        }
    }

    function handleDismiss() {
        hideInstallButton();
        hideIOSInstructions();
        writeState({ dismissedAt: Date.now() });
    }

    function agendarExibicaoAutomatica() {
        if (autoShowTimer) return;
        autoShowTimer = window.setTimeout(function () {
            if (!shouldShowInstallPrompt()) return;

            if (platform.isIOS) {
                showIOSInstructions();
            } else if (deferredPrompt) {
                showInstallButton();
            }
        }, AUTO_SHOW_DELAY_MS);
    }

    // ---------------------------------------------------------------
    // Eventos do navegador
    // ---------------------------------------------------------------

    function handleBeforeInstallPrompt(event) {
        // Impede o mini-infobar automático do Chrome -- quem decide quando
        // mostrar o convite de instalação é o FitLog, não o navegador.
        event.preventDefault();
        deferredPrompt = event;
        atualizarVisibilidadeMenu();
        agendarExibicaoAutomatica();
    }

    function handleAppInstalled() {
        writeState({ installed: true, dismissedAt: null });
        deferredPrompt = null;
        hideInstallButton();
        hideIOSInstructions();
        atualizarVisibilidadeMenu();
        if (window.console) console.log('✅ FitLog instalado como aplicativo');
    }

    // ---------------------------------------------------------------
    // Inicialização
    // ---------------------------------------------------------------

    function init() {
        if (initialized) return;
        initialized = true;

        platform = detectPlatform();

        if (isAppInstalled()) {
            // Já é PWA instalado: não há nada a oferecer, só garante que o
            // estado fique consistente para a próxima checagem.
            writeState({ installed: true });
            return;
        }

        if ('addEventListener' in window) {
            window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
            window.addEventListener('appinstalled', handleAppInstalled);
        }

        ligarMenuItem();

        // No iOS não existe beforeinstallprompt -- se ainda não foi
        // instalado nem dispensado recentemente, agenda o tutorial.
        if (platform.isIOS) {
            agendarExibicaoAutomatica();
        }

        atualizarVisibilidadeMenu();
    }

    // API pública
    return {
        init: init,
        isAppInstalled: isAppInstalled,
        detectPlatform: detectPlatform,
        shouldShowInstallPrompt: shouldShowInstallPrompt,
        showInstallButton: showInstallButton,
        hideInstallButton: hideInstallButton,
        showIOSInstructions: showIOSInstructions,
        hideIOSInstructions: hideIOSInstructions,
        handleInstall: handleInstall,
        handleDismiss: handleDismiss
    };
})();

document.addEventListener('DOMContentLoaded', function () {
    InstallManager.init();
});

if (typeof window !== 'undefined') {
    window.InstallManager = InstallManager;
}
