/* ==========================================================
   Ficha: modo de leitura e modo de edição na mesma tela (lote 6d, T2).

   templates/aluno/ver_versao.html serve a ficha ativa ("Cadastrar
   treinos"), qualquer ficha de "Minhas fichas" e a ficha do aluno vista
   pelo professor. Na ficha ativa, o botão "Editar ficha" (#btnModoEdicao)
   liga a classe .is-editando em #ctFicha, que mostra os controles
   marcados com .ct-so-edicao (renomear/finalizar, editar e excluir
   treino, arrastar, adicionar treino) e esconde os .ct-so-leitura.

   O modo fica guardado por ficha no sessionStorage: depois de salvar um
   treino a página recarrega e volta em edição; numa visita nova, abre
   para leitura. Ficha sem nenhum treino já abre em edição (o servidor
   põe a classe).

   window.FitLogFicha = { editavel(), editando(), definir(ligado, {lembrar}) }
   -- usado pelo tutorial para mostrar os botões de edição durante o passeio.
   ========================================================== */
(function () {
    'use strict';

    var ficha = document.getElementById('ctFicha');
    if (!ficha) return;

    var editavel = ficha.getAttribute('data-editavel') === '1';
    var chave = 'fitlog:ficha-editando:' + (ficha.getAttribute('data-versao-id') || '');
    var botao = document.getElementById('btnModoEdicao');

    function lembrar(ligado) {
        try { window.sessionStorage.setItem(chave, ligado ? '1' : '0'); } catch (e) { /* sem storage */ }
    }

    function lido() {
        try { return window.sessionStorage.getItem(chave); } catch (e) { return null; }
    }

    function definir(ligado, opcoes) {
        ligado = !!ligado && editavel;
        ficha.classList.toggle('is-editando', ligado);
        if (botao) botao.setAttribute('aria-pressed', ligado ? 'true' : 'false');
        if (!opcoes || opcoes.lembrar !== false) lembrar(ligado);
    }

    if (!editavel) {
        ficha.classList.remove('is-editando');
    } else {
        var salvo = lido();
        if (salvo === '1' || salvo === '0') definir(salvo === '1', { lembrar: false });
        else definir(ficha.classList.contains('is-editando'), { lembrar: false });
    }

    if (botao) {
        botao.addEventListener('click', function () {
            definir(!ficha.classList.contains('is-editando'));
        });
    }

    window.FitLogFicha = {
        editavel: function () { return editavel; },
        editando: function () { return ficha.classList.contains('is-editando'); },
        definir: definir
    };
})();
