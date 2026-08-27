/* ==========================================================
   Cadastrar Treinos (aluno) — popula o modal compartilhado de
   nome/descrição/exercícios com os dados do treino clicado.

   Depende de:
   - editar-treino-versao.js, já carregado antes deste arquivo,
     que cuida do filtro de busca/músculo, da sincronização visual
     do card (.is-selected) e do contador de selecionados sempre
     que um checkbox dispara 'change' — por isso este script nunca
     mexe em classes/contador diretamente, só marca/desmarca os
     checkboxes e dispara 'change' pra reaproveitar aquela lógica.
   - window.CT_TREINO_EXERCICIOS, um mapa {treino_versao_id: [ids
     prefixados]} embutido pelo template (cadastrar_treinos.html)
     para saber o que já está marcado em cada treino.
   ========================================================== */

document.addEventListener('DOMContentLoaded', function () {
    const modalExercicios = document.getElementById('modalExercicios');
    if (!modalExercicios) return; // Não é a tela de Cadastrar Treinos

    const form = document.getElementById('formEditarTreino');
    const inputNome = document.getElementById('ctInputNome');
    const inputDescricao = document.getElementById('ctInputDescricao');
    const modalCodigo = document.getElementById('ctModalCodigo');
    const busca = document.getElementById('etvBusca');
    const grid = document.getElementById('etvGrid');
    const chipTodos = document.querySelector('#etvChipsMusculo .etv-chip[data-musculo=""]');

    function checkboxesDoGrid() {
        return grid ? Array.from(grid.querySelectorAll('.etv-checkbox')) : [];
    }

    modalExercicios.addEventListener('show.bs.modal', function (event) {
        const trigger = event.relatedTarget;
        if (!trigger) return;

        const treinoVersaoId = trigger.getAttribute('data-treino-versao-id') || '';
        const codigo = trigger.getAttribute('data-treino-codigo') || '';
        const nome = trigger.getAttribute('data-treino-nome') || '';
        const descricao = trigger.getAttribute('data-treino-descricao') || '';
        const action = trigger.getAttribute('data-action') || '';

        if (form && action) form.action = action;
        if (inputNome) inputNome.value = nome;
        if (inputDescricao) inputDescricao.value = descricao;
        if (modalCodigo) modalCodigo.textContent = codigo;

        // Reseta filtros (busca + chip de músculo) pra sempre abrir com
        // a lista completa visível, independente do que ficou setado
        // na última vez que o modal foi usado para outro treino.
        if (busca) {
            busca.value = '';
            busca.dispatchEvent(new Event('input', { bubbles: true }));
        }
        chipTodos?.click();

        const mapa = window.CT_TREINO_EXERCICIOS || {};
        const mapaObs = window.CT_TREINO_OBSERVACOES || {};
        const selecionados = new Set(mapa[treinoVersaoId] || []);
        const observacoes = mapaObs[treinoVersaoId] || {};

        checkboxesDoGrid().forEach(function (cb) {
            const deveEstarMarcado = selecionados.has(cb.value);
            if (cb.checked !== deveEstarMarcado) {
                cb.checked = deveEstarMarcado;
            }
            // Dispara 'change' sempre (mesmo sem alterar .checked) pra
            // garantir que o card e o contador fiquem consistentes com
            // o estado atual, já que os listeners de editar-treino-versao.js
            // só reagem a eventos, não ao valor sendo setado via JS.
            cb.dispatchEvent(new Event('change', { bubbles: true }));

            // Campo de observação -- só faz sentido preencher quando o
            // exercício está marcado; o próprio listener de 'change' acima
            // (editar-treino-versao.js) já cuida de habilitar/desabilitar
            // o input conforme o checkbox, aqui só define o valor salvo.
            const card = cb.closest('.etv-card');
            const obsInput = card?.querySelector('.etv-obs-input');
            if (obsInput) {
                obsInput.value = deveEstarMarcado ? (observacoes[cb.value] || '') : '';
            }
        });

        // Traz os exercícios já marcados pra esse treino pro início
        // da lista (editar-treino-versao.js escuta esse evento).
        grid?.dispatchEvent(new CustomEvent('etv:reordenar'));
    });
});