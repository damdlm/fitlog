/**
 * ver-versao-tour.js -- Product tour da tela de uma VERSÃO de treino
 * (templates/aluno/ver_versao.html). A mesma tela é usada pelo aluno
 * (nas próprias versões) e pelo professor (editando a versão de um aluno),
 * por isso o texto muda conforme data-contexto="professor" no <script>.
 * Driver.js servido localmente em static/vendor/driverjs/; o tema vem de
 * css/registrar-treino-tour.css (compartilhado com os outros tours).
 *
 * Dois passeios, um por momento da tela:
 *   1) "lista": resumo da versão e cartões de treino. Os passos mudam
 *      se a versão está ATIVA (editável) ou FINALIZADA (só Clonar/Excluir).
 *   2) "modal": janela de montar/editar o treino (nome, busca, exercícios).
 *
 * Cada passeio abre sozinho só na primeira vez (flag no localStorage,
 * separada por usuário) e pode ser reaberto pelos botões "Tutorial"
 * (#btnTourVersaoLista e #btnTourVersaoModal).
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Excluir", "Salvar treino") dispare a ação de verdade no tour.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;
    // Professor editando a versão de um aluno (texto em 3ª pessoa).
    var doProfessor = (scriptEl && scriptEl.getAttribute('data-contexto')) === 'professor';

    // ---------- passos ----------
    function passosLista() {
        return [
            {
                element: '.ct-hero',
                popover: {
                    title: 'Resumo da versão',
                    description: 'Uma versão é uma fase do treino ' + (doProfessor ? 'do aluno' : 'que você segue')
                        + '. Aqui ficam o nome, se está <b>Ativa</b> ou <b>Finalizada</b>, o início, '
                        + 'quantos treinos e quantos exercícios ela tem.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '.ct-hero-desc-edit',
                popover: {
                    title: 'Editar a versão',
                    description: 'Muda o nome da versão e permite <b>finalizá-la</b> quando essa fase '
                        + 'acabar. Finalizada, ela vira histórico e pode ser clonada.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-hero-actions .btn-outline-primary',
                popover: {
                    title: 'Clonar a versão',
                    description: 'Cria uma nova versão ativa com os mesmos treinos e exercícios. '
                        + 'Só dá para clonar se não houver outra versão ativa ' + (doProfessor ? 'para o aluno.' : 'no momento.'),
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-hero-actions .btn-outline-danger',
                popover: {
                    title: 'Excluir a versão',
                    description: 'Só é possível se nenhum treino dela já foi registrado. '
                        + 'O app pede confirmação antes de apagar.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                // Só o cabeçalho do cartão: o cartão inteiro cresce com a
                // lista de exercícios e passaria da altura da tela.
                element: '.ct-treino-card .ct-treino-top',
                popover: {
                    title: 'Um cartão por treino',
                    description: 'Cada treino (A, B, C...) mostra o nome e quantos exercícios '
                        + 'tem, com a lista deles logo abaixo. Treino sem exercício '
                        + 'aparece em vermelho.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '.ct-treino-card .ct-btn-editar-exercicios',
                popover: {
                    title: 'Editar o treino',
                    description: 'Abre a janela para mudar o nome do treino e marcar ou '
                        + 'desmarcar exercícios.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '.ct-treino-card .ct-btn-excluir-treino',
                popover: {
                    title: 'Excluir o treino',
                    description: 'Remove o treino e seus exercícios desta versão, com confirmação. '
                        + 'Se o treino já foi registrado alguma vez, a remoção é bloqueada '
                        + 'para não perder o histórico.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '.ct-treino-card .ct-ex-drag-handle',
                popover: {
                    title: 'Reordene os exercícios',
                    description: 'Segure esta alça e arraste o exercício para mudar a ordem. '
                        + 'Quando mexer, aparece o botão <b>Salvar ordem</b>.',
                    side: 'bottom',
                    align: 'start'
                }
            },
            {
                element: '.ct-add-treino-btn',
                popover: {
                    title: 'Adicionar treino',
                    description: 'Cria o próximo treino da versão (B, C...). '
                        + 'O contador mostra quantos já existem e o limite.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    function passosModal() {
        return [
            {
                element: '#ctInputNome',
                popover: {
                    title: 'Nome do treino',
                    description: 'Dê um nome que facilite achar depois, como "Peito e tríceps".',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#etvSearchWrap',
                popover: {
                    title: 'Buscar exercício',
                    description: 'Digite parte do nome (ou um apelido) para filtrar a lista.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#modalExercicios .etv-btn-novo',
                popover: {
                    title: 'Não achou? Crie o seu',
                    description: 'Cadastre um exercício personalizado e ele entra na lista '
                        + 'para você marcar.',
                    side: 'bottom',
                    align: 'end'
                }
            },
            {
                element: '#etvGrid .etv-card',
                popover: {
                    title: 'Marque os exercícios',
                    description: 'Toque no cartão para incluir o exercício no treino. '
                        + 'Toque de novo para tirar.',
                    side: 'top',
                    align: 'center'
                }
            },
            {
                element: '#etvGrid .etv-obs-toggle',
                popover: {
                    title: 'Observação',
                    description: 'Quer lembrar de algo, como "pegada fechada"? '
                        + 'Abra e escreva uma observação curta para este exercício.',
                    side: 'top',
                    align: 'start'
                }
            },
            {
                element: '#etvGrid .etv-video-btn:not([disabled])',
                popover: {
                    title: 'Veja a execução',
                    description: 'O botão de play abre a demonstração em GIF ou vídeo '
                        + 'do exercício.',
                    side: 'left',
                    align: 'center'
                }
            },
            {
                element: '#modalExercicios .etv-footer-bar',
                popover: {
                    title: 'Salvar o treino',
                    description: 'Acompanhe quantos exercícios marcou e toque em <b>Salvar treino</b> '
                        + 'para gravar. <b>Cancelar</b> descarta as mudanças.',
                    side: 'top',
                    align: 'center'
                }
            }
        ];
    }

    var tour = window.FlTour.criar({
        tela: 'ver-versao',
        scriptEl: scriptEl,
        fasesModal: ['modal'],
        passos: {
            lista: passosLista,
            modal: passosModal
        }
    });

    function init() {
        tour.ligarBotao('btnTourVersaoLista', 'lista');
        tour.ligarBotao('btnTourVersaoModal', 'modal');

        var modal = document.getElementById('modalExercicios');
        if (modal) {
            // Primeira vez que abre a janela de montar o treino: o passeio
            // do modal abre sozinho quando a lista de exercícios já existe.
            modal.addEventListener('shown.bs.modal', function () {
                tour.iniciarAposAtraso('modal', 350, function () {
                    return !!document.querySelector('#modalExercicios .modal-body');
                });
            });
            modal.addEventListener('hide.bs.modal', tour.destruir);
        }

        if (document.querySelector('.ct-hero')) {
            // Espera o loader e a transição de página terminarem.
            tour.iniciarAposAtraso('lista', 900);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
