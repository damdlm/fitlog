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

    // Remove acentos para a busca não diferenciar "peito" de "pé" ->
    // "supino inclinado" bater buscando "inclinaddo" sem acento,
    // "tríceps" bater buscando "triceps", etc. NFD separa a letra do
    // acento (combining diacritical mark) e o regex descarta a marca.
    function normalizarTexto(texto) {
        return (texto || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function itens() {
        return grid ? Array.from(grid.querySelectorAll('.etv-card')) : [];
    }

    function checkboxes() {
        return grid ? Array.from(grid.querySelectorAll('.etv-checkbox')) : [];
    }

    // -----------------------------------------------------
    // Reordenação (selecionados primeiro)
    // -----------------------------------------------------
    // Move os cards já marcados para o início da lista, mantendo a
    // ordem original dentro de cada grupo (selecionados / não
    // selecionados). appendChild em um nó que já existe no DOM só
    // move ele -- não duplica -- então isso não perde listeners nem
    // o estado do checkbox.
    function reordenarSelecionados() {
        if (!grid) return;
        const selecionados = [];
        const outros = [];

        itens().forEach(item => {
            const cb = item.querySelector('.etv-checkbox');
            (cb && cb.checked ? selecionados : outros).push(item);
        });

        selecionados.forEach(item => grid.appendChild(item));
        outros.forEach(item => grid.appendChild(item));
    }

    // cadastrar-treinos.js reaproveita este grid num modal compartilhado
    // entre vários treinos; quando ele marca os checkboxes de um treino
    // específico ao abrir o modal, dispara este evento pra reordenar de
    // novo (não dá pra chamar reordenarSelecionados() direto, ela é
    // local a este closure).
    grid?.addEventListener('etv:reordenar', reordenarSelecionados);

    // -----------------------------------------------------
    // Filtro (texto + músculo)
    // -----------------------------------------------------
    function filtrar() {
        const termo = normalizarTexto((busca?.value || '').toLowerCase().trim());
        let visiveis = 0;

        itens().forEach(item => {
            const nome = normalizarTexto(item.dataset.nome || '');
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

    // O card inteiro é um <label for="..."> (facilita o alvo de toque),
    // mas o comportamento padrão do label é repassar QUALQUER clique
    // dentro dele para o checkbox associado -- isso brigava com o
    // tooltip do nome (clicar no nome pra ver o nome completo/nicknames
    // também selecionava/desmarcava o exercício). Agora só o clique no
    // próprio checkbox seleciona; clique em qualquer outro ponto do
    // card é ignorado (preventDefault cancela o repasse do label).
    grid?.addEventListener('click', function (e) {
        if (e.target.closest('.etv-checkbox')) return;
        if (!e.target.closest('.etv-card')) return;
        e.preventDefault();
    });

    // -----------------------------------------------------
    // Tooltips (Bootstrap) — nome completo e nicknames do exercício
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
    reordenarSelecionados();
});