/**
 * calendario-tour.js -- Tour guiado da tela de Calendário
 * (templates/calendar/calendario.html). Usa o motor static/js/fl-tour-core.js
 * (Driver.js local) e o tema css/registrar-treino-tour.css.
 *
 * Três passeios, um por momento da tela:
 *   1) "pagina":   resumo do mês, compartilhar, tema, navegação, dias
 *                  treinados e gráfico de evolução.
 *   2) "detalhes": janela com o treino do dia (exercícios, séries, totais).
 *   3) "edicao":   janela de edição de um treino já registrado
 *                  (só existe para o próprio aluno).
 * O texto muda com data-contexto="professor" (professor vendo um aluno).
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    var doProfessor = (scriptEl && scriptEl.getAttribute('data-contexto')) === 'professor';

    function passosPagina() {
        return [
            {
                element: '#monthSummary',
                popover: {
                    title: 'Resumo do mês',
                    description: 'Mostra os <b>dias treinados</b>, a <b>sequência atual</b> de dias seguidos '
                        + 'e o <b>volume total</b> (kg) do mês que está na tela.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#btnCompartilharCalendario',
                popover: {
                    title: 'Compartilhar',
                    description: 'Gera uma imagem do calendário do mês para ' + (doProfessor ? 'enviar ao aluno ou guardar.' : 'você mandar para quem quiser.'),
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#themeToggle',
                popover: {
                    title: 'Tema claro ou escuro',
                    description: 'Troca o visual do calendário. Vale também para a imagem compartilhada.',
                    side: 'bottom', align: 'end'
                }
            },
            {
                element: '#calendar .fc-toolbar',
                popover: {
                    title: 'Mudar de mês',
                    description: 'As setas navegam entre os meses e <b>Hoje</b> volta para o mês atual. '
                        + 'No celular, deslizar o calendário para os lados também troca o mês.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: ['.fc-daygrid-day-number:has(.fc-day-dot)', '.fc-daygrid-event'],
                popover: {
                    title: 'Dias com treino',
                    description: 'Os dias em que ' + (doProfessor ? 'o aluno treinou' : 'você treinou')
                        + ' aparecem marcados. <b>Toque no dia</b> para ver o que foi feito.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#evolucaoWrap .dash-card-header',
                popover: {
                    title: 'Evolução',
                    description: 'O gráfico mostra a carga ao longo do tempo. Use os botões para ver '
                        + '<b>todos os treinos</b> ou só um deles (A, B, C...).',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '#evolucaoWrap .dash-chart-toolbar',
                popover: {
                    title: 'Por semana ou por treino',
                    description: '<b>Por semana</b> soma o período; <b>Por treino</b> compara cada treino registrado.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    function passosDetalhes() {
        return [
            {
                element: '#eventoDetalhes .grupo-treino-header',
                popover: {
                    title: 'O treino do dia',
                    description: 'Nome do treino e o volume total (kg) dele. Se houve mais de um treino no mesmo dia, '
                        + 'cada um aparece num bloco.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#eventoDetalhes .exercicio-card',
                popover: {
                    title: 'Exercícios',
                    description: 'Cada exercício realizado, com as séries registradas.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#eventoDetalhes .serie-chip',
                popover: {
                    title: 'Séries',
                    description: 'Cada etiqueta é uma série: <b>carga (kg) × repetições</b>.',
                    side: 'top', align: 'start'
                }
            },
            {
                element: '#eventoDetalhes .btn-editar-registro',
                popover: {
                    title: 'Editar este treino',
                    description: 'Corrija cargas, repetições, séries ou a data, mesmo que a versão '
                        + 'do treino já esteja finalizada.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '#eventoDetalhes .dia-total-strip',
                popover: {
                    title: 'Totais do dia',
                    description: 'Volume total levantado e o tempo de treino do dia.',
                    side: 'top', align: 'center'
                }
            }
        ];
    }

    function passosEdicao() {
        return [
            {
                element: '#editarRegistroData',
                popover: {
                    title: 'Data do treino',
                    description: 'Errou o dia? Mude a data aqui e o treino é movido no calendário.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#editarRegistroCorpo .editar-registro-card',
                popover: {
                    title: 'Carga, repetições e séries',
                    description: 'Ajuste a <b>carga</b>, as <b>repetições</b> e, com os botões − e +, '
                        + 'o número de <b>séries</b> do exercício.',
                    side: 'bottom', align: 'center'
                }
            },
            {
                element: '#editarRegistroCorpo .btn-abrir-series-modal-cal',
                popover: {
                    title: 'Série por série',
                    description: 'Quando as séries tiveram cargas ou repetições diferentes, '
                        + 'toque na seta para editar uma a uma.',
                    side: 'left', align: 'center'
                }
            },
            {
                element: '#editarRegistroBtnExcluir',
                popover: {
                    title: 'Excluir o registro',
                    description: 'Apaga este treino do dia, com confirmação. Não dá para desfazer.',
                    side: 'top', align: 'start'
                }
            },
            {
                element: '#modalEditarRegistro .modal-footer .btn-secondary',
                popover: {
                    title: 'Cancelar',
                    description: 'Fecha a janela sem alterar nada.',
                    side: 'top', align: 'center'
                }
            },
            {
                element: '#editarRegistroBtnSalvar',
                popover: {
                    title: 'Salvar',
                    description: 'Grava as mudanças no treino.',
                    side: 'top', align: 'end'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'calendario',
        scriptEl: scriptEl,
        fasesModal: ['detalhes', 'edicao'],
        passos: { pagina: passosPagina, detalhes: passosDetalhes, edicao: passosEdicao }
    });

    function ligarModal(idModal, fase, atraso) {
        var modal = document.getElementById(idModal);
        if (!modal) return;
        modal.addEventListener('shown.bs.modal', function () {
            tour.iniciarAposAtraso(fase, atraso);
        });
        modal.addEventListener('hide.bs.modal', tour.destruir);
    }

    function init() {
        tour.ligarBotao('btnTourCalendario', 'pagina');
        tour.ligarBotao('btnTourCalendarioDetalhes', 'detalhes');
        tour.ligarBotao('btnTourCalendarioEdicao', 'edicao');
        ligarModal('eventoModal', 'detalhes', 450);
        // O corpo da edição chega por fetch depois de abrir a janela.
        ligarModal('modalEditarRegistro', 'edicao', 900);

        if (document.getElementById('calendar')) {
            // Espera o loader, a transição de página e os eventos do mês.
            tour.iniciarAposAtraso('pagina', 1600);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();