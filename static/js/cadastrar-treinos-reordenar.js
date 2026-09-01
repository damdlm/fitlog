/* ==========================================================
   Cadastrar Treinos (aluno) / Ver Versão (aluno + professor
   editando em nome do aluno) — reordenar exercícios dentro de
   cada card de treino via drag-and-drop (SortableJS).

   Chama window.CT_REORDENAR_URL (embutido pelo template),
   recebe {versao_id, treino_codigo, nova_ordem} e persiste o
   campo `ordem` de VersaoExercicio.

   A URL muda conforme quem está editando:
   - aluno editando o próprio treino -> /api/reordenar-exercicios
     (routes/api_routes.py), ownership validada via
     VersaoService.get_by_id(versao_id, user_id=current_user.id)
   - professor editando o treino de um aluno vinculado ->
     /professor/aluno/<id>/reordenar-exercicios
     (routes/professor_routes.py:reordenar_exercicios_aluno),
     que valida a posse do ALUNO (não do professor logado) antes
     de reordenar -- usar o endpoint fixo aqui seria o mesmo bug
     que os outros *_aluno (salvar_treino_url, adicionar_treino_url
     etc.) já evitam: a versão pertence ao aluno, e buscar pelo
     ID do professor nunca encontra nada.

   Depende de:
   - SortableJS (carregado antes deste arquivo)
   - window.CT_VERSAO_ID e window.CT_REORDENAR_URL, embutidos pelo template
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
            // Força o SortableJS a usar a própria simulação de arraste
            // (baseada em toque/ponteiro) em vez do drag-and-drop nativo
            // HTML5 do navegador -- em boa parte dos navegadores/webviews
            // mobile, o nativo simplesmente não funciona bem (ou não
            // funciona) via toque, mesmo com a alça correta configurada.
            // Essa era provavelmente a causa de "não seleciona o
            // exercício" no celular.
            forceFallback: true,
            fallbackTolerance: 3,
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
            const url = window.CT_REORDENAR_URL || '/api/reordenar-exercicios';
            const data = await FitLogUtils.apiCall(url, 'POST', {
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