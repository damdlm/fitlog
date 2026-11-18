/* ==========================================================
   Tema claro / escuro / do sistema (lote 6e, C2).

   A preferência fica no aparelho (localStorage "fitlog:tema": "claro",
   "escuro" ou "sistema"; padrão "claro"). O <head> do base.html já aplica
   data-bs-theme no <html> antes da primeira pintura; este arquivo:
   - liga os seletores [data-tema-opcao] (menu do avatar e "Ajustes");
   - em "sistema", acompanha a troca de claro/escuro do aparelho com a
     página aberta;
   - avisa a página com o evento "fitlog:tema" (detail: {escuro}) --
     chart-ptbr.js usa para recolorir os gráficos.

   window.FitLogTema = { preferencia(), escuro(), definir(pref) }
   ========================================================== */
(function () {
    'use strict';

    var CHAVE = 'fitlog:tema';
    var VALIDAS = ['claro', 'escuro', 'sistema'];
    var raiz = document.documentElement;
    var midia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function preferencia() {
        try {
            var p = window.localStorage.getItem(CHAVE);
            return VALIDAS.indexOf(p) !== -1 ? p : 'claro';
        } catch (e) { return 'claro'; }
    }

    function calcularEscuro(pref) {
        return pref === 'escuro' || (pref === 'sistema' && !!(midia && midia.matches));
    }

    function marcarSeletores(pref) {
        document.querySelectorAll('[data-tema-opcao]').forEach(function (el) {
            var ativo = el.getAttribute('data-tema-opcao') === pref;
            el.classList.toggle('is-ativo', ativo);
            el.setAttribute('aria-checked', ativo ? 'true' : 'false');
        });
    }

    function aplicar(pref) {
        var escuro = calcularEscuro(pref);
        var mudou = (raiz.getAttribute('data-bs-theme') === 'dark') !== escuro;
        raiz.setAttribute('data-bs-theme', escuro ? 'dark' : 'light');
        marcarSeletores(pref);
        if (mudou) {
            document.dispatchEvent(new CustomEvent('fitlog:tema', { detail: { escuro: escuro } }));
        }
    }

    function definir(pref) {
        if (VALIDAS.indexOf(pref) === -1) return;
        try { window.localStorage.setItem(CHAVE, pref); } catch (e) { /* aplica só nesta página */ }
        aplicar(pref);
    }

    document.addEventListener('click', function (ev) {
        var opcao = ev.target.closest && ev.target.closest('[data-tema-opcao]');
        if (!opcao) return;
        ev.preventDefault();
        definir(opcao.getAttribute('data-tema-opcao'));
    });

    // Setas no grupo (role="radiogroup"), como num grupo de rádios.
    document.addEventListener('keydown', function (ev) {
        var opcao = ev.target.closest && ev.target.closest('[data-tema-opcao]');
        if (!opcao || ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(ev.key) === -1) return;
        var grupo = Array.prototype.slice.call(opcao.parentElement.querySelectorAll('[data-tema-opcao]'));
        var i = grupo.indexOf(opcao) + (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp' ? -1 : 1);
        var alvo = grupo[(i + grupo.length) % grupo.length];
        ev.preventDefault();
        definir(alvo.getAttribute('data-tema-opcao'));
        alvo.focus();
    });

    if (midia) {
        var aoMudarSistema = function () { if (preferencia() === 'sistema') aplicar('sistema'); };
        if (midia.addEventListener) midia.addEventListener('change', aoMudarSistema);
        else if (midia.addListener) midia.addListener(aoMudarSistema);
    }

    // Outra aba mudou o tema: acompanha.
    window.addEventListener('storage', function (ev) {
        if (ev.key === CHAVE) aplicar(preferencia());
    });

    aplicar(preferencia());

    window.FitLogTema = {
        preferencia: preferencia,
        escuro: function () { return raiz.getAttribute('data-bs-theme') === 'dark'; },
        definir: definir
    };
})();
