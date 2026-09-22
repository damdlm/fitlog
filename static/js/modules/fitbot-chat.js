/* ============================================================
   FitBot · Assistente virtual de treino (chat com IA)
   ============================================================
   - Máquina de estados do robô: idle (com um vídeo de humor sorteado)
     -> thinking (aguardando IA) -> talking ou error -> idle de novo ->
     bye (ao abrir ou fechar o modal). Cada estado mostra um <video>
     diferente dentro de .fitbot-avatar-frame (ver fitbot-chat.css).
   - Antes de enviar uma foto, ela é redimensionada no navegador para
     no máximo 800x800px (canvas) e comprimida em JPEG, economizando
     a cota gratuita da API de visão (Gemini).
   - O histórico da conversa fica só em memória (não é salvo no
     servidor) e é reenviado truncado a cada mensagem para dar
     contexto ao modelo.
   ============================================================ */
(function () {
    'use strict';

    var MAX_DIMENSAO_IMAGEM = 800;
    var QUALIDADE_JPEG = 0.8;
    var MAX_HISTORICO = 10;
    var DURACAO_ESTADO_TALKING_MS = 2500;
    var DURACAO_ESTADO_ERROR_MS = 3000;
    var DURACAO_ESTADO_BYE_MS = 1200; // usado ao FECHAR o chat (despedirEFechar)

    // Vídeos "de humor" do FitBot — sem significado fixo, só para
    // deixar a espera mais divertida. Um é sorteado toda vez que o
    // robô volta para o estado parado (idle).
    var VIDEOS_POOL_IDLE = [

        'Agachamento.mp4', 'agua.mp4', 'alo.mp4', 'arremesso.mp4', 'beijo.mp4',
        'bracos.mp4', 'celular.mp4', 'dancando.mp4', 'dancando2.mp4', 'duvida.mp4',
        'fortao.mp4', 'mao.mp4', 'pensando.mp4', 'prancheta.mp4', 'pulso.mp4', 
        'saudacao.mp4', 'stiff.mp4', 'tchau.mp4',
    ];
    // "padrao.mp4" não entra no sorteio -- ele é intercalado manualmente
    // entre os aleatórios (ver escolherProximoVideoIdle): aleatório,
    // padrão, aleatório, padrão... sempre alternando.
    var VIDEO_PADRAO_IDLE = 'padrao.mp4';
    var PASTA_VIDEOS = '/static/videos/fitbot/';
    // Duração do esmaecimento entre um vídeo e outro (crossfade simultâneo:
    // o antigo esmaece enquanto o novo já vai aparecendo). Precisa bater
    // com o CSS (.fitbot-avatar-frame video).
    var CROSSFADE_DURACAO_MS = 300;

    // Saudações iniciais do FitBot -- uma é sorteada e mostrada só na
    // primeira vez que o chat é aberto (ver onModalShown / primeiraVez).
    var SAUDACOES_INICIAIS = [
        '🤖 Olá! Eu sou o FitBot, seu parceiro de treino.\n\n' +
        'Prometo uma coisa: nunca vou dizer "só mais uma" quando ainda faltarem cinco. 😅\n\n' +
        'Posso explicar exercícios, sugerir treinos, identificar equipamentos por foto e tirar suas dúvidas para você treinar com mais segurança.\n\n' +
        'Então... qual vai ser o desafio de hoje? 💪',

        '👋 Olá! Eu sou o FitBot.\n\n' +
        'Não substituo seu personal... mas também não fico olhando o celular entre uma série e outra. 😏\n\n' +
        'Pergunte sobre exercícios, técnicas, treinos ou envie uma foto de um equipamento da academia.',

        '🤖 Bem-vindo! Eu sou o FitBot.\n\n' +
        'Pode perguntar qualquer coisa sobre treino. Só não me peça para fazer burpees... 😂\n\n' +
        'Também posso analisar fotos de equipamentos e explicar como utilizá-los.',

        '💪 Oi! Eu sou o FitBot.\n\n' +
        'Seu treino pode até falhar... eu não. 😎\n\n' +
        'Estou pronto para responder dúvidas, explicar exercícios e mostrar como usar os equipamentos da academia.',

        '🤖 E aí! Eu sou o FitBot.\n\n' +
        'Prometo que não vou pedir 100 flexões como aquecimento. 😅\n\n' +
        'Posso ajudar com exercícios, treinos, equipamentos da academia e até analisar uma foto para explicar como usar um aparelho.\n\n' +
        'Bora treinar? 💪',

        '🏋️ Olá! Eu sou o FitBot, seu personal trainer virtual com inteligência artificial.\n\n' +
        'Posso explicar a execução correta dos exercícios, sugerir treinos, esclarecer dúvidas sobre musculação e cardio, além de identificar equipamentos por foto e mostrar como utilizá-los com segurança.\n\n' +
        'Como posso ajudar você hoje?',

        '🤖 Bem-vindo! Eu sou o FitBot.\n\n' +
        'Estou aqui para deixar seus treinos mais fáceis e eficientes.\n\n' +
        'Pergunte sobre qualquer exercício, peça sugestões de treino, tire dúvidas ou envie uma foto de um equipamento da academia para que eu explique como usá-lo.',

        '👋 Olá! Eu sou o FitBot, seu assistente no FitLog.\n\n' +
        '💪 Posso ajudar com:\n' +
        '• Exercícios e execução correta\n' +
        '• Treinos de musculação e cardio\n' +
        '• Dúvidas sobre equipamentos da academia\n' +
        '• Dicas para melhorar seus resultados\n\n' +
        '📸 Você também pode enviar uma foto de um equipamento ou exercício que eu explico como utilizá-lo.',

        'Oi! Eu sou o FitBot 🤖\n' +
        'Seu personal trainer virtual aqui no FitLog.\n' +
        'Pode me perguntar sobre musculação, aeróbico, execução de exercícios ' +
        'ou me mandar uma foto de um equipamento que eu explico como usar.'
    ];

    function sortearSaudacaoInicial() {
        var indice = Math.floor(Math.random() * SAUDACOES_INICIAIS.length);
        return SAUDACOES_INICIAIS[indice];
    }

    var elWidget, elModal, elMessages, elForm, elTextarea, elSendBtn,
        elImageInput, elImageBtn, elImagePreview, elImagePreviewThumb,
        elImageRemoveBtn, elTyping, elIdleVideoA, elIdleVideoB, elCloseBtn;

    // elIdleAtivo é o buffer visível agora; elIdleInativo é onde o
    // próximo vídeo é pré-carregado antes do crossfade (double buffer).
    var elIdleAtivo = null;
    var elIdleInativo = null;
    var ultimoVideoAleatorioIdle = null;
    var proximoIdleEhPadrao = false;
    var idleRotationTimeoutId = null;
    var idleBufferPreparado = null; // buffer (A ou B) já carregado/decodificado, pronto pra ativar sem espera de rede
    var idleBufferEmCarregamento = null; // buffer que está no meio de um load() ainda sem loadedmetadata (evita 2 loads concorrentes no mesmo buffer)
    var idleAoTerminarCarregamento = null; // callback de quem pediu o vídeo idle enquanto um load já estava em andamento (ver sortearVideoIdle)
    var DURACAO_ROTACAO_IDLE_FALLBACK_MS = 6000; // usado só se não der pra ler a duração do vídeo

    var historico = [];               // [{papel: 'usuario'|'bot', texto: '...'}]
    var imagemSelecionadaDataUrl = null; // dataURL completo (para preview)
    var estadoTimeoutId = null;
    var conversaIniciada = false;

    // Consentimento LGPD (FitBot manda dados a IA de terceiros -- Groq/
    // Gemini). Guarda a última mensagem que ficou pendente de aceite,
    // pra poder reenviá-la assim que o usuário confirmar.
    var mensagemPendenteConsentimento = null;

    function byId(id) {
        return document.getElementById(id);
    }

    function init() {
        elWidget = byId('fitbotWidget');
        elModal = byId('fitbotModal');
        if (!elWidget || !elModal) return; // página sem o FitBot

        elMessages = byId('fitbotMessages');
        elForm = byId('fitbotForm');
        elTextarea = byId('fitbotTextarea');
        elSendBtn = byId('fitbotSendBtn');
        elImageInput = byId('fitbotImageInput');
        elImageBtn = byId('fitbotImageBtn');
        elImagePreview = byId('fitbotImagePreview');
        elImagePreviewThumb = byId('fitbotImagePreviewThumb');
        elImageRemoveBtn = byId('fitbotImageRemoveBtn');
        elTyping = byId('fitbotTyping');
        elIdleVideoA = byId('fitbotIdleVideoA');
        elIdleVideoB = byId('fitbotIdleVideoB');
        elIdleAtivo = elIdleVideoA;
        elIdleInativo = elIdleVideoB;
        elCloseBtn = elModal.querySelector('[data-bs-dismiss="modal"]');

        setState('idle');

        elModal.addEventListener('show.bs.modal', onModalShown);

        if (elCloseBtn) {
            elCloseBtn.addEventListener('click', function (evt) {
                evt.preventDefault();
                evt.stopPropagation();
                despedirEFechar();
            });
        }

        elForm.addEventListener('submit', onSubmit);

        elTextarea.addEventListener('keydown', function (evt) {
            if (evt.key === 'Enter' && !evt.shiftKey) {
                evt.preventDefault();
                elForm.requestSubmit ? elForm.requestSubmit() : onSubmit(evt);
            }
        });

        elImageBtn.addEventListener('click', function () {
            elImageInput.click();
        });

        elImageInput.addEventListener('change', onImageSelected);
        elImageRemoveBtn.addEventListener('click', limparImagemSelecionada);
    }

    function onModalShown() {
        var primeiraVez = !conversaIniciada;
        conversaIniciada = true;

        // Abre direto no idle (rotação normal de vídeos), sem forçar
        // nenhum vídeo específico de abertura.
        setState('idle');
        if (primeiraVez) {
            adicionarMensagem('bot', sortearSaudacaoInicial());
        }
    }

    function despedirEFechar() {
        setState('bye', function aoFicarVisivel() {
            setTimeout(function () {
                var instancia = bootstrap.Modal.getOrCreateInstance(elModal);
                instancia.hide();
                setState('idle');
            }, DURACAO_ESTADO_BYE_MS);
        });
    }

    /* ------------------------------------------------------------
       Máquina de estados do robô
       ------------------------------------------------------------ */
    // aoFicarVisivel (opcional): chamado quando o vídeo do novo estado
    // realmente terminou de aparecer (não antes) -- ver ativarVideoComPreload.
    // Só se aplica a estados de vídeo único (bye/talking/error/thinking);
    // pro 'idle' (dois buffers, crossfade próprio) não é usado.
    function setState(novoEstado, aoFicarVisivel) {
        if (estadoTimeoutId) {
            clearTimeout(estadoTimeoutId);
            estadoTimeoutId = null;
        }
        elWidget.classList.remove('is-idle', 'is-thinking', 'is-talking', 'is-error', 'is-bye');
        elWidget.classList.add('is-' + novoEstado);

        pararRotacaoIdle(); // se estava girando os vídeos de idle, para -- reagenda de novo se o novo estado for idle

        if (novoEstado === 'thinking' && elTyping) {
            elMessages.appendChild(elTyping); // mantém o "digitando..." sempre por último
            elMessages.scrollTop = elMessages.scrollHeight;
        }

        if (novoEstado === 'talking') {
            estadoTimeoutId = setTimeout(function () { setState('idle'); }, DURACAO_ESTADO_TALKING_MS);
        } else if (novoEstado === 'error') {
            estadoTimeoutId = setTimeout(function () { setState('idle'); }, DURACAO_ESTADO_ERROR_MS);
        }

        if (novoEstado === 'idle') {
            sortearVideoIdle();
        }

        trocarVideoAtivo(novoEstado, aoFicarVisivel);
    }

    function trocarVideoAtivo(estado, aoFicarVisivel) {
        var videos = elWidget.querySelectorAll('.fitbot-avatar-frame video');
        var videoAlvo = null;

        for (var i = 0; i < videos.length; i++) {
            var video = videos[i];
            var ehDoEstadoAtual = video.getAttribute('data-state') === estado;

            if (estado === 'idle' && ehDoEstadoAtual) {
                // Os dois buffers de idle são geridos por sortearVideoIdle
                // (play/pause/crossfade) -- não mexe neles aqui.
                continue;
            }

            if (!ehDoEstadoAtual) {
                if (video.classList.contains('is-active')) {
                    video.classList.remove('is-active');
                    // Só pausa depois que o fade (CROSSFADE_DURACAO_MS) terminar --
                    // pausar na hora congela o quadro no meio da transição visível
                    // e ainda deixa o vídeo "frio" (precisando decodificar de novo)
                    // na próxima vez que ele for reativado, o que causava o
                    // intervalo/piscada entre um vídeo e outro.
                    (function (v) {
                        setTimeout(function () {
                            if (!v.classList.contains('is-active')) v.pause();
                        }, CROSSFADE_DURACAO_MS);
                    })(video);
                }
                continue;
            }

            videoAlvo = video;
        }

        if (!videoAlvo) return;

        // Crossfade simultâneo: o vídeo que estava ativo já começou a
        // esmaecer (acima) enquanto este já é ativado aqui -- os dois
        // ficam com opacidade > 0 ao mesmo tempo durante CROSSFADE_DURACAO_MS.
        ativarVideoComPreload(videoAlvo, aoFicarVisivel);
    }

    // Ativa um vídeo de estado (bye/talking/error/thinking) só depois que
    // o frame no início dele já está decodificado -- evita o flash/pulo
    // que acontecia quando o vídeo estava pausado numa posição antiga
    // (ex.: "tchau.mp4" da última vez que o chat foi aberto) e a gente
    // tentava mostrar ele já em fade antes do navegador ter o frame pronto.
    // aoAtivar (opcional): chamado assim que a classe is-active é aplicada
    // (o vídeo começou a de fato aparecer) -- é o que permite a quem chamou
    // contar o "tempo em tela" a partir da aparição real, não da intenção.
    function ativarVideoComPreload(video, aoAtivar) {
        if (video.classList.contains('is-active')) {
            if (aoAtivar) aoAtivar();
            return;
        }

        function tocarEEsmaecer() {
            var promessa = video.play();
            function esmaecer() {
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () {
                        video.classList.add('is-active');
                        if (aoAtivar) aoAtivar();
                    });
                });
            }
            if (promessa && promessa.then) {
                promessa.then(esmaecer).catch(esmaecer);
            } else {
                esmaecer();
            }
        }

        // Já está exatamente no frame 0 e com dado suficiente decodificado?
        // Pode tocar direto, sem esperar por "seeked".
        if (video.currentTime === 0 && video.readyState >= 2) {
            tocarEEsmaecer();
            return;
        }

        video.addEventListener('seeked', function aoBuscarFrame() {
            video.removeEventListener('seeked', aoBuscarFrame);
            tocarEEsmaecer();
        });
        video.currentTime = 0;
    }

    // Escolhe o próximo vídeo do estado idle, sempre alternando entre um
    // aleatório do pool e o "padrao.mp4" -- ou seja, o padrão sempre roda
    // entre dois vídeos aleatórios, nunca dois aleatórios seguidos.
    function escolherProximoVideoIdle() {
        if (proximoIdleEhPadrao) {
            proximoIdleEhPadrao = false;
            return VIDEO_PADRAO_IDLE;
        }

        proximoIdleEhPadrao = true;
        var opcoes = VIDEOS_POOL_IDLE;
        if (opcoes.length > 1 && ultimoVideoAleatorioIdle) {
            opcoes = opcoes.filter(function (nome) { return nome !== ultimoVideoAleatorioIdle; });
        }
        var escolhido = opcoes[Math.floor(Math.random() * opcoes.length)];
        ultimoVideoAleatorioIdle = escolhido;
        return escolhido;
    }

    // Crossfade simultâneo entre os dois buffers de idle: o novo aparece
    // enquanto o antigo ainda está esmaecendo (opacidade > 0 nos dois por
    // CROSSFADE_DURACAO_MS).
    function iniciarCrossfadeIdle(bufferNovo) {
        var bufferAnterior = elIdleAtivo;
        var bufferAnteriorEstavaAtivo = !!(bufferAnterior && bufferAnterior !== bufferNovo && bufferAnterior.classList.contains('is-active'));

        elIdleAtivo = bufferNovo;
        elIdleInativo = bufferAnterior;

        if (bufferAnteriorEstavaAtivo) {
            bufferAnterior.classList.remove('is-active');
            setTimeout(function () {
                if (bufferAnterior !== elIdleAtivo) {
                    bufferAnterior.pause();
                }
            }, CROSSFADE_DURACAO_MS);
        }

        bufferNovo.classList.add('is-active');
    }

    // Carrega um vídeo idle num buffer específico e decodifica o primeiro
    // frame, SEM ativar/crossfade ainda. Único caminho de carregamento de
    // vídeo idle (usado tanto pelo preload inicial da página em init()
    // quanto pela troca normal ao entrar em idle -- sortearVideoIdle) --
    // o guard de idleBufferEmCarregamento abaixo evita dois carregamentos
    // concorrentes no MESMO buffer, o que acontecia se o chat fosse
    // aberto (e sortearVideoIdle chamado de novo) antes do preload
    // inicial da página terminar de carregar (comum em conexão lenta).
    function carregarVideoIdleNoBuffer(bufferAlvo, aoPronto) {
        if (idleBufferPreparado === bufferAlvo) {
            if (aoPronto) aoPronto();
            return;
        }
        if (idleBufferEmCarregamento === bufferAlvo) return; // já tem um load() em andamento pra esse buffer -- não duplica

        idleBufferEmCarregamento = bufferAlvo;
        var proximoNome = escolherProximoVideoIdle();
        bufferAlvo.src = PASTA_VIDEOS + proximoNome;
        bufferAlvo.load();

        // Assim que os metadados chegarem, dá play no buffer invisível
        // para decodificar o primeiro frame -- assim quando começarmos o
        // crossfade o browser já tem frame pra mostrar (sem isso, o fade
        // acontece sobre um quadro preto/parado, que é outra forma de
        // "piscar").
        bufferAlvo.addEventListener('loadedmetadata', function aoCarregar() {
            bufferAlvo.removeEventListener('loadedmetadata', aoCarregar);
            if (idleBufferEmCarregamento === bufferAlvo) idleBufferEmCarregamento = null;

            var promessaPreload = bufferAlvo.play();
            function marcarPronto() {
                idleBufferPreparado = bufferAlvo;
                // Só um dos dois interessados é avisado -- os dois fariam
                // exatamente a mesma coisa (ativar esse mesmo buffer), e
                // como cada "ativarAgora" só aplica a classe depois de 2
                // requestAnimationFrame, chamar os dois deixava as duas
                // agendadas sem que uma visse o resultado da outra a
                // tempo, duplicando a ativação. Prioriza quem pediu por
                // último (idleAoTerminarCarregamento), por ser o pedido
                // mais recente/relevante.
                if (idleAoTerminarCarregamento) {
                    var cb = idleAoTerminarCarregamento;
                    idleAoTerminarCarregamento = null;
                    cb();
                } else if (aoPronto) {
                    aoPronto();
                }
            }
            if (promessaPreload && promessaPreload.then) {
                promessaPreload.then(marcarPronto).catch(marcarPronto);
            } else {
                marcarPronto();
            }
        });
    }

    function sortearVideoIdle() {
        if (!elIdleInativo) return;

        var bufferAlvo = elIdleInativo;

        function ativarAgora() {
            // Idempotente: se esse buffer já é o idle ativo agora, não há
            // nada a fazer (pode acontecer se dois pedidos pelo mesmo
            // vídeo terminarem de carregar quase juntos -- ex.: o preload
            // inicial de init() e uma chamada de sortearVideoIdle logo
            // depois, ambos esperando o mesmo buffer).
            if (elIdleAtivo === bufferAlvo && bufferAlvo.classList.contains('is-active')) {
                return;
            }

            idleBufferPreparado = null;

            // Se o estado do robô mudou enquanto esse vídeo carregava (ex.:
            // usuário já fechou o chat, ou já entrou em "thinking"/"bye"
            // antes do load terminar -- comum em conexão lenta), NÃO ativa
            // por cima do que está na tela agora. Só marca como pronto:
            // na próxima vez que o idle realmente entrar de verdade, o
            // fast-path abaixo (idleBufferPreparado === bufferAlvo) usa
            // esse mesmo vídeo já carregado, sem gastar rede de novo.
            if (!elWidget.classList.contains('is-idle')) {
                idleBufferPreparado = bufferAlvo;
                return;
            }

            // Consome o vídeo pré-carregado: se ele ainda for o buffer
            // "escondido" atual, ativa com crossfade. Aguarda dois frames
            // pintados antes do fade, garantindo que o primeiro frame já
            // está decodificado e visível assim que a opacidade começar
            // a subir.
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    iniciarCrossfadeIdle(bufferAlvo);
                });
            });
            agendarProximaRotacaoIdle();
        }

        if (idleBufferPreparado === bufferAlvo) {
            ativarAgora();
            return;
        }

        if (idleBufferEmCarregamento === bufferAlvo) {
            // Já tem um load em andamento pra esse buffer (ex.: o preload
            // inicial de init() ainda rodando) -- espera ele terminar em
            // vez de disparar um load() concorrente por cima (era essa
            // disputa que corrompia o carregamento e travava a troca).
            idleAoTerminarCarregamento = ativarAgora;
            return;
        }

        carregarVideoIdleNoBuffer(bufferAlvo, ativarAgora);
    }

    function agendarProximaRotacaoIdle() {
        pararRotacaoIdle();
        var duracaoMs = (elIdleAtivo && elIdleAtivo.duration && isFinite(elIdleAtivo.duration) && elIdleAtivo.duration > 0)
            ? elIdleAtivo.duration * 1000
            : DURACAO_ROTACAO_IDLE_FALLBACK_MS;

        // Antecipa a troca em CROSSFADE_DURACAO_MS para que o crossfade
        // termine bem no fim do loop do vídeo atual, sem cortar ele no meio.
        var duracaoComMargem = Math.max(duracaoMs - CROSSFADE_DURACAO_MS, 500);

        idleRotationTimeoutId = setTimeout(function () {
            // só troca se ainda estiver parado -- se o usuário mandou uma
            // mensagem nesse meio tempo, setState já limpou esse timer
            if (elWidget.classList.contains('is-idle')) {
                sortearVideoIdle();
            }
        }, duracaoComMargem);
    }

    function pararRotacaoIdle() {
        if (idleRotationTimeoutId) {
            clearTimeout(idleRotationTimeoutId);
            idleRotationTimeoutId = null;
        }
    }

    /* ------------------------------------------------------------
       Mensagens na tela
       ------------------------------------------------------------ */
    function adicionarMensagem(papel, texto, imagemDataUrl) {
        var bolha = document.createElement('div');
        bolha.className = 'fitbot-msg from-' + papel;
        bolha.textContent = texto;

        if (imagemDataUrl) {
            var img = document.createElement('img');
            img.src = imagemDataUrl;
            img.alt = 'Foto enviada';
            img.className = 'fitbot-msg-thumb';
            bolha.appendChild(img);
        }

        elMessages.appendChild(bolha);
        elMessages.scrollTop = elMessages.scrollHeight;
    }

    /* ------------------------------------------------------------
       Envio de mensagem
       ------------------------------------------------------------ */
    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function onSubmit(evt) {
        evt.preventDefault();

        var texto = elTextarea.value.trim();
        var imagem = imagemSelecionadaDataUrl;

        if (!texto && !imagem) return;
        if (elWidget.classList.contains('is-thinking')) return; // já tem uma pergunta em andamento

        adicionarMensagem('user', texto || '(foto enviada)', imagem);

        historico.push({ papel: 'usuario', texto: texto || '(usuário enviou uma foto de um equipamento)' });
        historico = historico.slice(-MAX_HISTORICO);

        var imagemBase64 = imagem ? imagem.split(',')[1] : null;

        elTextarea.value = '';
        limparImagemSelecionada();

        enviarAoServidor(texto, imagemBase64);
    }

    function enviarAoServidor(texto, imagemBase64) {
        setState('thinking');

        fetch('/fitbot/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mensagem: texto,
                imagem_base64: imagemBase64,
                historico: historico,
            }),
        })
            .then(function (resp) {
                return resp.json().then(function (dados) {
                    return { status: resp.status, dados: dados };
                });
            })
            .then(function (resultado) {
                var dados = resultado.dados || {};

                if (dados.consentimento_necessario) {
                    mensagemPendenteConsentimento = { texto: texto, imagemBase64: imagemBase64 };
                    setState('idle');
                    perguntarConsentimentoFitbot(dados.resposta);
                    return;
                }

                if (dados.ok) {
                    adicionarMensagem('bot', dados.resposta);
                    historico.push({ papel: 'bot', texto: dados.resposta });
                    historico = historico.slice(-MAX_HISTORICO);
                    setState('talking');
                } else {
                    adicionarMensagem('error', dados.resposta || 'Não consegui responder agora.');
                    setState('error');
                }
            })
            .catch(function () {
                adicionarMensagem('error', 'Não consegui falar com o FitBot. Verifica sua conexão.');
                setState('error');
            });
    }

    /* ------------------------------------------------------------
       Consentimento LGPD (uso de IA de terceiros pelo FitBot)
       ------------------------------------------------------------ */
    function perguntarConsentimentoFitbot(texto) {
        var bolha = document.createElement('div');
        bolha.className = 'fitbot-msg from-bot';
        bolha.textContent = texto;

        var botoes = document.createElement('div');
        botoes.className = 'mt-2 d-flex gap-2';

        var btnAceitar = document.createElement('button');
        btnAceitar.type = 'button';
        btnAceitar.className = 'btn btn-sm';
        btnAceitar.style.background = 'linear-gradient(135deg, #F28C33 0%, #FFB366 100%)';
        btnAceitar.style.color = '#fff';
        btnAceitar.textContent = 'Concordo, continuar';

        var btnRecusar = document.createElement('button');
        btnRecusar.type = 'button';
        btnRecusar.className = 'btn btn-sm btn-outline-secondary';
        btnRecusar.textContent = 'Agora não';

        btnAceitar.addEventListener('click', function () {
            botoes.remove();
            responderConsentimentoFitbot(true);
        });
        btnRecusar.addEventListener('click', function () {
            botoes.remove();
            responderConsentimentoFitbot(false);
        });

        botoes.appendChild(btnAceitar);
        botoes.appendChild(btnRecusar);
        bolha.appendChild(botoes);

        elMessages.appendChild(bolha);
        elMessages.scrollTop = elMessages.scrollHeight;
    }

    function responderConsentimentoFitbot(concedido) {
        fetch('/privacidade/fitbot-consentimento', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ concedido: concedido }),
        })
            .then(function () {
                if (concedido && mensagemPendenteConsentimento) {
                    var pendente = mensagemPendenteConsentimento;
                    mensagemPendenteConsentimento = null;
                    enviarAoServidor(pendente.texto, pendente.imagemBase64);
                } else {
                    mensagemPendenteConsentimento = null;
                    adicionarMensagem('bot', 'Tudo bem, sem problemas. Se mudar de ideia, é só perguntar de novo.');
                }
            })
            .catch(function () {
                adicionarMensagem('error', 'Não consegui salvar sua resposta agora. Tente de novo.');
                setState('error');
            });
    }

    /* ------------------------------------------------------------
       Captura + compressão de imagem (canvas, máx. 800x800)
       ------------------------------------------------------------ */
    function onImageSelected(evt) {
        var arquivo = evt.target.files && evt.target.files[0];
        elImageInput.value = ''; // permite selecionar o mesmo arquivo de novo depois
        if (!arquivo) return;

        comprimirImagem(arquivo)
            .then(function (dataUrl) {
                imagemSelecionadaDataUrl = dataUrl;
                elImagePreviewThumb.src = dataUrl;
                elImagePreview.classList.add('is-visible');
            })
            .catch(function () {
                adicionarMensagem('error', 'Não consegui processar essa imagem. Tenta outra foto.');
            });
    }

    function limparImagemSelecionada() {
        imagemSelecionadaDataUrl = null;
        elImagePreviewThumb.src = '';
        elImagePreview.classList.remove('is-visible');
    }

    function comprimirImagem(arquivo) {
        return new Promise(function (resolve, reject) {
            var leitor = new FileReader();
            leitor.onerror = reject;
            leitor.onload = function () {
                var img = new Image();
                img.onerror = reject;
                img.onload = function () {
                    var largura = img.width;
                    var altura = img.height;

                    if (largura > MAX_DIMENSAO_IMAGEM || altura > MAX_DIMENSAO_IMAGEM) {
                        var escala = Math.min(
                            MAX_DIMENSAO_IMAGEM / largura,
                            MAX_DIMENSAO_IMAGEM / altura
                        );
                        largura = Math.round(largura * escala);
                        altura = Math.round(altura * escala);
                    }

                    var canvas = document.createElement('canvas');
                    canvas.width = largura;
                    canvas.height = altura;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, largura, altura);

                    resolve(canvas.toDataURL('image/jpeg', QUALIDADE_JPEG));
                };
                img.src = leitor.result;
            };
            leitor.readAsDataURL(arquivo);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();