/* ==========================================================
   Cadastrar Treinos (aluno) — reordenar exercícios dentro de
   cada card de treino via drag-and-drop (SortableJS).

   Reaproveita a API já existente /api/reordenar-exercicios
   (mesma usada em aluno/ver_versao.html), que recebe
   {versao_id, treino_codigo, nova_ordem} e persiste o campo
   `ordem` de VersaoExercicio -- ownership já validada no
   servidor via VersaoService.get_by_id(versao_id, user_id).

   Depende de:
   - SortableJS (carregado antes deste arquivo)
   - window.CT_VERSAO_ID, embutido pelo template
   - FitLogUtils (fitlog-utils.js, carregado globalmente em
     base.html), usado só pro toast de sucesso/erro
   ========================================================== */

document.addEventListener('DOMContentLoaded', function () {
    const listas = document.querySelectorAll('.ct-ex-list');
    if (!listas.length || typeof Sortable === 'undefined') return;

    listas.forEach(function (lista) {
        const treinoCodigo = lista.dataset.treinoCodigo;
        const btnSalvar = document.querySelector(
            `.ct-save-order-btn[data-treino-codigo="${treinoCodigo}"]`
        );

        Sortable.create(lista, {
            animation: 200,
            handle: '.ct-ex-drag-handle',
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: function () {
                if (btnSalvar) btnSalvar.classList.add('is-visible');
            }
        });

        if (btnSalvar) {
            btnSalvar.addEventListener('click', function () {
                salvarOrdem(lista, treinoCodigo, btnSalvar);
            });
        }
    });

    async function salvarOrdem(lista, treinoCodigo, btnSalvar) {
        const novaOrdem = Array.from(lista.querySelectorAll('.ct-ex-item'))
            .map(function (item) { return item.dataset.exercicioId; })
            .filter(Boolean);

        if (!novaOrdem.length) return;

        const textoOriginal = btnSalvar.innerHTML;
        btnSalvar.disabled = true;
        btnSalvar.innerHTML = '<i class="bi bi-hourglass-split"></i> Salvando...';

        try {
            const data = await FitLogUtils.apiCall('/api/reordenar-exercicios', 'POST', {
                versao_id: window.CT_VERSAO_ID,
                treino_codigo: treinoCodigo,
                nova_ordem: novaOrdem
            });

            if (data && data.success) {
                btnSalvar.classList.remove('is-visible');
                FitLogUtils.showToast('Ordem dos exercícios salva!', 'success');
            } else {
                FitLogUtils.showToast((data && data.error) || 'Não foi possível salvar a ordem.', 'danger');
            }
        } catch (err) {
            FitLogUtils.showToast('Não foi possível salvar a ordem.', 'danger');
        } finally {
            btnSalvar.disabled = false;
            btnSalvar.innerHTML = textoOriginal;
        }
    }
});