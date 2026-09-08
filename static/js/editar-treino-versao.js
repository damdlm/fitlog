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
    // Redução de memória pra listas grandes (catálogo completo,
    // ~1300 itens -- mesmo caso marcado com .etv-grid-static no
    // template/CSS pra desligar a animação de entrada)
    // -----------------------------------------------------
    // As correções anteriores (tooltip preguiçoso, content-visibility,
    // debounce na busca) resolveram custo de RENDERIZAÇÃO, mas os ~1300
    // cards continuavam sempre PRESENTES no DOM -- e isso sozinho já é
    // uma pegada de memória alta. No Safari normal isso tem folga, mas
    // um PWA instalado (modo standalone) roda num WKWebView com teto de
    // memória bem mais apertado; abrir/fechar esse modal repetidas
    // vezes ia empurrando o uso pra cima até estourar esse teto --
    // mesmo sem nenhum vazamento de verdade, só pelo tamanho base já
    // ser grande demais pro ambiente do PWA.
    //
    // Solução: só cerca de 80 cards ficam no DOM de cara (o resto é
    // removido e guardado como texto/HTML puro num Map -- string é
    // muito mais barata que nó de DOM real). Eles voltam pro DOM só
    // quando precisam aparecer de verdade: (a) a busca ou um filtro de
    // músculo é usado de verdade (não a limpeza automática que acontece
    // toda vez que o modal abre), (b) a pessoa rola até o fim da lista
    // inicial, ou (c) um exercício específico já está marcado no treino
    // que está sendo aberto (senão o check dele nunca apareceria).
    // Uma vez de volta no DOM, o card fica lá pro resto da sessão --
    // não tem re-remoção, então não existe risco de perder seleção ou
    // observação já digitada, e o envio do formulário continua 100%
    // nativo (só existe checkbox marcado pra quem já foi renderizado
    // -- e pra ficar marcado, teve que ser renderizado primeiro).
    const ETV_LOTE_INICIAL = 80;
    const etvOcultosPorId = new Map();
    let etvMaterializado = !grid?.classList.contains('etv-grid-static');

    if (!etvMaterializado) {
        itens().slice(ETV_LOTE_INICIAL).forEach(function (card) {
            const id = card.dataset.valor;
            if (!id) return;
            etvOcultosPorId.set(id, card.outerHTML);
            grid.removeChild(card);
        });
    }

    function etvPrepararCardNovo(card) {
        const cb = card.querySelector('.etv-checkbox');
        if (cb) cb.addEventListener('change', () => onCheckboxChange(cb));
    }

    // Traz TODOS os cards restantes de volta, no fim da lista (preserva
    // a ordem original do catálogo). Usado quando a lista precisa ser
    // vasculhada por inteiro: busca de verdade ou rolagem até o fim.
    function etvMaterializarTodos() {
        if (etvMaterializado) return;
        const frag = document.createDocumentFragment();
        const tmp = document.createElement('div');
        etvOcultosPorId.forEach(function (html) {
            tmp.innerHTML = html;
            const card = tmp.firstElementChild;
            etvPrepararCardNovo(card);
            frag.appendChild(card);
        });
        grid.appendChild(frag);
        etvOcultosPorId.clear();
        etvMaterializado = true;
    }

    // Traz só IDs específicos de volta, no INÍCIO da lista -- usado pra
    // garantir que os exercícios já marcados num treino apareçam (e
    // fiquem marcados) mesmo que ainda não tivessem sido renderizados.
    function etvMaterializarPorIds(ids) {
        if (etvMaterializado || !ids || !ids.length) return;
        const frag = document.createDocumentFragment();
        const tmp = document.createElement('div');
        let alguma = false;
        ids.forEach(function (id) {
            const html = etvOcultosPorId.get(id);
            if (!html) return;
            tmp.innerHTML = html;
            const card = tmp.firstElementChild;
            etvPrepararCardNovo(card);
            frag.appendChild(card);
            etvOcultosPorId.delete(id);
            alguma = true;
        });
        if (alguma) grid.prepend(frag);
    }

    // cadastrar-treinos.js dispara isso antes de marcar os checkboxes do
    // treino selecionado no modal compartilhado -- garante que os
    // exercícios já salvos nesse treino existam no DOM antes da
    // sincronização de "marcado/desmarcado" rodar.
    grid?.addEventListener('etv:garantir', function (e) {
        etvMaterializarPorIds(e.detail?.ids);
    });

    // Rolar até perto do fim da lista inicial carrega o resto -- só
    // enquanto ainda faltar algo por materializar.
    const etvScrollContainer = document.querySelector('.etv-scroll');
    etvScrollContainer?.addEventListener('scroll', function () {
        if (etvMaterializado) return;
        const restante = etvScrollContainer.scrollHeight - etvScrollContainer.scrollTop - etvScrollContainer.clientHeight;
        if (restante < 600) etvMaterializarTodos();
    }, { passive: true });

    // -----------------------------------------------------
    // Reordenação (selecionados primeiro)
    // -----------------------------------------------------
    function reordenarSelecionados() {
        if (!grid) return;
        // Só move os SELECIONADOS (tipicamente uma dúzia, no máximo) pro
        // início -- os não-selecionados (podem ser ~1300, o catálogo
        // inteiro) nunca são tocados, já estão na posição certa entre
        // si. Antes, a função reinseria TODOS os itens da grade, um por
        // um (inclusive os que não precisavam mudar de lugar): rodando
        // tanto no carregamento da página quanto toda vez que o modal
        // "Editar" abre, isso pesava bastante -- prepend() com múltiplos
        // nós faz o navegador mover só o que precisa, numa operação só.
        const selecionados = itens().filter(item => {
            const cb = item.querySelector('.etv-checkbox');
            return cb && cb.checked;
        });
        if (selecionados.length) {
            grid.prepend(...selecionados);
        }
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
        if (termo) etvMaterializarTodos();
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

    // Filtrar varre a grade inteira (~1300 itens no catálogo completo)
    // -- sem debounce, digitar rápido dispara essa varredura a cada
    // tecla, empilhando trabalho e deixando a digitação com lag
    // perceptível no celular. 150ms é curto o bastante pra não atrasar
    // a sensação de resposta, mas já absorve a rajada de teclas de uma
    // digitação normal.
    let filtrarTimeoutId = null;
    function filtrarComDebounce() {
        window.clearTimeout(filtrarTimeoutId);
        filtrarTimeoutId = window.setTimeout(filtrar, 150);
    }
    busca?.addEventListener('input', filtrarComDebounce);
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
        if (musculoAtivo) etvMaterializarTodos();
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

    // cadastrar-treinos.js precisa recalcular o contador depois de marcar
    // os checkboxes do treino selecionado no modal compartilhado -- mas
    // SEM disparar 'change' em cada um dos ~1300 checkboxes da grade (isso
    // travava a tela: cada dispatch de 'change' chamava atualizarContador,
    // que varre a grade inteira de novo -- ou seja, ~1300 disparos x ~1300
    // itens escaneados cada = trabalho quadrático). Com esse evento, dá
    // pra recalcular uma vez só, depois de marcar tudo.
    grid?.addEventListener('etv:contador', atualizarContador);

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
    // Criar uma instância de Tooltip pra cada um dos ~1300 exercícios da
    // grade, de uma vez só no carregamento, consumia memória demais e
    // derrubava o processo do Safari no iOS nessa tela (catálogo completo
    // carregado) -- "Um problema ocorreu repetidamente em .../cadastrar-
    // treinos". Em vez disso, a instância só é criada na hora que o
    // elemento é realmente tocado/passa o mouse pela primeira vez
    // (delegação de evento) -- os itens que a pessoa nunca interage não
    // custam nada.
    function inicializarTooltipSobDemanda(e) {
        const el = e.target.closest('[data-bs-toggle="tooltip"]');
        if (!el || el._tooltipPronto) return;
        el._tooltipPronto = true;
        new bootstrap.Tooltip(el, { trigger: 'hover' });
    }
    if (window.bootstrap) {
        grid?.addEventListener('mouseover', inicializarTooltipSobDemanda);
        grid?.addEventListener('touchstart', inicializarTooltipSobDemanda, { passive: true });
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