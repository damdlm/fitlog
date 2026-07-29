/* ============================================================
   FitBot · Assistente virtual de treino (chat com IA)
   ============================================================
   - Máquina de estados do robô: greeting (ao abrir) -> idle (com um
     vídeo de humor sorteado) -> thinking (aguardando IA) -> talking
     ou error -> idle de novo -> bye (ao fechar o modal). Cada estado
     mostra um <video> diferente dentro de .fitbot-avatar-frame (ver
     fitbot-chat.css).
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
    var DURACAO_ESTADO_GREETING_MS = 2200;
    var DURACAO_ESTADO_BYE_MS = 1200;

    // Vídeos "de humor" do FitBot — sem significado fixo, só para
    // deixar a espera mais divertida. Um é sorteado toda vez que o
    // robô volta para o estado parado (idle).
    var VIDEOS_POOL_IDLE = [

        'Agachamento.mp4', 'agua.mp4', 'arremesso.mp4', 'beijo.mp4',
        'celular.mp4', 'dancando.mp4', 'fortao.mp4',
        'stiff.mp4',
    ];
    // "padrao.mp4" não entra no sorteio -- ele é intercalado manualmente
    // entre os aleatórios (ver escolherProximoVideoIdle): aleatório,
    // padrão, aleatório, padrão... sempre alternando.
    var VIDEO_PADRAO_IDLE = 'padrao.mp4';
    var PASTA_VIDEOS = '/static/videos/fitbot/';
    var CROSSFADE_DURACAO_MS = 450; // precisa bater com a transition do CSS

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
    var DURACAO_ROTACAO_IDLE_FALLBACK_MS = 6000; // usado só se não der pra ler a duração do vídeo

    var historico = [];               // [{papel: 'usuario'|'bot', texto: '...'}]
    var imagemSelecionadaDataUrl = null; // dataURL completo (para preview)
    var estadoTimeoutId = null;
    var conversaIniciada = false;

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

        elModal.addEventListener('shown.bs.modal', onModalShown);

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
        if (conversaIniciada) return;
        conversaIniciada = true;
        setState('greeting');
        adicionarMensagem(
            'bot',
            'Oi! Eu sou o FitBot 🤖, o personal trainer virtual do FitLog. ' +
            'Pode me perguntar sobre musculação, aeróbico, execução de exercícios ' +
            'ou me mandar uma foto de um equipamento que eu explico como usar.'
        );
    }

    function despedirEFechar() {
        setState('bye');
        setTimeout(function () {
            var instancia = bootstrap.Modal.getOrCreateInstance(elModal);
            instancia.hide();
            setState('idle');
        }, DURACAO_ESTADO_BYE_MS);
    }

    /* ------------------------------------------------------------
       Máquina de estados do robô
       ------------------------------------------------------------ */
    function setState(novoEstado) {
        if (estadoTimeoutId) {
            clearTimeout(estadoTimeoutId);
            estadoTimeoutId = null;
        }
        elWidget.classList.remove('is-idle', 'is-thinking', 'is-talking', 'is-error', 'is-greeting', 'is-bye');
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
        } else if (novoEstado === 'greeting') {
            estadoTimeoutId = setTimeout(function () { setState('idle'); }, DURACAO_ESTADO_GREETING_MS);
        }

        if (novoEstado === 'idle') {
            sortearVideoIdle();
        }

        trocarVideoAtivo(novoEstado);
    }

    function trocarVideoAtivo(estado) {
        var videos = elWidget.querySelectorAll('.fitbot-avatar-frame video');
        for (var i = 0; i < videos.length; i++) {
            var video = videos[i];
            var ehDoEstadoAtual = video.getAttribute('data-state') === estado;

            if (estado === 'idle' && ehDoEstadoAtual) {
                // Os dois buffers de idle são geridos por sortearVideoIdle
                // (play/pause/crossfade) -- não mexe neles aqui.
                continue;
            }

            if (!ehDoEstadoAtual) {
                video.classList.remove('is-active');
                video.pause();
                continue;
            }

            video.classList.add('is-active');
            video.currentTime = 0;
            var promessa = video.play();
            if (promessa && promessa.catch) promessa.catch(function () {});
        }
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

    function sortearVideoIdle() {
        if (!elIdleInativo) return;

        var proximoNome = escolherProximoVideoIdle();
        var bufferAlvo = elIdleInativo; // carrega o próximo vídeo no buffer que está escondido agora

        bufferAlvo.src = PASTA_VIDEOS + proximoNome;
        bufferAlvo.load();

        // Assim que soubermos a duração do vídeo sorteado, dá play nele
        // (ainda invisível, opacity 0) e faz o crossfade com o buffer
        // anterior -- só então agenda a próxima troca. Se a duração não
        // vier (erro de carregamento etc), cai no tempo fixo de fallback.
        bufferAlvo.addEventListener('loadedmetadata', function aoCarregar() {
            bufferAlvo.removeEventListener('loadedmetadata', aoCarregar);

            var promessa = bufferAlvo.play();
            if (promessa && promessa.catch) promessa.catch(function () {});

            var bufferAnterior = elIdleAtivo;

            // Crossfade: o novo sobe de opacidade enquanto o antigo desce,
            // ao mesmo tempo (CSS: transition de opacity em ambos) -- em
            // vez do corte seco de antes.
            bufferAlvo.classList.add('is-active');
            if (bufferAnterior) bufferAnterior.classList.remove('is-active');

            elIdleAtivo = bufferAlvo;
            elIdleInativo = bufferAnterior;

            // Só pausa o buffer antigo depois que o crossfade terminar,
            // pra não "congelar" ele no meio da transição visível.
            setTimeout(function () {
                if (bufferAnterior && bufferAnterior !== elIdleAtivo) {
                    bufferAnterior.pause();
                }
            }, CROSSFADE_DURACAO_MS);

            agendarProximaRotacaoIdle();
        });
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