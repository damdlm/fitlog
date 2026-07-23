/**
 * Modal de imagens do exercício.
 *
 * Cada botão ".btn-imagens-exercicio" carrega nos data-attributes o(s)
 * caminho(s) relativo(s) das imagens (ex: "Ab_Crunch_Machine/0.jpg"),
 * salvos nos campos imagem_inicial / imagem_execucao de ExercicioBase.
 * As imagens ficam em static/exercicios/<pasta>/<arquivo>.
 */
(function () {
    'use strict';

    const BASE_PATH = '/static/exercicios/';

    let imagens = [];
    let indiceAtual = 0;
    let modalInstance = null;

    function getModalEls() {
        return {
            modalEl: document.getElementById('modalImagensExercicio'),
            img: document.getElementById('modalImagensExercicioImg'),
            legenda: document.getElementById('modalImagensExercicioLegenda'),
            titulo: document.getElementById('modalImagensExercicioLabel'),
            contador: document.getElementById('modalImagensExercicioContador'),
            btnAnterior: document.getElementById('btnImgExercicioAnterior'),
            btnProxima: document.getElementById('btnImgExercicioProxima'),
        };
    }

    function montarUrl(caminho) {
        if (!caminho) return null;
        return BASE_PATH + String(caminho).replace(/^\/+/, '');
    }

    function atualizarTela() {
        const els = getModalEls();
        if (!els.modalEl || !imagens.length) return;

        const atual = imagens[indiceAtual];
        els.img.src = atual.url;
        els.img.alt = atual.label;
        els.legenda.textContent = atual.label;

        const temMaisDeUma = imagens.length > 1;
        els.btnAnterior.classList.toggle('d-none', !temMaisDeUma);
        els.btnProxima.classList.toggle('d-none', !temMaisDeUma);
        els.contador.classList.toggle('d-none', !temMaisDeUma);
        if (temMaisDeUma) {
            els.contador.textContent = (indiceAtual + 1) + ' / ' + imagens.length;
        }
    }

    window.alternarImagemExercicio = function (direcao) {
        if (imagens.length < 2) return;
        indiceAtual = (indiceAtual + direcao + imagens.length) % imagens.length;
        atualizarTela();
    };

    window.abrirModalImagensExercicio = function (btn) {
        const nome = btn.dataset.nome || 'Exercício';
        const inicial = montarUrl(btn.dataset.imgInicial);
        const execucao = montarUrl(btn.dataset.imgExecucao);

        imagens = [];
        if (inicial) imagens.push({ url: inicial, label: 'Posição inicial' });
        if (execucao) imagens.push({ url: execucao, label: 'Execução' });

        if (!imagens.length) return;

        indiceAtual = 0;

        const els = getModalEls();
        if (!els.modalEl) return;
        els.titulo.textContent = nome;

        els.img.onerror = function () {
            els.legenda.textContent = 'Não foi possível carregar esta imagem.';
        };

        atualizarTela();

        modalInstance = bootstrap.Modal.getOrCreateInstance(els.modalEl);
        modalInstance.show();
    };
})();