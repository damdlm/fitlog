/**
 * Centraliza o título do cabeçalho mobile (.navbar-brand-title). Com
 * usuário logado, centraliza no espaço livre real entre a logo e o
 * grupo de ícones à direita (FitBot, sino de notificações, avatar, e o
 * botão de instalar PWA quando visível). Sem usuário logado (não tem
 * grupo de ícones), centraliza no meio do cabeçalho inteiro em vez de
 * só no espaço à direita da logo -- e, se mesmo assim o texto quebrar
 * em 2 linhas, esconde o ícone do título pra sobrar mais espaço pro
 * texto.
 *
 * Antes disso o centro era fixo via CSS (left: 50% do container) e a
 * largura máxima do título era um número fixo (132px) só pro caso do
 * PWA -- não considerava o sino, nem títulos como "Train · Log ·
 * Analyze" que quebram linha mesmo sem o PWA visível. Medir a posição
 * e a largura real dos elementos evita ter que caçar e ajustar esses
 * números mágicos de novo toda vez que um ícone for adicionado.
 */
(function () {
    'use strict';

    const MARGEM_RESPIRO = 12; // px de folga entre o título e cada ícone vizinho

    function ajustar() {
        // Título só existe/importa abaixo do breakpoint lg (ver classe
        // d-lg-none) -- acima disso a logo já tem espaço próprio.
        if (window.innerWidth >= 992) return;

        const container = document.querySelector('.navbar > .container');
        const logo = document.querySelector('.navbar-brand');
        const iconGroup = document.querySelector('.navbar .order-lg-2');
        const titulo = document.querySelector('.navbar-brand-title');
        if (!container || !logo || !titulo) return;

        const icone = titulo.querySelector(':scope > i');

        const containerRect = container.getBoundingClientRect();
        const logoRect = logo.getBoundingClientRect();

        // Sem grupo de ícones (usuário deslogado): centraliza no meio do
        // cabeçalho inteiro, não só no espaço livre entre a logo e a
        // borda direita -- senão o título fica visualmente puxado pra
        // direita (a logo "pesa" mais à esquerda). Com grupo de ícones
        // (usuário logado), mantém o comportamento original: centraliza
        // no espaço livre real entre a logo e os ícones.
        let centro;
        let larguraDisponivel;

        if (iconGroup) {
            const inicioEspacoLivre = logoRect.right;
            const fimEspacoLivre = iconGroup.getBoundingClientRect().left;
            centro = (inicioEspacoLivre + fimEspacoLivre) / 2 - containerRect.left;
            larguraDisponivel = Math.max(
                0,
                (fimEspacoLivre - inicioEspacoLivre) - MARGEM_RESPIRO * 2
            );
        } else {
            centro = containerRect.width / 2;
            const logoRightRelativo = logoRect.right - containerRect.left;
            // Não deixa o título (mesmo centralizado) invadir a logo à
            // esquerda -- limita a largura disponível pela menor distância
            // entre o centro e cada borda (logo à esquerda, container à
            // direita).
            larguraDisponivel = Math.max(
                0,
                2 * Math.min(centro - logoRightRelativo, containerRect.width - centro) - MARGEM_RESPIRO * 2
            );
        }

        titulo.style.left = centro + 'px';
        titulo.style.transform = 'translateX(-50%)';
        titulo.style.maxWidth = larguraDisponivel + 'px';

        if (!icone) return;

        // Mostra o ícone de novo antes de medir -- sem isso, uma vez
        // escondido (ex: girou o celular pra retrato) ele nunca mais
        // voltaria mesmo que depois sobrasse espaço (ex: girou de volta
        // pra paisagem).
        icone.style.display = '';

        const estilo = getComputedStyle(titulo);
        const lineHeight = parseFloat(estilo.lineHeight) || (parseFloat(estilo.fontSize) * 1.3);
        const linhas = Math.round(titulo.scrollHeight / lineHeight);

        if (linhas > 1) {
            icone.style.display = 'none';
        }
    }

    // Recalcula em qualquer mudança que possa alterar a largura do grupo
    // de ícones (ex: botão de instalar PWA aparecendo/sumindo) sem
    // precisar acoplar este arquivo aos outros módulos -- observa a
    // classe do body, que é quem sinaliza essa mudança.
    const observer = new MutationObserver(ajustar);
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });

    window.addEventListener('resize', ajustar);
    window.addEventListener('load', ajustar);
    document.addEventListener('DOMContentLoaded', ajustar);
    // Fontes/ícones (Bootstrap Icons) podem terminar de carregar depois do
    // DOMContentLoaded e mudar a largura da logo/ícones -- recalcula de
    // novo logo em seguida pra não ficar com posição/quebra errada só
    // por causa de timing.
    setTimeout(ajustar, 300);
})();