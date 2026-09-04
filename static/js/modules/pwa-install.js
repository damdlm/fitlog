/**
 * InstallManager — controlador único da experiência de instalação do PWA.
 *
 * Segue o mesmo padrão dos outros módulos (IIFE + objeto exposto em
 * window), ver static/js/modules/csrf.js e exercicio-imagens.js.
 *
 * Responsável por:
 *  - detectar plataforma (iOS / iPadOS / Android / Desktop / Safari / Chromium);
 *  - detectar se o app já está instalado (display-mode / navigator.standalone);
 *  - capturar o evento `beforeinstallprompt` (Android/Desktop) e expor um
 *    botão próprio do FitLog em vez do prompt automático do navegador;
 *  - mostrar um banner + tutorial visual premium no iOS/iPadOS (não suporta
 *    prompt nativo);
 *  - controlar a frequência dos avisos via localStorage (estado estruturado
 *    e versionado);
 *  - alimentar o item fixo "Instalar aplicativo" no menu do usuário;
 *  - confirmar visualmente quando a instalação é concluída.
 *
 * Não depende de bibliotecas externas -- só JS nativo, para não adicionar
 * peso desnecessário só por causa dessa funcionalidade. Todo o código
 * assume que qualquer API pode estar ausente (localStorage em modo
 * privado, matchMedia em navegador antigo etc.) e nunca deixa isso
 * quebrar o uso normal do FitLog -- na dúvida, a funcionalidade de
 * instalação simplesmente não aparece.
 */
const InstallManager = (function () {
    'use strict';

    // Chave única no localStorage. Formato: { installed, dismissedAt, version }
    const STORAGE_KEY = 'fitlog_pwa_install_v1';
    const STATE_VERSION = 1;

    // Depois que o usuário fecha o aviso, quantos dias esperar antes de
    // voltar a sugerir a instalação.
    const DISMISS_COOLDOWN_DAYS = 7;

    // Espera um pouco antes de sugerir a instalação automaticamente, pra
    // não interromper a primeira coisa que o usuário for fazer na página.
    const AUTO_SHOW_DELAY_MS = 4000;

    // Quanto tempo o toast de confirmação ("instalado com sucesso") fica
    // visível antes de sumir sozinho.
    const SUCCESS_TOAST_MS = 3200;

    let deferredPrompt = null;   // evento beforeinstallprompt guardado (Android/Desktop)
    let platform = null;         // resultado de detectPlatform()
    let bannerEl = null;         // banner/CTA (Android/Desktop OU iOS)
    let iosSheetEl = null;       // bottom sheet com o tutorial iOS
    let backdropEl = null;       // fundo escurecido atrás do tutorial iOS
    let toastEl = null;          // toast de confirmação ("instalado com sucesso")
    let menuItemEl = null;       // <li> "Instalar aplicativo" no dropdown
    let headerBtnEl = null;      // botão de instalar no cabeçalho, ao lado do FitBot
    let autoShowTimer = null;
    let toastTimer = null;
    let elementoComFocoAntes = null; // pra devolver o foco ao fechar o modal iOS
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
            // localStorage indisponível (modo privado, quota, navegador
            // antigo) -- segue sem memória entre visitas, não trava nada.
            return {};
        }
    }

    function writeState(patch) {
        try {
            const state = Object.assign(readState(), patch, { version: STATE_VERSION });
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            // Idem -- perde a memória, não quebra a funcionalidade.
        }
    }

    /**
     * Decide se o aviso automático (banner) pode aparecer agora. Não afeta
     * o item do menu, que fica disponível sempre que a instalação for
     * possível. Esse cooldown persiste normalmente entre sessões -- fechar
     * o app, reabrir, reiniciar o aparelho -- porque vive no localStorage,
     * não em variável de memória.
     */
    function shouldShowInstallPrompt() {
        if (isPWAInstalled()) return false;

        const state = readState();
        if (state.installed) return false;

        if (state.dismissedAt) {
            const diasDesdeDispensa = (Date.now() - state.dismissedAt) / (1000 * 60 * 60 * 24);
            if (diasDesdeDispensa < DISMISS_COOLDOWN_DAYS) return false;
        }

        return true;
    }

    // ---------------------------------------------------------------
    // Detecção de ambiente -- funções pequenas e organizadas, cada uma
    // com uma responsabilidade só, pra não duplicar lógica de UA em
    // vários lugares do módulo (nem fora dele).
    // ---------------------------------------------------------------

    function getUserAgent() {
        return (window.navigator && (window.navigator.userAgent || window.navigator.vendor)) || '';
    }

    /** iPhone/iPod, ou iPad "de verdade" (UA ainda antigo, raro hoje). */
    function isIOSPorUserAgent() {
        const ua = getUserAgent();
        return /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    }

    /**
     * iPadOS 13+ se identifica como "MacIntel" no user-agent (modo
     * desktop por padrão do Safari) -- só dá pra distinguir de um Mac de
     * verdade pela presença de tela sensível ao toque.
     */
    function isIPadOS() {
        try {
            return window.navigator.platform === 'MacIntel'
                && typeof window.navigator.maxTouchPoints === 'number'
                && window.navigator.maxTouchPoints > 1;
        } catch (e) {
            return false;
        }
    }

    function isIOS() {
        return isIOSPorUserAgent() || isIPadOS();
    }

    function isAndroid() {
        return /Android/.test(getUserAgent());
    }

    function isMobile() {
        return isIOS() || isAndroid();
    }

    function isDesktop() {
        return !isMobile();
    }

    /**
     * Safari "de verdade": tem "Safari" no UA mas não é Chrome/Chromium/
     * Android (esses navegadores também incluem "Safari" no UA por
     * compatibilidade).
     */
    function isSafariBrowser() {
        const ua = getUserAgent();
        return /Safari/.test(ua) && !/Chrome|Chromium|CriOS|Android|Edg|OPR/.test(ua);
    }

    function isChromiumBrowser() {
        return /Chrome|Chromium|CriOS|Edg|OPR/.test(getUserAgent()) && !isSafariBrowser();
    }

    /**
     * No iOS todo navegador usa o motor do Safari por baixo, mas a barra
     * de ferramentas (e onde fica o botão Compartilhar) muda de nome
     * conforme o app. Retorna o nome certo pra usar no tutorial, ou null
     * se não reconhecer (aí o texto cai num genérico "seu navegador").
     */
    function getIOSBrowserLabel() {
        const ua = getUserAgent();
        if (/CriOS/.test(ua)) return 'Chrome';
        if (/FxiOS/.test(ua)) return 'Firefox';
        if (/EdgiOS/.test(ua)) return 'Edge';
        if (isSafariBrowser()) return 'Safari';
        return null;
    }

    /**
     * Navegadores embutidos dentro de apps (Instagram, Facebook, TikTok,
     * LinkedIn, WhatsApp em alguns casos) usam uma WebView customizada,
     * não o Safari de verdade -- mesmo que o user-agent contenha
     * "Safari" (quase todos incluem, por compatibilidade). Em muitos
     * desses o botão Compartilhar nem existe, ou "Adicionar à Tela de
     * Início" simplesmente não funciona. Mostrar o tutorial normal
     * nesse caso confunde mais do que ajuda -- melhor orientar a pessoa
     * a abrir no Safari primeiro.
     */
    function isInAppBrowser() {
        const ua = getUserAgent();
        return /FBAN|FBAV|Instagram|Line\/|MicroMessenger|TikTok|Twitter|LinkedInApp/i.test(ua);
    }

    /**
     * true se a página já estiver rodando numa janela "standalone" --
     * Android/Desktop via display-mode, iOS via navigator.standalone
     * (API específica da Apple, não padronizada).
     */
    function isStandalone() {
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

    /** Alias semântico -- "instalado" e "standalone" são a mesma coisa
     * aqui, mas o nome comunica melhor a intenção em cada chamada. */
    function isPWAInstalled() {
        return isStandalone();
    }

    /** Mantido por compatibilidade (nome usado antes desta revisão). */
    function isAppInstalled() {
        return isPWAInstalled();
    }

    function detectPlatform() {
        return {
            isIOS: isIOS(),
            isIPadOS: isIPadOS(),
            isAndroid: isAndroid(),
            isDesktop: isDesktop(),
            isSafari: isSafariBrowser(),
            isChromium: isChromiumBrowser()
        };
    }

    // ---------------------------------------------------------------
    // Construção da UI (banner + tutorial iOS + toast de sucesso)
    // Os elementos são criados uma única vez e reaproveitados.
    // ---------------------------------------------------------------

    function garantirBanner() {
        if (bannerEl) return bannerEl;

        const el = document.createElement('div');
        el.id = 'pwaInstallBanner';
        el.className = 'pwa-install-sheet';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.setAttribute('aria-label', 'Instalar aplicativo FitLog');

        if (platform.isIOS) {
            // iOS: banner compacto -- o clique só abre o tutorial completo
            // (não existe prompt nativo aqui, então não faz sentido um
            // cartão grande antes do próprio tutorial).
            el.classList.add('pwa-ios-banner');
            el.innerHTML = `
                <div class="pwa-install-sheet-content">
                    <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                    <div class="pwa-install-text">
                        <strong>📲 Instale o FitLog</strong>
                        <span>Tenha acesso rápido aos seus treinos direto pela tela inicial.</span>
                    </div>
                    <div class="pwa-install-actions">
                        <button type="button" class="btn-pwa-dismiss" aria-label="Agora não">Agora não</button>
                        <button type="button" class="btn-pwa-install">Instalar</button>
                    </div>
                </div>
            `;
        } else {
            // Android/Desktop: esse cartão é a única tela que o FitLog
            // controla antes do navegador assumir com o prompt nativo --
            // por isso ganha o mesmo nível de acabamento do tutorial iOS.
            el.classList.add('pwa-android-sheet');
            el.innerHTML = `
                <div class="pwa-install-sheet-content pwa-android-sheet-content">
                    <button type="button" class="btn-pwa-close" aria-label="Agora não">&times;</button>
                    <div class="pwa-ios-hero">
                        <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                    </div>
                    <strong>Instale o FitLog</strong>
                    <p>Tenha seus treinos sempre à mão, direto da tela inicial -- mais rápido e sem precisar abrir o navegador.</p>
                    <ul class="pwa-android-features">
                        <li><i class="bi bi-graph-up-arrow" aria-hidden="true"></i> Acompanhe sua evolução treino a treino</li>
                        <li><i class="bi bi-calendar-check" aria-hidden="true"></i> Acesso rápido à sua rotina de treinos</li>
                        <li><i class="bi bi-robot" aria-hidden="true"></i> Tire dúvidas com o FitBot na hora</li>
                    </ul>
                    <button type="button" class="btn-pwa-install btn-pwa-entendi">
                        <i class="bi bi-download" aria-hidden="true"></i> Instalar aplicativo
                    </button>
                    <button type="button" class="btn-pwa-dismiss-link">Agora não</button>
                </div>
            `;
        }
        document.body.appendChild(el);

        el.querySelector('.btn-pwa-install').addEventListener('click', handleInstall);

        const botaoDispensar = el.querySelector('.btn-pwa-dismiss, .btn-pwa-dismiss-link');
        if (botaoDispensar) botaoDispensar.addEventListener('click', handleDismiss);

        const botaoFecharAndroid = el.querySelector('.pwa-android-sheet-content .btn-pwa-close');
        if (botaoFecharAndroid) botaoFecharAndroid.addEventListener('click', handleDismiss);

        bannerEl = el;
        return el;
    }

    function garantirTutorialIOS() {
        if (iosSheetEl) return iosSheetEl;

        const el = document.createElement('div');
        el.id = 'pwaIosSheet';
        el.className = 'pwa-install-sheet pwa-ios-sheet';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.setAttribute('aria-label', 'Como instalar o FitLog no iPhone ou iPad');

        if (isInAppBrowser()) {
            // Navegador embutido de app (Instagram, Facebook, TikTok...):
            // o passo a passo do Safari não se aplica, e em muitos casos
            // "Adicionar à Tela de Início" nem funciona por ali. Melhor
            // orientar a abrir no Safari em vez de um tutorial que não
            // vai funcionar.
            el.innerHTML = `
                <div class="pwa-install-sheet-content pwa-ios-sheet-content">
                    <button type="button" class="btn-pwa-close" aria-label="Fechar">&times;</button>

                    <div class="pwa-ios-hero">
                        <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                    </div>

                    <strong>Abra no Safari para instalar</strong>
                    <p>Esse navegador dentro do app não permite instalar o FitLog. Toque em <strong>"⋯"</strong> ou <strong>"Abrir no navegador"</strong> no canto da tela e depois repita a instalação pelo Safari.</p>

                    <button type="button" class="btn-pwa-install btn-pwa-entendi">
                        <i class="bi bi-check2" aria-hidden="true"></i> Entendi
                    </button>
                </div>
            `;
            document.body.appendChild(el);
            el.querySelector('.btn-pwa-close').addEventListener('click', handleDismiss);
            el.querySelector('.btn-pwa-entendi').addEventListener('click', handleDismiss);

            iosSheetEl = el;
            return el;
        }

        const nomeNavegador = getIOSBrowserLabel();
        const legendaCompartilhar = nomeNavegador ? `Na barra do ${nomeNavegador}` : 'No seu navegador';

        el.innerHTML = `
            <div class="pwa-install-sheet-content pwa-ios-sheet-content">
                <button type="button" class="btn-pwa-close" aria-label="Fechar">&times;</button>

                <div class="pwa-ios-hero">
                    <img src="/static/icons/icon-192.png" alt="" class="pwa-install-icon">
                </div>

                <strong>Instale o FitLog</strong>
                <p>Tenha o FitLog sempre à mão, direto da tela inicial do seu iPhone.</p>

                <ol class="pwa-ios-steps">
                    <li>
                        <span class="pwa-step-icon-chip">
                            <i class="bi bi-box-arrow-up" aria-hidden="true"></i>
                        </span>
                        <span class="pwa-step-text">
                            <strong>Toque em Compartilhar</strong>
                            <small>${legendaCompartilhar}</small>
                        </span>
                    </li>
                    <li>
                        <span class="pwa-step-icon-chip pwa-step-icon-chip-circle">
                            <i class="bi bi-chevron-down" aria-hidden="true"></i>
                        </span>
                        <span class="pwa-step-text">
                            <strong>Toque em Ver Mais</strong>
                            <small>Se "Adicionar à Tela de Início" não aparecer direto</small>
                        </span>
                    </li>
                    <li>
                        <span class="pwa-step-icon-chip pwa-step-icon-chip-alt">
                            <i class="bi bi-plus-square" aria-hidden="true"></i>
                        </span>
                        <span class="pwa-step-text">
                            <strong>Adicionar à Tela de Início</strong>
                            <small>E depois toque em Adicionar</small>
                        </span>
                    </li>
                </ol>

                <button type="button" class="btn-pwa-install btn-pwa-entendi">
                    <i class="bi bi-check2" aria-hidden="true"></i> Entendi
                </button>
            </div>
        `;
        document.body.appendChild(el);

        el.querySelector('.btn-pwa-close').addEventListener('click', handleDismiss);
        el.querySelector('.btn-pwa-entendi').addEventListener('click', handleDismiss);

        iosSheetEl = el;
        return el;
    }

    function garantirBackdrop() {
        if (backdropEl) return backdropEl;

        const el = document.createElement('div');
        el.id = 'pwaBackdrop';
        el.className = 'pwa-backdrop';
        el.addEventListener('click', handleDismiss);
        document.body.appendChild(el);

        backdropEl = el;
        return el;
    }

    function garantirToast() {
        if (toastEl) return toastEl;

        const el = document.createElement('div');
        el.id = 'pwaSuccessToast';
        el.className = 'pwa-toast';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.innerHTML = '<i class="bi bi-check-circle-fill" aria-hidden="true"></i> FitLog instalado com sucesso!';
        document.body.appendChild(el);

        toastEl = el;
        return el;
    }

    function showInstallButton() {
        garantirBanner().classList.add('is-visible');

        // Guarda o foco original assim que QUALQUER banner aparece (iOS
        // ou Android/Desktop) -- é o ponto certo pra restaurar depois,
        // mesmo que o fluxo iOS ainda passe por um segundo passo (o
        // tutorial completo). Só captura se ainda não tiver nada
        // guardado, pra não sobrescrever com um elemento nosso que está
        // prestes a sumir (ver showIOSInstructions).
        if (!elementoComFocoAntes) elementoComFocoAntes = document.activeElement;

        // O cartão do Android/Desktop é uma "tela" completa (com backdrop
        // e role="dialog"), então merece o mesmo cuidado de foco/Esc do
        // tutorial iOS. O banner compacto do iOS não trava foco nem some
        // com Esc -- ele só existe pra abrir o tutorial de verdade, que
        // faz sua própria captura logo abaixo.
        if (!platform.isIOS) {
            garantirBackdrop().classList.add('is-visible');
            document.addEventListener('keydown', handleEscapeOverlay);

            const botaoFechar = bannerEl.querySelector('.btn-pwa-close');
            if (botaoFechar) botaoFechar.focus();
        }
    }

    function hideInstallButton() {
        if (bannerEl) bannerEl.classList.remove('is-visible');
        if (!platform.isIOS && backdropEl && !(iosSheetEl && iosSheetEl.classList.contains('is-visible'))) {
            backdropEl.classList.remove('is-visible');
            document.removeEventListener('keydown', handleEscapeOverlay);
            if (elementoComFocoAntes && typeof elementoComFocoAntes.focus === 'function') {
                elementoComFocoAntes.focus();
            }
            elementoComFocoAntes = null;
        }
    }

    function showIOSInstructions() {
        hideInstallButton();
        // Só captura o foco aqui se ainda não foi capturado -- se a
        // pessoa chegou até aqui clicando no banner compacto do iOS, o
        // botão "Instalar" do banner está prestes a sumir da tela, então
        // não faz sentido guardar ELE como "pra onde devolver o foco"
        // depois. Nesse caso o foco original já foi salvo antes, quando
        // o banner apareceu (ver início de showInstallButton/init). Só
        // quando o tutorial é aberto direto (menu ou botão do cabeçalho,
        // sem passar pelo banner) é que capturamos aqui.
        if (!elementoComFocoAntes) elementoComFocoAntes = document.activeElement;

        garantirBackdrop().classList.add('is-visible');

        const sheet = garantirTutorialIOS();
        sheet.classList.add('is-visible');

        document.addEventListener('keydown', handleEscapeOverlay);

        // Foco no botão de fechar -- acessibilidade básica de modal
        // (teclado no desktop Safari/Chrome também funciona assim).
        const botaoFechar = sheet.querySelector('.btn-pwa-close');
        if (botaoFechar) botaoFechar.focus();
    }

    function hideIOSInstructions() {
        if (backdropEl) backdropEl.classList.remove('is-visible');
        if (!iosSheetEl) return;
        iosSheetEl.classList.remove('is-visible');
        document.removeEventListener('keydown', handleEscapeOverlay);

        if (elementoComFocoAntes && typeof elementoComFocoAntes.focus === 'function') {
            elementoComFocoAntes.focus();
        }
        elementoComFocoAntes = null;
    }

    /** Fecha qualquer uma das telas de instalação (iOS ou Android/Desktop)
     * que estiver aberta no momento -- Esc funciona igual nas duas. */
    function handleEscapeOverlay(evento) {
        if (evento.key === 'Escape') handleDismiss();
    }

    function showSuccessToast() {
        const toast = garantirToast();
        toast.classList.add('is-visible');

        if (toastTimer) window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            toast.classList.remove('is-visible');
        }, SUCCESS_TOAST_MS);
    }

    // ---------------------------------------------------------------
    // Item fixo no menu ("Instalar aplicativo")
    // ---------------------------------------------------------------

    function atualizarVisibilidadeMenu() {
        const disponivel = !isPWAInstalled() && (!!deferredPrompt || platform.isIOS);
        if (menuItemEl) menuItemEl.style.display = disponivel ? '' : 'none';
        if (headerBtnEl) headerBtnEl.style.display = disponivel ? '' : 'none';
        if (document.body) document.body.classList.toggle('pwa-header-icon-active', disponivel);
    }

    function ligarMenuItem() {
        menuItemEl = document.getElementById('pwaMenuInstallItem');
        if (menuItemEl) {
            const link = menuItemEl.querySelector('a, button');
            if (link) {
                link.addEventListener('click', function (e) {
                    e.preventDefault();
                    handleInstall();
                });
            }
        }

        headerBtnEl = document.getElementById('pwaHeaderInstallBtn');
        if (headerBtnEl) {
            headerBtnEl.addEventListener('click', function (e) {
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

            // Tanto iOS quanto Android/Desktop começam pelo banner leve --
            // no iOS o clique em "Instalar" abre o tutorial; no
            // Android/Desktop, o prompt nativo do navegador.
            if (platform.isIOS || deferredPrompt) {
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

    /**
     * IMPORTANTE -- limitação conhecida do iOS, não é um bug daqui: o
     * evento `appinstalled` só existe em navegadores Chromium (Android/
     * Desktop). O Safari NUNCA dispara esse evento quando alguém conclui
     * "Adicionar à Tela de Início" -- então o toast de sucesso abaixo só
     * aparece pra quem instala pelo Android ou Desktop. No iOS, o
     * `localStorage` só é marcado como `installed:true` na PRÓXIMA vez
     * que a pessoa abrir o app pelo ícone da tela inicial (ver `init()`),
     * não no momento em que ela toca "Adicionar". Não existe API pública
     * da Apple pra saber isso na hora -- é intencional da plataforma.
     */
    function handleAppInstalled() {
        writeState({ installed: true, dismissedAt: null });
        deferredPrompt = null;
        hideInstallButton();
        hideIOSInstructions();
        atualizarVisibilidadeMenu();
        showSuccessToast();
    }

    // ---------------------------------------------------------------
    // Inicialização
    // ---------------------------------------------------------------

    function init() {
        if (initialized) return;
        initialized = true;

        platform = detectPlatform();

        if (isPWAInstalled()) {
            // Já é PWA instalado: não há nada a oferecer, só garante que o
            // estado fique consistente para a próxima checagem. Isso
            // continua valendo depois de fechar/reabrir o app ou
            // reiniciar o aparelho, porque a checagem em si (isStandalone)
            // não depende do localStorage -- só olha como a página está
            // rodando agora.
            writeState({ installed: true });
            return;
        }

        if ('addEventListener' in window) {
            window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
            window.addEventListener('appinstalled', handleAppInstalled);
        }

        ligarMenuItem();

        // No iOS não existe beforeinstallprompt -- se ainda não foi
        // instalado nem dispensado recentemente, agenda o banner.
        if (platform.isIOS) {
            agendarExibicaoAutomatica();
        }

        atualizarVisibilidadeMenu();
    }

    // API pública
    return {
        init: init,
        // Detecção (nomes organizados, sem duplicar lógica em quem chama)
        isIOS: isIOS,
        isIPadOS: isIPadOS,
        isAndroid: isAndroid,
        isMobile: isMobile,
        isDesktop: isDesktop,
        isSafari: isSafariBrowser,
        isChromium: isChromiumBrowser,
        getIOSBrowserLabel: getIOSBrowserLabel,
        isStandalone: isStandalone,
        isPWAInstalled: isPWAInstalled,
        isAppInstalled: isAppInstalled, // alias, compatibilidade
        detectPlatform: detectPlatform,
        // Estado / ações
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