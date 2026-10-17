/**
 * index-tour.js -- Tour guiado da Tela inicial (templates/index.html).
 * Como a tela inicial é basicamente o ponto de partida do app, o passeio
 * apresenta a NAVEGAÇÃO (menu, registrar treino, sino, FitBot, perfil).
 * Usa o motor static/js/fl-tour-core.js (Driver.js local) e o tema
 * css/registrar-treino-tour.css.
 *
 * O menu muda conforme o dispositivo (barra inferior no celular, barra
 * superior no desktop) e conforme o perfil (aluno/professor). Cada passo
 * lista seletores alternativos e o motor usa o primeiro que estiver
 * visível; o que não existir para o perfil/dispositivo fica de fora.
 * data-contexto="professor" ajusta só o texto do passo do perfil.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    var doProfessor = (scriptEl && scriptEl.getAttribute('data-contexto')) === 'professor';

    function passos() {
        return [
            {
                element: ['.bottom-nav', '#navbarNav .navbar-nav', '.navbar-nav'],
                popover: {
                    title: 'Menu principal',
                    description: 'É por aqui que você navega pelo FitLog. Vamos ver os atalhos principais, um a um.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['.bottom-nav a[href*="calend"]', 'a.mega-trigger[title="Calendário"]'],
                popover: {
                    title: 'Calendário',
                    description: 'Veja os dias em que treinou, abra o que foi feito em cada um e corrija '
                        + 'um treino registrado.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['.bottom-nav-cta', '.btn-registrar-treino'],
                popover: {
                    title: 'Registrar treino',
                    description: 'O botão <b>+</b> abre o seu treino do dia para anotar cargas, '
                        + 'repetições e séries enquanto você treina.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['.bottom-nav a[href*="estatistica"]', 'a.mega-trigger[title="Estatísticas"]'],
                popover: {
                    title: 'Progresso e estatísticas',
                    description: 'Gráficos de volume, recordes e força para você enxergar a sua evolução.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['.bottom-nav button[data-bs-target="#offcanvasMais"]'],
                popover: {
                    title: 'Ajustes',
                    description: 'Abre o painel com o resto do menu: cadastrar treinos, '
                        + 'seus exercícios e o ranking.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: ['a.mega-trigger[title="Cadastrar Treinos"]'],
                popover: {
                    title: 'Cadastrar treinos',
                    description: 'Aqui você monta as versões do seu treino (A, B, C...) e escolhe os exercícios.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: ['a.mega-trigger[title="Meus Alunos"]'],
                popover: {
                    title: 'Meus alunos',
                    description: 'Lista dos seus alunos: veja o histórico, edite treinos e acompanhe cada um.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: ['a.mega-trigger[title="Solicitações"]'],
                popover: {
                    title: 'Solicitações',
                    description: 'Pedidos de novos alunos que querem treinar com você. O número vermelho indica quantos aguardam resposta.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '.fitbot-toggle-btn',
                popover: {
                    title: 'FitBot',
                    description: 'O assistente do FitLog: tire dúvidas sobre treino e sobre o app conversando com ele.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#notificacoesDropdownWrapper',
                popover: {
                    title: 'Notificações',
                    description: 'O sino avisa quando algo acontece, como mudanças no seu treino. '
                        + 'O número vermelho mostra quantas você ainda não leu.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#userMenuDropdownWrapper',
                popover: {
                    title: 'Seu perfil',
                    description: doProfessor
                        ? 'Seu perfil, assinatura e a sua página pública. No celular, aqui também ficam o Painel, os alunos e as solicitações.'
                        : 'Seu perfil, assinatura, professor e a opção de sair da conta.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '.home-tips',
                popover: {
                    title: 'Dicas de treino',
                    description: 'Dicas rápidas que se alternam sozinhas. Dá para arrastar o cartão pela tela se ele estiver atrapalhando.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'inicio',
        scriptEl: scriptEl,
        passos: { pagina: passos }
    });

    function init() {
        // O cartão de dicas captura o ponteiro (arrastar); sem isto o toque
        // no botão seria engolido e o clique nunca chegaria.
        var btn = document.getElementById('btnTourInicio');
        if (btn) btn.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
        tour.ligarBotao('btnTourInicio', 'pagina');
        // Só a tela inicial de aluno/professor tem .home-stage (o admin vê só o átomo).
        if (document.querySelector('.home-stage')) {
            tour.iniciarAposAtraso('pagina', 1200);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
