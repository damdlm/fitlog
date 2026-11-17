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

    function etvGuardarExcedentes() {
        if (etvMaterializado) return;
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
    // Recebe opcionalmente a ordem REAL e salva do treino (a mesma que
    // aparece no card da lista de exercícios e no recurso de arrastar-
    // -para-reordenar) -- sem isso, cairia na ordem em que os itens
    // aparecem no DOM no momento, que pode ficar inconsistente: nem
    // todo exercício do catálogo (~1300 itens) fica materializado de
    // cara (ver etvMaterializarPorIds acima), então um exercício do
    // treino que precisou ser materializado na hora aparece na posição
    // certa, mas outro que já estava no DOM (materializado em ordem
    // alfabética do catálogo) aparece na posição alfabética -- uma
    // mistura das duas ordens, dependendo de detalhe incidental de
    // quais exercícios já estavam ou não no lote inicial.
    function reordenarSelecionados(ordemIds) {
        if (!grid) return;
        // Só move os SELECIONADOS (tipicamente uma dúzia, no máximo) pro
        // início -- os não-selecionados (podem ser ~1300, o catálogo
        // inteiro) nunca são tocados, já estão na posição certa entre
        // si. Antes, a função reinseria TODOS os itens da grade, um por
        // um (inclusive os que não precisavam mudar de lugar): rodando
        // tanto no carregamento da página quanto toda vez que o modal
        // "Editar" abre, isso pesava bastante -- prepend() com múltiplos
        // nós faz o navegador mover só o que precisa, numa operação só.
        let selecionados = itens().filter(item => {
            const cb = item.querySelector('.etv-checkbox');
            return cb && cb.checked;
        });
        if (!selecionados.length) return;
        if (ordemIds && ordemIds.length) {
            const posicao = new Map(ordemIds.map((id, i) => [id, i]));
            selecionados = selecionados.slice().sort(function (a, b) {
                const pa = posicao.has(a.dataset.valor) ? posicao.get(a.dataset.valor) : Infinity;
                const pb = posicao.has(b.dataset.valor) ? posicao.get(b.dataset.valor) : Infinity;
                return pa - pb;
            });
        }
        grid.prepend(...selecionados);
    }

    // cadastrar-treinos.js reaproveita este grid num modal compartilhado
    // entre vários treinos; quando ele marca os checkboxes de um treino
    // específico ao abrir o modal, dispara este evento pra reordenar de
    // novo (não dá pra chamar reordenarSelecionados() direto, ela é
    // local a este closure). detail.ordemIds, quando informado, é a
    // ordem real e salva do treino (ver comentário acima).
    grid?.addEventListener('etv:reordenar', function (e) {
        ultimaOrdemIds = e.detail?.ordemIds || null;
        reordenarSelecionados(ultimaOrdemIds);
    });

    // -----------------------------------------------------
    // Filtro (texto + músculo)
    // -----------------------------------------------------
    // Busca (T3): cada palavra digitada precisa aparecer no nome, nos
    // apelidos ou no músculo, em qualquer ordem ("extensao perna",
    // "cadeira extensora"), e os resultados vêm por relevância -- nome ou
    // apelido igual ao termo primeiro (FitLogUtils.pontuarBusca). Limpar a
    // busca devolve a ordem original do catálogo (data-i), com os
    // exercícios marcados no topo, na ordem salva do treino.
    const U = window.FitLogUtils || {};
    const normalizarBusca = U.normalizarBusca || function (t) { return normalizarTexto((t || '').toLowerCase()).trim(); };
    let ordenadoPorBusca = false;
    let ultimaOrdemIds = null;

    function dadosBusca(item) {
        if (!item._busca) {
            item._busca = {
                nome: normalizarBusca(item.dataset.nome || ''),
                apelidos: (item.dataset.apelidos || '').split('|').filter(Boolean).map(normalizarBusca),
                musculo: normalizarBusca(item.dataset.musculo || ''),
                ordem: item.dataset.i !== undefined ? Number(item.dataset.i) : -1
            };
        }
        return item._busca;
    }

    function restaurarOrdemOriginal() {
        const todos = itens().sort(function (a, b) { return dadosBusca(a).ordem - dadosBusca(b).ordem; });
        const frag = document.createDocumentFragment();
        todos.forEach(function (c) { frag.appendChild(c); });
        grid.appendChild(frag);
        ordenadoPorBusca = false;
        reordenarSelecionados(ultimaOrdemIds);
    }

    function filtrar() {
        const termo = normalizarBusca(busca?.value || '');
        if (termo) etvMaterializarTodos();
        let visiveis = 0;
        const achados = [];

        itens().forEach(item => {
            const musculo = item.dataset.musculo || '';
            let mostrar = true;
            let nota = 0;

            if (termo) {
                const d = dadosBusca(item);
                nota = U.pontuarBusca ? U.pontuarBusca(termo, d.nome, d.apelidos, d.musculo)
                    : ((d.nome + ' ' + d.apelidos.join(' ')).includes(termo) ? 0 : null);
                if (nota === null) mostrar = false;
            }
            if (musculoAtivo && musculo !== musculoAtivo) mostrar = false;

            item.classList.toggle('d-none', !mostrar);
            if (mostrar) {
                visiveis++;
                if (termo) achados.push({ item: item, nota: nota });
            }
        });

        if (termo && achados.length) {
            achados.sort(function (a, b) {
                return (a.nota - b.nota)
                    || (dadosBusca(a.item).nome.length - dadosBusca(b.item).nome.length)
                    || (dadosBusca(a.item).ordem - dadosBusca(b.item).ordem);
            });
            grid.prepend(...achados.map(function (a) { return a.item; }));
            ordenadoPorBusca = true;
        } else if (!termo && ordenadoPorBusca) {
            restaurarOrdemOriginal();
        }

        if (semResultados) {
            // Lista ainda chegando (ou falhou): o aviso de lá já explica.
            semResultados.classList.toggle('d-none', visiveis !== 0 || !catalogoPronto);
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

    // Prepara os cards que estão na grade: guarda o excedente (ver acima)
    // e liga o 'change' dos que ficaram no DOM. Roda uma vez -- no
    // carregamento da página quando os cards vêm no HTML, ou quando a
    // lista do catálogo chega (carregarCatalogo, abaixo).
    function etvPrepararGrade() {
        etvGuardarExcedentes();
        checkboxes().forEach(cb => {
            cb.addEventListener('change', () => onCheckboxChange(cb));
        });
    }

    // -----------------------------------------------------
    // Catálogo sob demanda
    // -----------------------------------------------------
    // Nas fichas (cadastrar_treinos.html / ver_versao.html) o grid vem
    // vazio, com data-catalogo-url: são ~1.350 exercícios (~4,5 MB de
    // HTML) que só servem quando o modal "Editar treino" abre. A lista é
    // buscada em segundo plano logo depois que a página termina de
    // carregar, e cadastrar-treinos.js espera por ela antes de abrir o
    // modal (window.FitLogCatalogoEtv.carregar). Sem data-catalogo-url
    // (tela antiga do professor), os cards vêm no HTML como antes.
    const catalogoUrl = grid?.dataset.catalogoUrl || '';
    let catalogoPromessa = null;
    let catalogoPronto = !catalogoUrl;

    function mostrarErroCatalogo() {
        const aviso = grid?.querySelector('[data-etv-carregando]');
        if (!aviso) return;
        aviso.classList.add('is-erro');
        aviso.innerHTML = 'Não foi possível carregar os exercícios.' +
            ' <button type="button" class="btn btn-link btn-sm p-0 ms-1" data-etv-recarregar>Tentar de novo</button>';
    }

    function carregarCatalogo() {
        if (catalogoPronto) return Promise.resolve();
        if (catalogoPromessa) return catalogoPromessa;
        catalogoPromessa = fetch(catalogoUrl, { credentials: 'same-origin' })
            .then(function (resp) {
                // redirected: sessão expirada (login) ou acesso bloqueado
                // -- nunca colocar uma página inteira dentro da grade.
                if (!resp.ok || resp.redirected) throw new Error('HTTP ' + resp.status);
                return resp.text();
            })
            .then(function (html) {
                grid.innerHTML = html;
                catalogoPronto = true;
                etvPrepararGrade();
                atualizarContador();
                filtrar();
                grid.dispatchEvent(new CustomEvent('etv:carregado'));
            })
            .catch(function (err) {
                catalogoPromessa = null;
                mostrarErroCatalogo();
                throw err;
            });
        return catalogoPromessa;
    }

    window.FitLogCatalogoEtv = {
        carregar: carregarCatalogo,
        pronto: function () { return catalogoPronto; }
    };

    grid?.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-etv-recarregar]');
        if (!btn) return;
        e.preventDefault();
        const aviso = grid.querySelector('[data-etv-carregando]');
        if (aviso) {
            aviso.classList.remove('is-erro');
            aviso.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Carregando exercícios…';
        }
        carregarCatalogo().catch(function () {});
    });

    if (catalogoUrl) {
        // Busca em segundo plano, sem disputar com o carregamento da tela.
        const preCarregar = function () { carregarCatalogo().catch(function () {}); };
        const agendar = function () {
            if ('requestIdleCallback' in window) {
                window.requestIdleCallback(preCarregar, { timeout: 3000 });
            } else {
                window.setTimeout(preCarregar, 1000);
            }
        };
        if (document.readyState === 'complete') agendar();
        else window.addEventListener('load', agendar, { once: true });
    } else {
        etvPrepararGrade();
    }

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

    // -----------------------------------------------------
    // Empilhamento de modais -- o Bootstrap não lida sozinho com um
    // modal aberto por cima de outro já aberto (o segundo backdrop
    // fica atrás do primeiro modal). Sobe o z-index do modal/backdrop
    // mais recente sempre que já existe algum aberto.
    // -----------------------------------------------------
    document.addEventListener('show.bs.modal', function (e) {
        const abertos = document.querySelectorAll('.modal.show').length;
        if (abertos === 0) return;
        const zBase = 1055 + (abertos * 20);
        e.target.style.zIndex = String(zBase + 10);
        setTimeout(function () {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            const topo = backdrops[backdrops.length - 1];
            if (topo) topo.style.zIndex = String(zBase + 5);
        }, 0);
    });

    // -----------------------------------------------------
    // Criar novo exercício direto do modal (botão "+ Novo" ao lado da
    // busca) -- via API, sem sair da tela, e já injeta o card recém-
    // criado no topo da grade, marcado e pronto pra usar no treino.
    // -----------------------------------------------------
    const modalNovoExEl = document.getElementById('modalCriarExercicio');
    if (modalNovoExEl && window.bootstrap) {
        const nomeInput = document.getElementById('novoExercicioNome');
        const musculoSelect = document.getElementById('novoExercicioMusculo');
        const descricaoInput = document.getElementById('novoExercicioDescricao');
        const erroBox = document.getElementById('novoExercicioErro');
        const btnSalvar = document.getElementById('novoExercicioSalvar');
        const modalNovoEx = new bootstrap.Modal(modalNovoExEl);

        function novoExercicioLimpar() {
            if (nomeInput) nomeInput.value = '';
            if (descricaoInput) descricaoInput.value = '';
            if (musculoSelect) musculoSelect.selectedIndex = 0;
            erroBox?.classList.add('d-none');
            if (erroBox) erroBox.textContent = '';
        }
        function novoExercicioErro(msg) {
            if (!erroBox) return;
            erroBox.textContent = msg;
            erroBox.classList.remove('d-none');
        }

        // "+ Novo" abre por JS, não por data-bs-toggle: o atalho do
        // Bootstrap 5.3 fecha o modal aberto antes de abrir outro -- o
        // "Editar treino" sumia e o exercício criado (já marcado na grade)
        // ficava fora do treino. Aberto assim, ele empilha por cima (ver
        // "Empilhamento de modais" acima) e o de baixo continua aberto.
        document.querySelectorAll('[data-etv-novo]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                modalNovoEx.show(btn);
            });
        });

        modalNovoExEl.addEventListener('hidden.bs.modal', function () {
            novoExercicioLimpar();
            // Fechar o modal de cima faz o Bootstrap liberar a rolagem da
            // página, mesmo com o "Editar treino" ainda aberto embaixo.
            if (document.querySelector('.modal.show')) {
                document.body.classList.add('modal-open');
                document.body.style.overflow = 'hidden';
            }
        });
        modalNovoExEl.addEventListener('shown.bs.modal', function () { nomeInput?.focus(); });

        function montarCardNovoExercicio(id, nome, musculo) {
            const valor = 'u_' + id;
            const card = document.createElement('label');
            card.className = 'etv-card';
            card.setAttribute('for', 'ex_usuario_' + id);
            card.dataset.nome = nome.toLowerCase();
            card.dataset.nomeDisplay = nome;
            card.dataset.musculo = musculo;
            card.dataset.valor = valor;
            card.innerHTML =
                '<input class="etv-checkbox" type="checkbox" name="exercicios[]" value="' + valor + '" id="ex_usuario_' + id + '">' +
                '<div class="etv-card-body">' +
                    '<div class="etv-card-nome">' + nome + '</div>' +
                    '<div class="etv-card-row2">' +
                        '<span class="badge etv-card-musculo">' + musculo + '</span>' +
                        '<button type="button" class="etv-obs-toggle" title="Adicionar observação" ' +
                            'onclick="event.preventDefault(); event.stopPropagation(); this.closest(\'.etv-card\').classList.toggle(\'etv-obs-open\');">' +
                            'Observação <i class="bi bi-chevron-down"></i>' +
                        '</button>' +
                    '</div>' +
                    '<input type="text" class="etv-obs-input" name="observacao_' + valor + '" maxlength="60" ' +
                        'placeholder="Observação (opcional)" value="" onclick="event.stopPropagation()" disabled>' +
                '</div>' +
                '<span class="etv-tipo-badge" title="Exercício personalizado"><i class="bi bi-person-fill"></i></span>';
            return card;
        }

        if (btnSalvar) {
            btnSalvar.addEventListener('click', async function () {
                const nome = (nomeInput?.value || '').trim();
                if (!nome) {
                    novoExercicioErro('Digite o nome do exercício.');
                    nomeInput?.focus();
                    return;
                }
                const musculo = musculoSelect?.value || 'Outros';
                const descricao = (descricaoInput?.value || '').trim();

                btnSalvar.disabled = true;
                const textoOriginal = btnSalvar.innerHTML;
                btnSalvar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Salvando...';

                try {
                    const resp = await window.FitLogUtils.apiCall('/api/criar-exercicio', 'POST', {
                        nome, musculo, descricao
                    });
                    if (resp && resp.success) {
                        // Com o catálogo sob demanda, a lista pode chegar
                        // depois -- e já trazendo o exercício recém-criado.
                        // Espera por ela e reaproveita o card se ele veio.
                        await carregarCatalogo().catch(function () {});
                        etvMaterializarPorIds(['u_' + resp.id]);
                        let card = grid?.querySelector('.etv-card[data-valor="u_' + resp.id + '"]');
                        if (!card) {
                            card = montarCardNovoExercicio(resp.id, nome, musculo);
                            grid?.prepend(card);
                            etvPrepararCardNovo(card);
                        }
                        const cb = card.querySelector('.etv-checkbox');
                        if (cb) {
                            cb.checked = true;
                            onCheckboxChange(cb);
                        }
                        atualizarContador();
                        filtrar();
                        if (window.FitLogUtils?.showToast) {
                            window.FitLogUtils.showToast('Exercício criado e adicionado!', 'success');
                        }
                        modalNovoEx.hide();
                        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    } else {
                        novoExercicioErro((resp && resp.error) || 'Não foi possível criar o exercício.');
                    }
                } catch (err) {
                    novoExercicioErro('Erro de conexão. Tente novamente.');
                } finally {
                    btnSalvar.disabled = false;
                    btnSalvar.innerHTML = textoOriginal;
                }
            });
        }
    }

    // Estado inicial
    atualizarContador();
    filtrar();
    reordenarSelecionados();
});