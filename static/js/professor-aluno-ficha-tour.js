/**
 * professor-aluno-ficha-tour.js -- Tour guiado da ficha de um aluno, vista pelo
 * professor (templates/professor/visualizar_aluno.html). Usa o motor
 * static/js/fl-tour-core.js (Driver.js local) e o tema css/registrar-treino-tour.css.
 *
 * Passeio único ("pagina"): perfil, Voltar, Ver Versões, Nova versão,
 * ações de admin, atalhos (Estatísticas, Calendário) e últimos registros.
 * Passos cujo elemento não existe (ex.: "Nova versão" quando já há versão
 * ativa, ou ações de admin para professor comum) são ignorados pelo motor.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    function passos() {
        return [
            {
                element: '.va-profile-card',
                popover: {
                    title: 'Ficha do aluno',
                    description: 'Nome, situação (<b>Ativo</b> ou <b>Inativo</b>) e contato do aluno, '
                        + 'além de desde quando ele está na plataforma.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.va-actions-pair .va-btn-ghost',
                popover: {
                    title: 'Voltar',
                    description: 'Volta para a lista dos seus alunos.',
                    side: 'bottom', align: 'start'
                }
            },
            {
                element: '.va-actions-pair .va-btn-solid',
                popover: {
                    title: 'Versões de treino',
                    description: 'Abre as <b>versões</b> do treino deste aluno: a ativa e o histórico. '
                        + 'É por lá que você monta e edita os treinos dele.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '.va-actions > a.va-btn-ghost',
                popover: {
                    title: 'Nova versão',
                    description: 'Aparece quando o aluno <b>não tem versão ativa</b>. '
                        + 'Cria a próxima fase de treino para ele.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '.va-actions .btn-group',
                popover: {
                    title: 'Gerenciar o aluno',
                    description: 'Só para administradores: <b>editar</b> os dados e <b>desativar</b> ou '
                        + '<b>reativar</b> o acesso do aluno.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '.dash-quick-tile[href*="estatisticas"]',
                popover: {
                    title: 'Estatísticas',
                    description: 'Volume, recordes e desempenho por treino do aluno, com filtro de período.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '.dash-quick-tile[href*="calendario"]',
                popover: {
                    title: 'Calendário',
                    description: 'Os dias em que ele treinou. Toque em um dia para ver o que foi feito.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['.card:has(.bi-clock-history) .dash-registro-item', '.card:has(.bi-clock-history) .card-header'],
                popover: {
                    title: 'Últimos registros',
                    description: 'Abaixo ficam os exercícios que o aluno registrou por último, com data, treino, '
                        + 'carga e repetições. Dá para ver de relance se ele está seguindo o plano.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'professor-aluno-ficha',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        tour.ligarBotao('btnTourAlunoFicha', 'pagina');
        if (document.querySelector('.va-profile-card')) {
            tour.iniciarAposAtraso('pagina', 1200);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
