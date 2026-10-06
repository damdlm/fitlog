/**
 * professor-pagina-imagem.js
 * ---------------------------------------------------------------
 * Gera a IMAGEM do pôster da página pública do professor, no formato
 * de Stories (1080 x 1920 px, 9:16), pronta pra mandar pra alguém ou
 * postar em rede social.
 *
 * Roda DENTRO da versão embed da página (pagina_publica_embed.html, o
 * iframe do modal "Ver página"), de propósito: assim a captura usa o
 * mesmo documento, CSS, fontes e fotos que o professor está vendo, em
 * qualquer um dos estilos. O modal (_modal_ver_pagina.html) chama
 * window.ppGerarImagem() pelo contentWindow do iframe.
 *
 * Depende de static/vendor/html-to-image (window.htmlToImage).
 * ---------------------------------------------------------------
 */
(function () {
    'use strict';

    var LARGURA = 1080;
    var ALTURA = 1920;

    var emAndamento = null;

    function aguardarImagens(raiz) {
        var pendentes = Array.prototype.slice.call(raiz.querySelectorAll('img')).map(function (img) {
            if (img.complete) return null;
            return new Promise(function (resolve) {
                img.addEventListener('load', resolve, { once: true });
                img.addEventListener('error', resolve, { once: true });
            });
        });
        return Promise.all(pendentes);
    }

    // Cor de fundo pra preencher as sobras (só aparecem se o "Sobre mim"
    // for tão longo que o pôster passe de 9:16 e precise ser reduzido).
    function corDeFundo(canvas) {
        try {
            var ctx = canvas.getContext('2d');
            var p = ctx.getImageData(2, Math.floor(canvas.height / 2), 1, 1).data;
            return 'rgb(' + p[0] + ',' + p[1] + ',' + p[2] + ')';
        } catch (e) {
            return '#0b0b0b';
        }
    }

    function paraCanvas1080x1920(origem) {
        var destino = document.createElement('canvas');
        destino.width = LARGURA;
        destino.height = ALTURA;
        var ctx = destino.getContext('2d');
        ctx.fillStyle = corDeFundo(origem);
        ctx.fillRect(0, 0, LARGURA, ALTURA);

        if (origem.height <= ALTURA * 1.01) {
            // Já é (quase) 9:16: ocupa a imagem inteira.
            ctx.drawImage(origem, 0, 0, LARGURA, ALTURA);
        } else {
            // Mais alto que 9:16: reduz pra caber na altura, centralizado.
            var escala = ALTURA / origem.height;
            var larg = origem.width * escala;
            ctx.drawImage(origem, (LARGURA - larg) / 2, 0, larg, ALTURA);
        }
        return destino;
    }

    async function gerar() {
        var poster = document.querySelector('.pp-poster');
        if (!poster || !window.htmlToImage) {
            throw new Error('Pôster ou biblioteca de imagem indisponível.');
        }
        if (document.fonts && document.fonts.ready) {
            await document.fonts.ready;
        }
        await aguardarImagens(poster);

        var largura = poster.offsetWidth;
        var canvas = await window.htmlToImage.toCanvas(poster, {
            pixelRatio: LARGURA / largura,
            cacheBust: false,
            // Imagem de Stories vai de ponta a ponta: sem cantos
            // arredondados, sombra nem margem de cartão.
            style: { borderRadius: '0', boxShadow: 'none', margin: '0', border: '0' },
            // Comentários HTML (nodeType 8) ficam de fora: um "--" dentro
            // deles é XML inválido e o navegador recusa carregar o SVG
            // que a biblioteca monta.
            filter: function (no) { return no.nodeType !== 8; }
        });

        var final = paraCanvas1080x1920(canvas);
        return new Promise(function (resolve, reject) {
            final.toBlob(function (blob) {
                if (blob) resolve(blob);
                else reject(new Error('Não foi possível gerar a imagem.'));
            }, 'image/png');
        });
    }

    // Uma geração por vez; reaproveita a que já estiver pronta/rodando.
    // forcar = true descarta e gera de novo (ex.: depois de editar a página).
    window.ppGerarImagem = function (forcar) {
        if (!emAndamento || forcar) {
            emAndamento = gerar().catch(function (erro) {
                emAndamento = null;  // permite tentar de novo
                throw erro;
            });
        }
        return emAndamento;
    };
})();