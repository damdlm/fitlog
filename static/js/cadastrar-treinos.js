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

    // Feedback leve de "carregando" no próprio botão clicado -- o loop
    // abaixo que marca os ~1300 checkboxes do treino escolhido é rápido
    // (linear, não trava de verdade), mas ainda assim é um trabalho
    // síncrono que roda bem no instante do toque; o spinner só evita a
    // sensação de "não registrou o clique" nesse intervalo curto. Não
    // tem relação com o crash de memória do Safari em iOS (esse já foi
    // corrigido à parte, na criação preguiçosa dos tooltips).
    //
    // Todos os cartões de treino compartilham o MESMO modal
    // (#modalExercicios), então existem duas corridas de tempo que
    // deixavam o botão preso no spinner pra sempre ("trava"), e em
    // alguns casos deixavam até o fundo escurecido do modal preso na
    // tela (parecendo um "erro" travando a página):
    //
    // 1) Clique duplo no mesmo botão: o Bootstrap, ao ser acionado de
    //    novo com o modal já aberto (via data-bs-toggle nativo), trata
    //    isso como TOGGLE e fecha o modal em vez de reabrir -- disparando
    //    'hide.bs.modal' e nunca 'show.bs.modal' (evento em que
    //    restaurávamos o botão).
    // 2) Cancelar e clicar em Editar de novo rápido: o clique cai
    //    ENQUANTO o modal ainda está no meio da animação de fechamento
    //    (~300ms) do Cancelar anterior. Bootstrap ignora silenciosamente
    //    um show() chamado nesse meio-tempo -- nem abre, nem dispara
    //    nenhum evento.
    //
    // Solução: parar de depender do data-bs-toggle automático do
    // Bootstrap pra esses botões (stopPropagation impede o listener
    // nativo dele de agir) e controlar a abertura manualmente aqui --
    // se o modal ainda estiver fechando, esperamos ele terminar
    // ('hidden.bs.modal') antes de reabrir com os dados do treino
    // clicado, em vez de tentar (e falhar) na hora.
    let modalFechando = false;
    modalExercicios.addEventListener('hide.bs.modal', function () {
        modalFechando = true;
    });

    // Página de transição já usada no resto do app (película escura +
    // loader), exposta por page-transition.js/base.html como
    // window.FitLogPageTransition -- reaproveitamos ela aqui em vez de
    // criar um overlay próprio.
    const transicao = window.FitLogPageTransition;

    document.querySelectorAll('.ct-btn-editar-exercicios').forEach(function (btn) {
        btn.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();

            if (btn.classList.contains('ct-is-loading')) return;
            btn.classList.add('ct-is-loading');
            btn.dataset.htmlOriginal = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Editar';

            // Mostra a transição já no clique (não só quando precisa
            // esperar o fechamento anterior) -- ela cobre tanto essa
            // espera quanto a própria animação de abertura do modal,
            // suavizando a troca em vez de deixar a tela "pular" direto
            // pro conteúdo.
            transicao?.show();

            const abrir = () => {
                const modalInstance = bootstrap.Modal.getOrCreateInstance(modalExercicios);
                if (modalInstance._isShown) {
                    // Já está aberto (ex: clique duplo no mesmo botão) --
                    // não há nada pra transicionar, e sem isso a película
                    // ficaria presa na tela, já que nem 'shown.bs.modal'
                    // nem 'hidden.bs.modal' disparariam de novo.
                    transicao?.hide();
                    return;
                }
                modalInstance.show(btn);
            };
            if (modalFechando) {
                // Ainda terminando de fechar (Cancelar/troca rápida de
                // treino) -- espera terminar antes de reabrir com os
                // dados deste botão, em vez de tentar na hora e falhar.
                modalExercicios.addEventListener('hidden.bs.modal', abrir, { once: true });
            } else {
                abrir();
            }
        });
    });

    // Esconde a transição assim que o modal termina de aparecer (fim da
    // animação de abertura).
    modalExercicios.addEventListener('shown.bs.modal', function () { transicao?.hide(); });

    // Mesma transição ao fechar (Cancelar ou o X do canto) -- cobre a
    // animação de fechamento, que é escondida de novo pela rede de
    // segurança de 'hidden.bs.modal' logo abaixo.
    modalExercicios.querySelectorAll('[data-bs-dismiss="modal"]').forEach(function (btn) {
        btn.addEventListener('click', function () { transicao?.show(); });
    });

    function restaurarBotoesEditar() {
        document.querySelectorAll('.ct-btn-editar-exercicios.ct-is-loading').forEach(function (btn) {
            if (btn.dataset.htmlOriginal) {
                btn.innerHTML = btn.dataset.htmlOriginal;
                delete btn.dataset.htmlOriginal;
            }
            btn.classList.remove('ct-is-loading');
        });
    }

    // Rede de segurança: não importa se o modal abriu de verdade, se foi
    // fechado por um toggle acidental, ou se algo no meio do caminho deu
    // erro -- assim que ele terminar de fechar, nenhum botão fica preso
    // no estado de "carregando".
    modalExercicios.addEventListener('hidden.bs.modal', function () {
        modalFechando = false;
        transicao?.hide();
        restaurarBotoesEditar();
    });


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

        // Marca/desmarca e sincroniza o visual (classe .is-selected, campo
        // de observação) direto, SEM disparar 'change' em cada checkbox.
        // A grade tem ~1300 itens (catálogo inteiro + personalizados);
        // disparar 'change' em todos fazia o listener de
        // editar-treino-versao.js recalcular o contador de selecionados
        // varrendo a grade inteira A CADA disparo -- ~1300 x ~1300 =
        // trabalho quadrático, travando a tela por um instante. Fazendo a
        // sincronização aqui direto (sem passar pelo sistema de eventos) e
        // recalculando o contador só 1 vez no final (evento 'etv:contador'
        // abaixo), o custo cai de quadrático pra linear.
        checkboxesDoGrid().forEach(function (cb) {
            const deveEstarMarcado = selecionados.has(cb.value);
            cb.checked = deveEstarMarcado;

            const card = cb.closest('.etv-card');
            if (card) card.classList.toggle('is-selected', deveEstarMarcado);

            const obsInput = card?.querySelector('.etv-obs-input');
            if (obsInput) {
                obsInput.disabled = !deveEstarMarcado;
                obsInput.value = deveEstarMarcado ? (observacoes[cb.value] || '') : '';
            }
        });

        // Recalcula o contador (1 vez só) e traz os exercícios já
        // marcados pra esse treino pro início da lista (ambos ouvidos em
        // editar-treino-versao.js).
        grid?.dispatchEvent(new CustomEvent('etv:contador'));
        grid?.dispatchEvent(new CustomEvent('etv:reordenar'));

        // Restaura o botão que abriu o modal ao estado normal -- o
        // spinner (ver listener de 'click' acima) já cumpriu seu papel.
        // (a rede de segurança em 'hidden.bs.modal' cobre os casos em
        // que este evento não dispara.)
        if (trigger.classList.contains('ct-btn-editar-exercicios')) {
            if (trigger.dataset.htmlOriginal) {
                trigger.innerHTML = trigger.dataset.htmlOriginal;
                delete trigger.dataset.htmlOriginal;
            }
            trigger.classList.remove('ct-is-loading');
        }
    });
});