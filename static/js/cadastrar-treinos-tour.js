/**
 * cadastrar-treinos-tour.js -- Product tour da tela "Cadastrar Treinos"
 * SEM ficha ativa (fichas prontas e "Montar do zero"). Driver.js servido
 * localmente em static/vendor/driverjs/; o tema vem de
 * css/registrar-treino-tour.css, compartilhado com os outros tours.
 *
 * Com ficha ativa, "Cadastrar Treinos" mostra a tela da ficha
 * (aluno/ver_versao.html, lote 6d) e o tutorial é o de ver-versao-tour.js.
 *
 * Abre sozinho só na primeira vez (flag no localStorage, separada por
 * usuário) e pode ser reaberto pelo botão #btnTourCadastrarSemVersao.
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    // ---------- passos ----------
    function passosSemVersao() {
        return [
            {
                // E2: só aparece quando há fichas prontas na tela
                element: '#fichasProntas .fp-card',
                popover: {
                    title: 'Comece com uma ficha pronta',
                    description: 'Escolha um modelo e toque em "Usar esta ficha": os treinos já vêm '
                        + 'com exercícios e metas. "Ver exercícios" mostra tudo antes, e depois '
                        + 'você troca o que quiser.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#descricao',
                popover: {
                    title: (document.getElementById('fichasProntas') ? 'Ou monte do zero: dê' : 'Dê') + ' um nome à ficha',
                    description: 'Uma ficha é uma fase do seu treino (ex: "Hipertrofia - Agosto"). '
                        + 'Ela guarda seus treinos A, B, C... enquanto estiver valendo.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#validade_meses',
                popover: {
                    title: 'Validade (opcional)',
                    description: 'Se quiser, informe por quantos meses a ficha vale e o FitLog '
                        + 'avisa quando estiver perto de vencer. Em branco, ela não tem prazo.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '.ct-empty-form button[type="submit"]',
                popover: {
                    title: 'Criar e começar',
                    description: 'A data de início é hoje. Depois de criar, você monta os '
                        + 'treinos e escolhe os exercícios de cada um.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'cadastrar-treinos',
        scriptEl: scriptEl,
        passos: { semversao: passosSemVersao }
    });

    function init() {
        tour.ligarBotao('btnTourCadastrarSemVersao', 'semversao');
        if (document.getElementById('descricao') && document.querySelector('.ct-empty-form')) {
            // Espera o loader e a transição de página terminarem.
            tour.iniciarAposAtraso('semversao', 900);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
