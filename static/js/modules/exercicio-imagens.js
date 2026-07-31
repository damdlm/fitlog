/**
 * Modal de gif do exercício.
 *
 * Cada botão ".btn-imagens-exercicio" carrega no data-attribute "gif" o
 * caminho relativo do gif (ex: "videos/0001-2gPfomN.gif"), salvo no
 * campo gif_url de ExercicioSistema.
 *
 * Os arquivos ficam num volume do Railway montado em /app/exercicios,
 * servido pela rota /exercicios-media/<caminho> (ver app.py).
 */
(function () {
    'use strict';

    const BASE_PATH = '/exercicios-media/';

    let modalInstance = null;

    function getModalEls() {
        return {
            modalEl: document.getElementById('modalImagensExercicio'),
            img: document.getElementById('modalImagensExercicioImg'),
            legenda: document.getElementById('modalImagensExercicioLegenda'),
            titulo: document.getElementById('modalImagensExercicioLabel'),
            contador: document.getElementById('modalImagensExercicioContador'),
        };
    }

    function montarUrl(caminho) {
        if (!caminho) return null;
        return BASE_PATH + String(caminho).replace(/^\/+/, '');
    }

    window.abrirModalImagensExercicio = function (btn) {
        const nome = btn.dataset.nome || 'Exercício';
        const gif = montarUrl(btn.dataset.gif);

        if (!gif) return;

        const els = getModalEls();
        if (!els.modalEl) return;

        els.titulo.textContent = nome;
        els.img.src = gif;
        els.img.alt = nome;
        els.legenda.textContent = '';

        // Modal agora mostra um único gif
        if (els.contador) els.contador.classList.add('d-none');

        els.img.onerror = function () {
            els.legenda.textContent = 'Não foi possível carregar este gif.';
        };

        modalInstance = bootstrap.Modal.getOrCreateInstance(els.modalEl);
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

        const tituloEl = document.getElementById('modalInstrucoesExercicioLabel');
        const listaEl = document.getElementById('modalInstrucoesExercicioLista');
        const modalEl = document.getElementById('modalInstrucoesExercicio');
        if (!modalEl || !listaEl) return;

        tituloEl.textContent = nome;
        listaEl.innerHTML = '';
        passos.forEach(function (passo) {
            const li = document.createElement('li');
            li.textContent = passo;
            listaEl.appendChild(li);
        });

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    };
})();
