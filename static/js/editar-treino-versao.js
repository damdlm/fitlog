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

        if (semResultados) {
            semResultados.classList.toggle('d-none', visiveis !== 0);
        }
    }

    function limparFiltro() {
        if (busca) busca.value = '';
        musculoAtivo = '';
        chipsMusculo?.querySelectorAll('.etv-chip').forEach(chip => {
            const ativo = chip.dataset.musculo === '';
            chip.classList.toggle('is-active', ativo);
            chip.setAttribute('aria-pressed', String(ativo));
        });
        filtrar();
    }

    busca?.addEventListener('input', filtrar);
    busca?.addEventListener('keydown', function (e) {
        // O campo de busca vive dentro do <form> principal (não dá pra tirar
        // sem reestruturar o HTML), então Enter aqui submeteria o treino
        // inteiro sem querer. Enter deve só confirmar o filtro.
        if (e.key === 'Enter') e.preventDefault();
    });

    chipsMusculo?.addEventListener('click', function (e) {
        const chip = e.target.closest('.etv-chip');
        if (!chip) return;
        musculoAtivo = chip.dataset.musculo || '';
        chipsMusculo.querySelectorAll('.etv-chip').forEach(c => {
            c.classList.remove('is-active');
            c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('is-active');
        chip.setAttribute('aria-pressed', 'true');
        filtrar();
    });

    btnLimparFiltro?.addEventListener('click', limparFiltro);
    document.getElementById('etvLimparFiltroVazio')?.addEventListener('click', limparFiltro);

    // -----------------------------------------------------
    // Seleção (checkboxes, cards, bandeja de selecionados)
    // -----------------------------------------------------
    function sincronizarCard(checkbox) {
        const card = checkbox.closest('.etv-card');
        if (card) card.classList.toggle('is-selected', checkbox.checked);

        // Campo de observação só faz sentido pra exercício selecionado --
        // desabilita (e não envia valor) quando o card é desmarcado.
        const obsInput = card?.querySelector('.etv-obs-input');
        if (obsInput) obsInput.disabled = !checkbox.checked;
    }

    function atualizarContador() {
        const total = checkboxes().filter(cb => cb.checked).length;
        contadoresSelecionados.forEach(el => { el.textContent = String(total); });
    }

    function onCheckboxChange(checkbox) {
        sincronizarCard(checkbox);
        atualizarContador();
    }

    checkboxes().forEach(cb => {
        cb.addEventListener('change', () => onCheckboxChange(cb));
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