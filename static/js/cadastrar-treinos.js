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
    const modalTitulo = document.getElementById('ctModalTitulo');
    const modalIcone = document.getElementById('ctModalIcone');
    const btnSalvarTexto = document.getElementById('ctBtnSalvarTexto');
    const busca = document.getElementById('etvBusca');
    const buscaWrap = document.getElementById('etvSearchWrap');
    const grid = document.getElementById('etvGrid');
    const chipTodos = document.querySelector('#etvChipsMusculo .etv-chip[data-musculo=""]');

    function checkboxesDoGrid() {
        return grid ? Array.from(grid.querySelectorAll('.etv-checkbox')) : [];
    }

    // "X" de limpar a busca só aparece quando tem texto digitado -- o
    // próprio botão (#etvLimparFiltro) e o filtro em si continuam sendo
    // tratados por editar-treino-versao.js, isso aqui é só o visual do
    // campo em si (classe .has-text no wrapper).
    busca?.addEventListener('input', function () {
        buscaWrap?.classList.toggle('has-text', busca.value.length > 0);
    });
    // limparFiltro() (editar-treino-versao.js) zera busca.value direto,
    // sem disparar 'input' -- sincroniza o visual aqui também.
    document.getElementById('etvLimparFiltro')?.addEventListener('click', function () {
        buscaWrap?.classList.remove('has-text');
    });

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

    // Rastreia se algo foi de fato alterado nesse treino desde que o
    // modal abriu, pra só pedir confirmação no Cancelar quando existir
    // algo real a perder. 'input'/'change' delegados no form pegam
    // nome, descrição, marcar/desmarcar exercício e campo de observação
    // de uma vez -- exceto a busca (#etvBusca), que é só filtro de
    // visualização, não uma alteração no treino. A sincronização
    // automática do 'show.bs.modal' (marcar os exercícios já salvos)
    // usa atribuição direta de .checked/.value, que não dispara esses
    // eventos -- então abrir o modal nunca marca como "sujo" sozinho.
    let modalSujo = false;
    form?.addEventListener('input', function (event) {
        if (event.target === busca) return;
        modalSujo = true;
    });
    form?.addEventListener('change', function (event) {
        if (event.target === busca) return;
        modalSujo = true;
    });

    // Página de transição já usada no resto do app (película escura +
    // loader), exposta por page-transition.js/base.html como
    // window.FitLogPageTransition -- reaproveitamos ela aqui em vez de
    // criar um overlay próprio.
    //
    // Importante: na navegação normal de página, essa película fica
    // visível por um tempo mínimo garantido (NAV_DELAY_MS) antes de
    // qualquer coisa acontecer -- sem isso, ela só ficava visível ~0,3s
    // (a duração da própria animação de abrir/fechar do Bootstrap), tempo
    // curto demais pra sequer completar seu próprio fade de 0,4s. Por
    // isso ela mal aparecia. Aplicamos o mesmo delay mínimo aqui.
    const transicao = window.FitLogPageTransition;
    const ATRASO_MINIMO_MS = transicao?.NAV_DELAY_MS ?? 400;

    document.querySelectorAll('.ct-btn-editar-exercicios').forEach(function (btn) {
        btn.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();

            if (btn.classList.contains('ct-is-loading')) return;
            btn.classList.add('ct-is-loading');
            btn.dataset.htmlOriginal = btn.innerHTML;
            const rotuloCarregando = btn.getAttribute('data-modo') === 'adicionar' ? 'Adicionar' : 'Editar';
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> ' + rotuloCarregando;

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
                // dados deste botão. A própria espera do fechamento
                // anterior (~0,3s) já dá tempo da película aparecer.
                modalExercicios.addEventListener('hidden.bs.modal', abrir, { once: true });
            } else {
                // Caso comum: dá tempo da película realmente aparecer
                // antes do modal se sobrepor a ela.
                window.setTimeout(abrir, ATRASO_MINIMO_MS);
            }
        });
    });

    // Esconde a transição assim que o modal termina de aparecer (fim da
    // animação de abertura).
    modalExercicios.addEventListener('shown.bs.modal', function () { transicao?.hide(); });

    // Mesma transição ao fechar (Cancelar ou o X do canto) -- assume
    // controle manual do fechamento (preventDefault/stopPropagation) pra
    // poder dar o mesmo tempo mínimo de tela escurecida antes do modal
    // sumir de fato.
    // Antes esses botões usavam data-bs-dismiss="modal" -- só que o
    // Bootstrap regista o próprio listener de fechamento no DOCUMENTO
    // INTEIRO na fase de CAPTURA (antes até do clique "descer" até o
    // botão), então ele sempre fechava o modal primeiro, não importa o
    // que a gente fizesse aqui (preventDefault/stopPropagation chegam
    // tarde demais pra evitar isso). Por isso os botões usam
    // data-etv-cancelar em vez de data-bs-dismiss -- assim o Bootstrap
    // nem tenta mexer neles, e o fechamento (com ou sem confirmação) é
    // 100% controlado por este código.
    modalExercicios.querySelectorAll('[data-etv-cancelar]').forEach(function (btn) {
        btn.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();

            // CORRIDA REAL (causava o crash "Um problema ocorreu
            // repetidamente" ao clicar Editar -> Cancelar -> Editar
            // rápido): modalFechando só virava true dentro do listener
            // de 'hide.bs.modal' acima, mas esse evento só dispara
            // quando bootstrap.Modal.hide() é chamado de fato -- e isso
            // só acontece DEPOIS do setTimeout de ATRASO_MINIMO_MS
            // (400ms) abaixo, não no instante do clique em Cancelar.
            // Ou seja, existia uma janela de até 400ms em que
            // modalFechando ainda estava false mesmo com o Cancelar já
            // clicado. Um clique em "Editar" nessa janela caía no ramo
            // "else" do listener de clique acima (agenda abrir() direto,
            // sem esperar), e o `_isShown` do Bootstrap já virava false
            // no instante em que hide() começa (antes da animação de
            // fechar terminar) -- então o guard "já está aberto?"
            // também não pegava. Resultado: show() era chamado enquanto
            // o hide() anterior ainda estava no meio da animação,
            // deixando o Bootstrap empilhar um backdrop/estado novo por
            // cima do antigo sem limpar o de antes. Repetindo o ciclo
            // editar/cancelar/editar, isso acumulava backdrops e
            // listeners de sobra até estourar a memória do Safari.
            // Marcando modalFechando=true JÁ AQUI (no clique, não no
            // hide.bs.modal 400ms depois), qualquer "Editar" nessa
            // janela cai no ramo que espera 'hidden.bs.modal' de
            // verdade antes de reabrir, fechando a corrida.
            const fecharDeVerdade = function () {
                modalFechando = true;

                transicao?.show();
                window.setTimeout(function () {
                    bootstrap.Modal.getInstance(modalExercicios)?.hide();
                }, ATRASO_MINIMO_MS);
            };

            if (!modalSujo || typeof window.FitLogConfirm !== 'function') {
                fecharDeVerdade();
                return;
            }

            window.FitLogConfirm({
                variant: 'warning',
                icon: 'bi-exclamation-triangle-fill',
                title: 'Descartar alterações?',
                text: 'Você fez alterações nesse treino que ainda não foram salvas.',
                confirmLabel: 'Descartar',
                onConfirm: fecharDeVerdade
            });
        });
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

        modalSujo = false;

        const modoAdicionar = trigger.getAttribute('data-modo') === 'adicionar';
        const treinoVersaoId = trigger.getAttribute('data-treino-versao-id') || '';
        const codigo = trigger.getAttribute('data-treino-codigo') || '';
        const nome = trigger.getAttribute('data-treino-nome') || '';
        const descricao = trigger.getAttribute('data-treino-descricao') || '';
        const action = trigger.getAttribute('data-action') || '';

        if (form && action) form.action = action;
        if (inputNome) inputNome.value = nome;
        if (inputDescricao) inputDescricao.value = descricao;
        if (modalCodigo) modalCodigo.textContent = modoAdicionar ? '' : codigo;

        // Mesmo modal servindo os dois fluxos (ver cadastrar_treinos.html):
        // só o texto/ícone do cabeçalho, o aviso da letra automática e o
        // rótulo do botão de salvar mudam -- nome/descrição/exercícios já
        // ficam vazios/desmarcados naturalmente no modo adicionar, porque
        // o botão "Adicionar treino" não tem os data-treino-* preenchidos.
        if (modalTitulo) modalTitulo.textContent = modoAdicionar ? 'Adicionar treino' : 'Editar treino';
        if (modalIcone) modalIcone.className = modoAdicionar ? 'bi bi-plus-circle me-2' : 'bi bi-pencil-square me-2';
        if (btnSalvarTexto) btnSalvarTexto.textContent = modoAdicionar ? 'Adicionar treino' : 'Salvar treino';

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

        // A grade grande (~1300 itens) só mantém uma parte no DOM por
        // padrão (ver editar-treino-versao.js) -- garante que os
        // exercícios já salvos NESTE treino existam de verdade antes do
        // loop abaixo tentar marcá-los.
        grid?.dispatchEvent(new CustomEvent('etv:garantir', { detail: { ids: Array.from(selecionados) } }));

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

            // Campo de observação vem fechado por padrão (mais compacto) --
            // só abre sozinho se este exercício já tinha uma observação
            // salva, pra ela não ficar escondida sem indicação nenhuma.
            if (card) card.classList.toggle('etv-obs-open', deveEstarMarcado && !!(observacoes[cb.value] || '').trim());
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