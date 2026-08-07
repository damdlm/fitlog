/* ==========================================================
   Editar Treino na Versão — comportamento compartilhado
   Usado por: templates/version/, templates/aluno/,
              templates/professor/editar_treino_versao*.html
   Depende de FitLogUtils (static/js/fitlog-utils.js) para toasts,
   com fallback para alert() caso não esteja disponível.
   ========================================================== */

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('formEditarTreino');
    if (!form) return; // Página não é uma tela de editar treino na versão

    const busca = document.getElementById('etvBusca');
    const chipsMusculo = document.getElementById('etvChipsMusculo');
    const grid = document.getElementById('etvGrid');
    const semResultados = document.getElementById('etvSemResultados');
    const contadorVisiveis = document.getElementById('etvContadorVisiveis');
    const tray = document.getElementById('etvTray');
    const btnSelecionarVisiveis = document.getElementById('etvSelecionarVisiveis');
    const btnLimparTodos = document.getElementById('etvLimparTodos');
    const btnLimparFiltro = document.getElementById('etvLimparFiltro');
    const contadoresSelecionados = document.querySelectorAll('[data-etv-contador-selecionados]');

    let musculoAtivo = '';

    function itens() {
        return grid ? Array.from(grid.querySelectorAll('.etv-card')) : [];
    }

    function checkboxes() {
        return grid ? Array.from(grid.querySelectorAll('.etv-checkbox')) : [];
    }

    // -----------------------------------------------------
    // Filtro (texto + músculo)
    // -----------------------------------------------------
    function filtrar() {
        const termo = (busca?.value || '').toLowerCase().trim();
        let visiveis = 0;

        itens().forEach(item => {
            const nome = item.dataset.nome || '';
            const musculo = item.dataset.musculo || '';
            let mostrar = true;

            if (termo && !nome.includes(termo)) mostrar = false;
            if (musculoAtivo && musculo !== musculoAtivo) mostrar = false;

            item.classList.toggle('d-none', !mostrar);
            if (mostrar) visiveis++;
        });

        if (contadorVisiveis) {
            contadorVisiveis.textContent = visiveis + ' exercício(s) encontrado(s)';
        }
        if (semResultados) {
            semResultados.classList.toggle('d-none', visiveis !== 0);
        }
    }

    function limparFiltro() {
        if (busca) busca.value = '';
        musculoAtivo = '';
        chipsMusculo?.querySelectorAll('.etv-chip').forEach(chip => {
            chip.classList.toggle('is-active', chip.dataset.musculo === '');
        });
        filtrar();
    }

    busca?.addEventListener('input', filtrar);

    chipsMusculo?.addEventListener('click', function (e) {
        const chip = e.target.closest('.etv-chip');
        if (!chip) return;
        musculoAtivo = chip.dataset.musculo || '';
        chipsMusculo.querySelectorAll('.etv-chip').forEach(c => c.classList.remove('is-active'));
        chip.classList.add('is-active');
        filtrar();
    });

    btnLimparFiltro?.addEventListener('click', limparFiltro);

    // -----------------------------------------------------
    // Seleção (checkboxes, cards, bandeja de selecionados)
    // -----------------------------------------------------
    function sincronizarCard(checkbox) {
        const card = checkbox.closest('.etv-card');
        if (card) card.classList.toggle('is-selected', checkbox.checked);
    }

    function atualizarTray() {
        if (!tray) return;
        const marcados = checkboxes().filter(cb => cb.checked);

        if (marcados.length === 0) {
            tray.classList.add('is-empty');
            tray.innerHTML = '';
            return;
        }

        tray.classList.remove('is-empty');
        tray.innerHTML = marcados.map(cb => {
            const nome = cb.closest('.etv-card')?.dataset.nomeDisplay || cb.value;
            return `<span class="etv-tray-chip" data-tray-for="${cb.id}">${nome}` +
                   `<button type="button" aria-label="Remover ${nome}"><i class="bi bi-x"></i></button></span>`;
        }).join('');
    }

    tray?.addEventListener('click', function (e) {
        const btn = e.target.closest('button[aria-label]');
        if (!btn) return;
        const chip = btn.closest('.etv-tray-chip');
        const cb = document.getElementById(chip?.dataset.trayFor);
        if (cb) {
            cb.checked = false;
            sincronizarCard(cb);
            atualizarContador();
        }
    });

    function atualizarContador() {
        const total = checkboxes().filter(cb => cb.checked).length;
        contadoresSelecionados.forEach(el => { el.textContent = String(total); });
        atualizarTray();
    }

    function onCheckboxChange(checkbox) {
        sincronizarCard(checkbox);
        atualizarContador();
    }

    checkboxes().forEach(cb => {
        cb.addEventListener('change', () => onCheckboxChange(cb));
    });

    btnSelecionarVisiveis?.addEventListener('click', function () {
        itens().forEach(item => {
            if (item.classList.contains('d-none')) return;
            const cb = item.querySelector('.etv-checkbox');
            if (cb && !cb.checked) {
                cb.checked = true;
                sincronizarCard(cb);
            }
        });
        atualizarContador();
    });

    btnLimparTodos?.addEventListener('click', function () {
        checkboxes().forEach(cb => {
            cb.checked = false;
            sincronizarCard(cb);
        });
        atualizarContador();
    });

    // -----------------------------------------------------
    // Tooltips (Bootstrap) — descrição completa do exercício
    // -----------------------------------------------------
    if (window.bootstrap) {
        grid?.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            new bootstrap.Tooltip(el, { trigger: 'hover' });
        });
    }

    // -----------------------------------------------------
    // Envio do formulário
    // -----------------------------------------------------
    form.addEventListener('submit', function (e) {
        const marcados = checkboxes().filter(cb => cb.checked).length;
        if (marcados === 0) {
            e.preventDefault();
            const msg = 'Selecione pelo menos um exercício para o treino!';
            if (window.FitLogUtils?.showToast) {
                window.FitLogUtils.showToast(msg, 'warning');
            } else {
                alert(msg);
            }
            return false;
        }

        document.querySelectorAll('.etv-btn-save').forEach(btn => {
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Salvando...';
            btn.disabled = true;
        });
    });

    // Estado inicial
    atualizarContador();
    filtrar();
});