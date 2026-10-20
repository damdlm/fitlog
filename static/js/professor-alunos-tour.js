/**
 * professor-alunos-tour.js -- Product tour da tela "Gerenciar Alunos"
 * (professor). Driver.js servido localmente em static/vendor/driverjs/;
 * o tema vem de css/registrar-treino-tour.css (compartilhado com os
 * outros tours do app).
 *
 * Abre sozinho só na primeira vez (flag no localStorage, separada por
 * usuário) e pode ser reaberto pelo botão "Tutorial" (#btnTourProfessorAlunos).
 *
 * A tela tem duas versões da lista (tabela no desktop, cartões no
 * celular) e só uma fica visível por vez. Por isso os passos sobre o
 * aluno procuram o primeiro elemento VISÍVEL de cada seletor.
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Novo Aluno") dispare a ação de verdade durante o tour.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    var usuarioId = (scriptEl && scriptEl.getAttribute('data-user-id')) || 'anon';

    // A versão anterior guardava a flag sem sufixo de fase. Quem já viu o
    // tour não deve vê-lo de novo por causa da migração.
    try {
        var legado = 'fitlog:tour:professor-alunos:v1:' + usuarioId;
        if (window.localStorage.getItem(legado) === '1') {
            window.localStorage.setItem(legado + ':pagina', '1');
        }
    } catch (e) { /* sem storage: ignora */ }

    // ---------- passos ----------
    function montarPassos() {
        var temAlunos = !!document.querySelector('.ga-aluno-item');
        var passos = [
            {
                element: '#gaAlertaSolicitacoes',
                popover: {
                    title: 'Pedidos de vínculo',
                    description: 'Este aviso aparece quando algum aluno pediu para ser seu aluno. '
                        + 'Toque em <b>Ver solicitações</b> para aceitar ou recusar.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#gaBusca',
                popover: {
                    title: 'Encontre um aluno',
                    description: 'Digite o nome, o usuário ou o e-mail e toque em <b>Filtrar</b>. '
                        + 'Útil quando a lista começa a crescer.',
                    side: 'bottom',
                    align: 'center'
                }
            }
        ];

        if (temAlunos) {
            passos.push(
                {
                    element: '.ga-aluno-item',
                    popover: {
                        title: 'Seus alunos',
                        description: 'Cada aluno vinculado a você aparece aqui, em ordem alfabética, '
                            + 'com contato e a data em que o vínculo começou.',
                        side: 'top',
                        align: 'center'
                    }
                },
                {
                    element: '.ga-registros',
                    popover: {
                        title: 'Treinos registrados',
                        description: 'Quantos treinos o aluno já registrou. Dá para ver de relance '
                            + 'quem está treinando e quem sumiu.',
                        side: 'top',
                        align: 'center'
                    }
                },
                {
                    element: '.ga-btn-ver',
                    popover: {
                        title: 'Abrir o aluno',
                        description: 'Abre a ficha dele: versões de treino, estatísticas, calendário '
                            + 'e o que ele registrou.',
                        side: 'top',
                        align: 'end'
                    }
                },
                {
                    element: '.ga-btn-editar',
                    popover: {
                        title: 'Editar, desativar e reativar',
                        description: 'Ações de administrador: corrigir os dados do aluno e '
                            + 'desativar ou reativar o acesso dele.',
                        side: 'top',
                        align: 'center'
                    }
                }
            );
        }

        passos.push(
            {
                element: '#gaBtnSolicitacoes',
                popover: {
                    title: 'Solicitações',
                    description: 'Reúne os pedidos de alunos que querem treinar com você. '
                        + 'O número vermelho mostra quantos estão esperando resposta.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '#gaBtnNovoAluno',
                popover: {
                    title: 'Cadastrar um aluno novo',
                    description: 'Cria o acesso do aluno e já vincula a você. '
                        + 'Respeita o limite de alunos do seu plano.',
                    side: 'top',
                    align: 'center'
                }
            }
        );

        return passos;
    }

    var tour = window.FlTour.criar({
        tela: 'professor-alunos',
        scriptEl: scriptEl,
        passos: { pagina: montarPassos }
    });

    function init() {
        tour.ligarBotao('btnTourProfessorAlunos', 'pagina');
        // Espera o loader e a transição de página terminarem antes de abrir.
        if (document.getElementById('gaBusca')) tour.iniciarAposAtraso('pagina', 900);
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
