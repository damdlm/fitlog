/**
 * versoes-tour.js -- Tour guiado da lista de versões de treino
 * (templates/aluno/versoes.html), usada pelo aluno ("Minhas Versões") e pelo
 * professor ("Versões de <aluno>"). Usa o motor static/js/fl-tour-core.js
 * (Driver.js local) e o tema css/registrar-treino-tour.css.
 *
 * O texto muda com data-contexto="professor". Passos cujo elemento não existe
 * (ex.: "Nova versão" quando já há versão ativa, ou os cartões quando a lista
 * está vazia) são ignorados pelo motor.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    var doProfessor = (scriptEl && scriptEl.getAttribute('data-contexto')) === 'professor';

    function passos() {
        return [
            {
                element: '.v-empty-card',
                popover: {
                    title: 'Nenhuma versão ainda',
                    description: doProfessor
                        ? 'Este aluno ainda não tem versão de treino. Toque em <b>Criar versão</b> para montar a primeira.'
                        : 'Você ainda não tem versão de treino. Toque no botão para <b>criar a primeira</b> e montar os seus treinos.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '.v-voltar-btn',
                popover: {
                    title: 'Voltar',
                    description: doProfessor
                        ? 'Volta para a ficha do aluno.'
                        : 'Volta para a tela de Cadastrar treinos.',
                    side: 'bottom', align: 'start'
                }
            },
            {
                element: '.v-header a.btn:not(.v-voltar-btn)',
                popover: {
                    title: 'Nova versão',
                    description: 'Aparece quando não há nenhuma versão <b>ativa</b>. '
                        + 'Cria a próxima fase de treino'
                        + (doProfessor ? ' para o aluno.' : '.'),
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '.v-card',
                popover: {
                    title: 'Uma versão por cartão',
                    description: 'Cada cartão é uma fase do treino: número, nome, data de início e '
                        + 'quantos treinos ela tem. A mais recente fica no topo. '
                        + 'Toque no cartão para abrir' + (doProfessor ? ' e editar.' : '.'),
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.v-card .v-status-pill',
                popover: {
                    title: 'Ativa ou finalizada',
                    description: '<b>Ativa</b> é a versão em uso agora (só pode haver uma). '
                        + '<b>Finalizada</b> vira histórico: guarda o que foi feito e pode ser clonada '
                        + 'para começar uma nova fase.',
                    side: 'bottom', align: 'start'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'versoes',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourVersoes', 'pagina');
        if (document.querySelector('.v-header')) {
            tour.iniciarAposAtraso('pagina', 1200);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
