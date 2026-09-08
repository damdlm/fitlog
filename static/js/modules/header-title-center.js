/**
 * Centraliza o título do cabeçalho mobile (.navbar-brand-title) no
 * espaço livre real entre a logo e o grupo de ícones à direita
 * (FitBot, sino de notificações, avatar, e o botão de instalar PWA
 * quando visível).
 *
 * Antes disso o centro era fixo via CSS (left: 50% do container), com
 * um ajuste manual (`calc(50% - 24px)`) só para quando o botão de
 * instalar PWA aparecia. Isso quebra toda vez que a largura do grupo
 * de ícones muda por outro motivo -- foi o que aconteceu ao adicionar
 * o sino de notificações. Medir a posição real dos elementos evita
 * ter que caçar e ajustar esse número mágico de novo no futuro.
 */
(function () {
    'use strict';

    function centralizar() {
        // Título só existe/importa abaixo do breakpoint lg (ver classe
        // d-lg-none) -- acima disso a logo already tem espaço próprio.
        if (window.innerWidth >= 992) return;

        const container = document.querySelector('.navbar > .container');
        const logo = document.querySelector('.navbar-brand');
        const iconGroup = document.querySelector('.navbar .order-lg-2');
        const titulo = document.querySelector('.navbar-brand-title');

        if (!container || !logo || !titulo) return;

        const containerRect = container.getBoundingClientRect();
        const logoRect = logo.getBoundingClientRect();

        // Sem grupo de ícones (usuário deslogado) -- centro simples do container.
        const fimEspacoLivre = iconGroup
            ? iconGroup.getBoundingClientRect().left
            : containerRect.right;

        const inicioEspacoLivre = logoRect.right;
        const centro = (inicioEspacoLivre + fimEspacoLivre) / 2 - containerRect.left;

        titulo.style.left = centro + 'px';
        titulo.style.transform = 'translateX(-50%)';
    }

    // Recalcula em qualquer mudança que possa alterar a largura do grupo
    // de ícones (ex: botão de instalar PWA aparecendo/sumindo) sem
    // precisar acoplar este arquivo ao pwa-install.js -- observa a
    // classe do body, que é quem sinaliza essa mudança.
    const observer = new MutationObserver(centralizar);
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });

    window.addEventListener('resize', centralizar);
    window.addEventListener('load', centralizar);
    document.addEventListener('DOMContentLoaded', centralizar);
    // Fontes/ícones (Bootstrap Icons) podem terminar de carregar depois do
    // DOMContentLoaded e mudar a largura da logo/ícones -- recalcula de
    // novo logo em seguida pra não ficar com posição errada só por causa
    // de timing.
    setTimeout(centralizar, 300);
})();