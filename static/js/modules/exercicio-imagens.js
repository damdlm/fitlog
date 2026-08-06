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

    function mostrarSpinner(els) {
        els.spinner.classList.remove('d-none');
        els.erro.classList.remove('is-visible');
    }

    function esconderSpinner(els) {
        els.spinner.classList.add('d-none');
    }

    function mostrarErro(els) {
        esconderSpinner(els);
        els.erro.classList.add('is-visible');
        els.img.classList.add('d-none');
        els.video.classList.add('d-none');
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

        mostrarSpinner(els);
        els.img.classList.add('d-none');
        els.video.classList.add('d-none');
        // Zera handlers de uma abertura anterior para não empilhar.
        els.img.onload = null;
        els.img.onerror = null;
        els.video.oncanplay = null;
        els.video.onerror = null;

        if (ehVideo) {
            els.video.onerror = function () { mostrarErro(els); };
            els.video.oncanplay = function () {
                esconderSpinner(els);
                els.video.classList.remove('d-none');
            };
            els.video.src = url;
            els.video.load();
        } else {
            els.img.onerror = function () { mostrarErro(els); };
            els.img.onload = function () {
                esconderSpinner(els);
                els.img.classList.remove('d-none');
            };
            els.img.alt = nome;
            els.img.src = url;
        }

        modalInstance = bootstrap.Modal.getOrCreateInstance(els.modalEl);
        modalInstance.show();

        // Pausa/reseta o vídeo ao fechar, pra não continuar tocando (e
        // baixando) em segundo plano depois que o modal já foi fechado.
        els.modalEl.addEventListener('hidden.bs.modal', function aoFechar() {
            els.video.pause();
            els.video.removeAttribute('src');
            els.video.load();
            els.modalEl.removeEventListener('hidden.bs.modal', aoFechar);
        });
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
    };
})();