/* ==========================================================
   Cadastro (templates/auth/register.html) -- Termos de Uso e
   Política de Privacidade em modal.

   Antes, os dois links abriam outra página: no celular não havia
   como voltar e o que já tinha sido digitado no formulário se
   perdia. Agora o clique busca a página pública (mesma origem),
   pega só o conteúdo do cartão e mostra num modal por cima do
   cadastro -- o formulário nunca sai da tela.

   Sem JS, ou se a busca falhar, o link se comporta como sempre
   (abre a página numa nova aba).
   ========================================================== */

document.addEventListener('DOMContentLoaded', function () {
    var modalEl = document.getElementById('modalDocLegal');
    var corpo = document.getElementById('modalDocLegalCorpo');
    var titulo = document.getElementById('modalDocLegalTitulo');
    var links = document.querySelectorAll('a[data-doc-legal]');
    if (!modalEl || !corpo || !titulo || !links.length || !window.bootstrap) return;

    var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    // Evita respostas fora de ordem se a pessoa tocar em outro link
    // antes do primeiro terminar de carregar.
    var pedidoAtual = 0;

    function mesmaPaginaLegal(url) {
        // Só /privacidade/ e /privacidade/termos abrem no modal; qualquer
        // outro link de dentro do texto abre em nova aba.
        return url.origin === window.location.origin
            && /^\/privacidade\/(termos)?\/?$/.test(url.pathname);
    }

    function mostrarCarregando(nome) {
        titulo.textContent = nome;
        corpo.textContent = '';
        var aviso = document.createElement('div');
        aviso.className = 'text-center text-muted py-4';
        var spinner = document.createElement('span');
        spinner.className = 'spinner-border spinner-border-sm me-2';
        spinner.setAttribute('aria-hidden', 'true');
        aviso.appendChild(spinner);
        aviso.appendChild(document.createTextNode('Carregando…'));
        corpo.appendChild(aviso);
    }

    async function carregar(href, nome) {
        var pedido = ++pedidoAtual;
        mostrarCarregando(nome);
        var resposta = await fetch(href, { credentials: 'same-origin', headers: { 'Accept': 'text/html' } });
        if (!resposta.ok) throw new Error('HTTP ' + resposta.status);
        var html = await resposta.text();
        if (pedido !== pedidoAtual) return;

        var doc = new DOMParser().parseFromString(html, 'text/html');
        var conteudo = doc.querySelector('.card-body');
        if (!conteudo) throw new Error('conteúdo não encontrado');
        var tituloPagina = doc.querySelector('.card-header h4');

        titulo.textContent = tituloPagina ? tituloPagina.textContent.trim() : nome;
        corpo.textContent = '';
        corpo.appendChild(document.importNode(conteudo, true));

        // Links de dentro do texto: entre as duas páginas legais troca o
        // conteúdo do modal; o resto abre em outra aba (nunca navega a
        // página do cadastro).
        corpo.querySelectorAll('a[href]').forEach(function (a) {
            var destino = new URL(a.getAttribute('href'), window.location.origin);
            if (mesmaPaginaLegal(destino)) {
                a.dataset.docLegalInterno = destino.pathname;
            } else {
                a.target = '_blank';
                a.rel = 'noopener';
            }
        });
        corpo.scrollTop = 0;
        modalEl.querySelector('.modal-body').scrollTop = 0;
    }

    function abrir(href, nome, linkOriginal) {
        modal.show();
        carregar(href, nome).catch(function () {
            // Falhou (rede, página mudou...): volta ao comportamento
            // antigo, abrindo a página numa nova aba.
            modal.hide();
            window.open(href, '_blank', 'noopener');
        });
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (e) {
            // Ctrl/Cmd/botão do meio: deixa o navegador abrir a aba.
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
            e.preventDefault();
            e.stopPropagation();
            abrir(link.href, link.dataset.docLegal || 'Documento', link);
        });
    });

    corpo.addEventListener('click', function (e) {
        var a = e.target.closest('a[data-doc-legal-interno]');
        if (!a) return;
        e.preventDefault();
        abrir(a.href, titulo.textContent, a);
    });
});