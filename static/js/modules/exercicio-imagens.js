/**
 * Modais globais de mídia (gif/vídeo) e instruções do exercício.
 *
 * Cada botão ".btn-imagens-exercicio" carrega no data-attribute "gif" o
 * caminho relativo do arquivo de demonstração (ex: "videos/0001-2gPfomN.gif"
 * ou "videos/0001-2gPfomN.mp4"), salvo no campo gif_url de ExercicioSistema.
 * Apesar do nome do campo, a pasta no volume é "videos/" e alguns
 * exercícios têm vídeo (.mp4/.webm/.mov) em vez de gif -- por isso o
 * caminho é escolhido dinamicamente entre <img> e <video> conforme a
 * extensão do arquivo, em vez de sempre tentar renderizar como imagem
 * (o que deixava vídeos "sem carregar", já que <img> não reproduz mp4).
 *
 * Os arquivos ficam num volume do Railway montado em /app/exercicios,
 * servido pela rota /exercicios-media/<caminho> (ver app.py).
 */
(function () {
    'use strict';

    const BASE_PATH = '/exercicios-media/';
    const EXTENSOES_VIDEO = ['mp4', 'webm', 'mov', 'm4v'];

    let modalInstance = null;

    function getModalEls() {
        return {
            modalEl: document.getElementById('modalImagensExercicio'),
            img: document.getElementById('modalImagensExercicioImg'),
            video: document.getElementById('modalImagensExercicioVideo'),
            spinner: document.getElementById('modalImagensExercicioSpinner'),
            erro: document.getElementById('modalImagensExercicioErro'),
            nome: document.getElementById('modalImagensExercicioNome'),
            contador: document.getElementById('modalImagensExercicioContador'),
        };
    }

    function montarUrl(caminho) {
        if (!caminho) return null;
        return BASE_PATH + String(caminho).replace(/^\/+/, '');
    }

    function extensao(caminho) {
        const semQuery = String(caminho).split(/[?#]/)[0];
        const partes = semQuery.split('.');
        return partes.length > 1 ? partes.pop().toLowerCase() : '';
    }

    function frameDoSpinner(els) {
        return els.spinner.closest('.exmodal-media-frame');
    }

    function mostrarSpinner(els) {
        els.spinner.classList.remove('d-none');
        els.erro.classList.remove('is-visible');
        // Dá espaço mínimo pra moldura enquanto não há mídia real visível
        // (nem carregada, nem em erro) -- ver .exmodal-media-frame.is-vazia.
        // Removida assim que a mídia carrega de verdade (onload/oncanplay
        // abaixo), pra moldura passar a abraçar só o tamanho real dela.
        frameDoSpinner(els).classList.add('is-vazia');
    }

    function esconderSpinner(els) {
        els.spinner.classList.add('d-none');
    }

    function mostrarErro(els) {
        esconderSpinner(els);
        els.erro.classList.add('is-visible');
        els.img.classList.add('d-none');
        els.video.classList.add('d-none');
        // Continua "vazia" (sem mídia real) -- mantém o espaço mínimo
        // pra mensagem de erro não ficar sem altura pra aparecer.
        frameDoSpinner(els).classList.add('is-vazia');
    }

    // Avisa a página que um vídeo de demonstração vai tocar / parou. O
    // modo treino (registrar_treino.html) mantém a tela acesa com um
    // <video> invisível em loop quando o iPhone não concede o Wake Lock
    // nativo; com ele tocando, começar o MP4 da demonstração derrubava o
    // processo de vídeo do iOS e a página inteira congelava (só voltava
    // fechando o app -- e o treino em andamento recarregava do zero).
    // Ele pausa esse vídeo enquanto a demonstração está aberta.
    function avisarVideo(aberto) {
        document.dispatchEvent(new CustomEvent('fitlog:midia-video', { detail: { aberto: aberto } }));
    }

    // Um <video> NOVO a cada abertura, descartado ao fechar (em vez de
    // trocar o src do mesmo elemento e chamar load() no meio da animação
    // do modal): é o caminho mais previsível para o WebKit do iPhone.
    function novoVideo(els) {
        const v = els.video.cloneNode(false);
        v.removeAttribute('src');
        v.classList.add('d-none');
        v.controls = false;
        els.video.replaceWith(v);
        els.video = v;
        return v;
    }

    function descartarVideo(els) {
        const v = els.video;
        v.oncanplay = null;
        v.onloadeddata = null;
        v.onerror = null;
        try { v.pause(); } catch (e) { /* ignora */ }
        if (v.hasAttribute('src')) {
            v.removeAttribute('src');
            try { v.load(); } catch (e) { /* ignora */ }
        }
        novoVideo(els);
    }

    function carregarVideo(els, url) {
        const v = els.video;
        v.onerror = function () { mostrarErro(els); };
        // Sem controles: a animação se comporta como o GIF (loop mudo).
        // Uma única tentativa de tocar quando o primeiro quadro chega; se
        // o navegador barrar o autoplay (iPhone em modo de economia de
        // energia), mostra os controles para o aluno tocar.
        v.onloadeddata = function () {
            v.onloadeddata = null;
            esconderSpinner(els);
            frameDoSpinner(els).classList.remove('is-vazia');
            v.classList.remove('d-none');
            const tocando = v.play();
            if (tocando && tocando.catch) {
                tocando.catch(function () { v.controls = true; });
            }
        };
        v.src = url;
    }

    window.abrirModalImagensExercicio = function (btn) {
        const nome = btn.dataset.nome || 'Exercício';
        const caminhoOriginal = btn.dataset.gif;
        const url = montarUrl(caminhoOriginal);

        if (!url) return;

        const els = getModalEls();
        if (!els.modalEl) return;

        els.nome.textContent = nome;
        if (els.contador) els.contador.classList.add('d-none');

        const ehVideo = EXTENSOES_VIDEO.indexOf(extensao(caminhoOriginal)) !== -1;
        // Cada abertura ganha um número: um "shown" ou "hidden" atrasado de
        // uma abertura anterior (aluno fechou e já tocou em outro
        // exercício) não mexe na mídia da atual.
        const abertura = (els.modalEl._flAbertura || 0) + 1;
        els.modalEl._flAbertura = abertura;

        mostrarSpinner(els);
        els.img.classList.add('d-none');
        // Zera handlers de uma abertura anterior para não empilhar.
        els.img.onload = null;
        els.img.onerror = null;
        descartarVideo(els);

        // Vídeo: pausa o vídeo invisível do modo treino. GIF: libera (se
        // uma abertura anterior com vídeo não chegou a avisar o fim).
        avisarVideo(ehVideo);
        if (!ehVideo) {
            els.img.onerror = function () { mostrarErro(els); };
            els.img.onload = function () {
                esconderSpinner(els);
                frameDoSpinner(els).classList.remove('is-vazia');
                els.img.classList.remove('d-none');
            };
            els.img.alt = nome;
            els.img.src = url;
        }

        modalInstance = bootstrap.Modal.getOrCreateInstance(els.modalEl);
        const modalEl = els.modalEl;

        // Para e descarta o vídeo ao fechar, pra não continuar tocando (e
        // baixando) em segundo plano depois que o modal já foi fechado.
        function aoFechar() {
            if (modalEl._flAbertura !== abertura) return;
            descartarVideo(els);
            if (ehVideo) avisarVideo(false);
        }

        // Só depois que o modal terminou de abrir: o vídeo começa a
        // carregar (não no mesmo quadro em que o vídeo do modo treino
        // acabou de ser pausado e a animação do modal começou) e passa a
        // valer o "ao fechar" desta abertura.
        function aoMostrar() {
            if (modalEl._flAbertura !== abertura) return;
            if (ehVideo) carregarVideo(els, url);
            modalEl.addEventListener('hidden.bs.modal', aoFechar, { once: true });
        }

        if (modalEl.classList.contains('show')) {
            aoMostrar();
            return;
        }
        modalEl.addEventListener('shown.bs.modal', aoMostrar, { once: true });

        // Ainda fechando a abertura anterior (aluno fechou e já tocou em
        // outro exercício): o Bootstrap ignora o show() durante a animação
        // de fechar e nada abria -- era preciso tocar de novo. Abre assim
        // que ela terminar.
        if (modalEl.style.display === 'block') {
            modalEl.addEventListener('hidden.bs.modal', function () {
                if (modalEl._flAbertura === abertura) modalInstance.show();
            }, { once: true });
            return;
        }
        modalInstance.show();
    };

    window.abrirModalInstrucoesExercicio = function (btn) {
        const nome = btn.dataset.nome || 'Exercício';
        let passos = [];
        try {
            passos = JSON.parse(btn.dataset.passos || '[]');
        } catch (e) {
            passos = [];
        }
        if (!Array.isArray(passos) || !passos.length) return;

        const tituloEl = document.getElementById('modalInstrucoesExercicioNome');
        const listaEl = document.getElementById('modalInstrucoesExercicioLista');
        const modalEl = document.getElementById('modalInstrucoesExercicio');
        if (!modalEl || !listaEl) return;

        tituloEl.textContent = nome;
        listaEl.innerHTML = '';
        passos.forEach(function (passo, indice) {
            const li = document.createElement('li');
            li.className = 'exmodal-step';

            const numero = document.createElement('span');
            numero.className = 'exmodal-step-num';
            numero.textContent = String(indice + 1);

            const texto = document.createElement('span');
            texto.className = 'exmodal-step-text';
            texto.textContent = passo;

            li.appendChild(numero);
            li.appendChild(texto);
            listaEl.appendChild(li);
        });

        bootstrap.Modal.getOrCreateInstance(modalEl).show();

        // Liga/desliga o fade de "role pra ver mais" (ver CSS em
        // base.html) conforme o conteúdo realmente precisa de rolagem e
        // conforme o usuário já rolou até o fim ou não. Roda de novo a
        // cada 'shown.bs.modal' porque max-height do modal-body depende
        // de --fl-crono-flutuante-altura, que só é conhecida depois do
        // modal (e a barra flutuante, se houver) já estarem no layout
        // final -- medir cedo demais (antes do show) dava dimensões
        // erradas em alguns navegadores.
        const corpoEl = modalEl.querySelector('.modal-body');
        if (!corpoEl) return;

        function atualizarFadeRolagem() {
            const rolavel = corpoEl.scrollHeight > (corpoEl.clientHeight + 2);
            corpoEl.classList.toggle('is-rolavel', rolavel);
            const noFim = !rolavel ||
                (corpoEl.scrollTop + corpoEl.clientHeight >= corpoEl.scrollHeight - 4);
            corpoEl.classList.toggle('no-fim', noFim);
        }

        corpoEl.removeEventListener('scroll', atualizarFadeRolagem);
        corpoEl.addEventListener('scroll', atualizarFadeRolagem, { passive: true });

        modalEl.addEventListener('shown.bs.modal', function aoAbrir() {
            atualizarFadeRolagem();
            modalEl.removeEventListener('shown.bs.modal', aoAbrir);
        });
    };
})();