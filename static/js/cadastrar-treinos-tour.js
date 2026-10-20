/**
 * cadastrar-treinos-tour.js -- Product tour da tela "Cadastrar Treinos"
 * (Driver.js, servido localmente em static/vendor/driverjs/; o tema vem
 * de css/registrar-treino-tour.css, compartilhado com o tour de Registrar).
 *
 * Três passeios, um por momento da tela:
 *   1) "semversao": ainda não existe versão (formulário "Comece uma nova versão").
 *   2) "lista": versão em edição (resumo, cartões de treino, adicionar).
 *   3) "modal": janela de montar/editar o treino (nome, busca, exercícios).
 *
 * Cada passeio abre sozinho só na primeira vez (flag no localStorage,
 * separada por usuário) e pode ser reaberto pelos botões "Tutorial"
 * (#btnTourCadastrarSemVersao, #btnTourCadastrarLista, #btnTourCadastrarModal).
 *
 * Não mexe em nenhum fluxo da tela: só lê o DOM e desenha por cima.
 * disableActiveInteraction evita que um toque no elemento destacado
 * (ex: "Excluir", "Salvar treino") dispare a ação de verdade no tour.
 */
(function () {
    'use strict';
    if (!window.FlTour) return;

    var scriptEl = document.currentScript;

    // ---------- passos ----------
    function passosSemVersao() {
        return [
            {
                element: '#descricao',
                popover: {
                    title: 'Dê um nome à versão',
                    description: 'Uma versão é uma fase do seu treino (ex: "Hipertrofia - Agosto"). '
                        + 'Ela guarda seus treinos A, B, C... enquanto estiver valendo.',
                    side: 'bottom',
                    align: 'center'
                }
            },
            {
                element: '#validade_meses',
                popover: {
                    title: 'Validade (opcional)',
                    description: 'Se quiser, informe por quantos meses a versão vale e o FitLog '
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

    function passosLista() {
        return [
            {
                element: '.ct-hero',
                popover: {
                    title: 'Sua versão em edição',
                    description: 'Aqui está o resumo: início, quantos treinos e quantos '
                        + 'exercícios já foram cadastrados. Toque em <b>Editar</b> para mudar o nome '
                        + 'ou finalizar a versão.',
                    side: 'bottom',
                    align: 'center'
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
                    description: 'Remove o treino e seus exercícios desta versão. '
                        + 'O app pede confirmação antes de apagar.',
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
                        + 'O contador mostra quantos você já tem e o limite.',
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
        tela: 'cadastrar-treinos',
        scriptEl: scriptEl,
        fasesModal: ['modal'],
        passos: {
            semversao: passosSemVersao,
            lista: passosLista,
            modal: passosModal
        }
    });

    function init() {
        tour.ligarBotao('btnTourCadastrarSemVersao', 'semversao');
        tour.ligarBotao('btnTourCadastrarLista', 'lista');
        tour.ligarBotao('btnTourCadastrarModal', 'modal');

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

        if (document.getElementById('descricao')
            && document.querySelector('.ct-empty-form')) {
            tour.iniciarAposAtraso('semversao', 900);
        } else if (document.querySelector('.ct-hero')) {
            // Espera o loader e a transição de página terminarem.
            tour.iniciarAposAtraso('lista', 900);
        }
    }

    if (document.readyState === 'complete') init();
    else window.addEventListener('load', init);
})();
