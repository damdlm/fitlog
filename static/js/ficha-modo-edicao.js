/* ==========================================================
   Ficha ativa: sempre em edição e nome editável no próprio título.

   templates/aluno/ver_versao.html serve a ficha ativa ("Cadastrar
   treinos"), qualquer ficha de "Minhas fichas" e a ficha do aluno vista
   pelo professor. Na ficha ativa o servidor já põe .is-editando em
   #ctFicha, então os controles .ct-so-edicao (editar e excluir treino,
   arrastar, adicionar treino, finalizar) aparecem direto -- não existe
   mais o botão "Editar ficha". Na ficha finalizada eles ficam escondidos.

   O nome da ficha é um campo no próprio título (#ctTituloInput), com o
   botão ✓ (#ctTituloSalvar) ao lado: ele só fica ativo quando o nome
   muda e não está vazio; Esc desfaz a mudança; Enter salva.

   window.FitLogFicha = { editavel(), editando(), definir(ligado) }
   -- mantido para o tutorial e outros scripts que consultam o modo.
   ========================================================== */
(function () {
    'use strict';

    var ficha = document.getElementById('ctFicha');
    if (!ficha) return;

    var editavel = ficha.getAttribute('data-editavel') === '1';

    function definir(ligado) {
        ficha.classList.toggle('is-editando', !!ligado && editavel);
    }

    definir(editavel);

    // ---------- nome da ficha no título ----------
    var form = document.getElementById('ctTituloForm');
    var input = document.getElementById('ctTituloInput');
    var salvar = document.getElementById('ctTituloSalvar');

    if (form && input && salvar) {
        var original = input.getAttribute('data-original') || input.value;
        var enviando = false;

        var ajustarLargura = function () {
            // Fallback de field-sizing: content (navegadores sem suporte).
            input.size = Math.max((input.value || '').length, 4);
        };

        var mudou = function () {
            var valor = input.value.trim();
            return !!valor && valor !== original.trim();
        };

        var atualizar = function () {
            salvar.disabled = enviando || !mudou();
            ajustarLargura();
        };

        input.addEventListener('input', atualizar);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                input.value = original;
                atualizar();
                input.blur();
            }
        });
        form.addEventListener('submit', function (e) {
            // Reenvio feito pelo page-transition.js (ele cancela o 1º
            // submit, mostra a película e chama requestSubmit): deixa passar.
            if (form.dataset.flTransitionArmed) return;
            if (enviando || !mudou()) {
                // Enter sem mudança (ou 2º toque no ✓): não recarrega à toa.
                e.preventDefault();
                return;
            }
            enviando = true;
            salvar.setAttribute('aria-busy', 'true');
        });

        atualizar();
    }

    window.FitLogFicha = {
        editavel: function () { return editavel; },
        editando: function () { return ficha.classList.contains('is-editando'); },
        definir: definir
    };
})();
