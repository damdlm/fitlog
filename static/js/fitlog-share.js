/**
 * fitlog-share.js
 * ---------------------------------------------------------------
 * Gera imagens "compartilháveis" (formato 1080x1350, proporção 4:5 --
 * funciona bem tanto no feed quanto no story do Instagram) a partir
 * dos dados já carregados nas telas de Calendário e Estatísticas, e
 * abre um modal de preview com botões de baixar/compartilhar.
 *
 * Usado por: templates/calendar/calendario.html e
 * templates/aluno/estatisticas.html (ambos incluem este script e
 * chamam FitLogShare.compartilharCalendario(...) /
 * FitLogShare.compartilharEstatisticas(...) a partir de um clique).
 *
 * Tudo desenhado via Canvas 2D -- não é um screenshot da tela real
 * (ficaria com UI/menus/recorte estranho), é uma arte própria, no
 * mesmo estilo visual (fundo escuro degradê + brilho laranja) que já
 * aparece nos cards "hero" do app.
 * ---------------------------------------------------------------
 */
(function () {
    'use strict';

    const LARANJA = '#F28C33';
    const LARANJA_CLARO = '#FFB366';
    const W = 1080;
    const H = 1350;

    const PALETA_MUSCULOS = [
        '#F28C33', '#FFB366', '#e8e6e1', '#9a9a9a', '#5f6b7a',
        '#7fb3a0', '#c98fb0', '#8f8fd6', '#d6a05a', '#6fa8d6'
    ];

    function arredondar(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + w, y, x + w, y + h, r);
        ctx.arcTo(x + w, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r);
        ctx.arcTo(x, y, x + w, y, r);
        ctx.closePath();
    }

    function carregarImagem(src) {
        return new Promise(function (resolve) {
            const img = new Image();
            img.onload = function () { resolve(img); };
            img.onerror = function () { resolve(null); };
            img.src = src;
        });
    }

    function desenharBackground(ctx) {
        const grad = ctx.createLinearGradient(0, 0, W * 0.3, H);
        grad.addColorStop(0, '#2D2D2D');
        grad.addColorStop(1, '#161616');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);

        // Brilho radial laranja no canto superior direito, igual ao
        // ::before dos cards "hero" do app (est-hero, exs-hero antigo).
        const glow = ctx.createRadialGradient(W - 40, 60, 20, W - 40, 60, 420);
        glow.addColorStop(0, 'rgba(242,140,51,0.35)');
        glow.addColorStop(1, 'rgba(242,140,51,0)');
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, W, H);
    }

    async function desenharCabecalho(ctx, nomeUsuario) {
        const logo = await carregarImagem('/static/images/logo.png');
        const x = 64, y = 56;
        const alturaChip = 92;

        if (logo) {
            // logo.png tem fundo transparente mas o texto "FitLog" é
            // cinza-escuro -- direto no fundo escuro do poster ficaria
            // ilegível, por isso a placa branca por trás.
            const alturaLogo = alturaChip - 30;
            const larguraLogo = alturaLogo * (logo.width / logo.height);
            const larguraChip = larguraLogo + 40;

            ctx.fillStyle = '#ffffff';
            arredondar(ctx, x, y, larguraChip, alturaChip, 18);
            ctx.fill();
            ctx.drawImage(logo, x + 20, y + 15, larguraLogo, alturaLogo);

            ctx.textBaseline = 'middle';
            ctx.font = '700 38px Arial, sans-serif';
            ctx.fillStyle = '#ffffff';
            ctx.fillText(nomeUsuario, x + larguraChip + 22, y + alturaChip / 2);
            ctx.textBaseline = 'alphabetic';

            return y + alturaChip;
        }

        // Fallback (logo não carregou): mantém o wordmark desenhado.
        ctx.textBaseline = 'middle';
        ctx.font = '700 40px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        const fitW = ctx.measureText('Fit').width;
        ctx.fillText('Fit', x, y + alturaChip / 2);
        ctx.fillStyle = LARANJA;
        ctx.fillText('Log', x + fitW, y + alturaChip / 2);
        ctx.font = '700 34px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(nomeUsuario, x + 260, y + alturaChip / 2);
        ctx.textBaseline = 'alphabetic';
        return y + alturaChip;
    }

    function desenharRodape(ctx) {
        const y = H - 96;
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(64, y);
        ctx.lineTo(W - 64, y);
        ctx.stroke();

        ctx.textAlign = 'center';
        ctx.textBaseline = 'alphabetic';
        ctx.font = '700 34px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText('@fitlog.vip', W / 2, y + 50);
        ctx.font = '400 26px Arial, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.fillText('www.fitlog.vip', W / 2, y + 86);
        ctx.textAlign = 'left';
    }

    function desenharTiles(ctx, tiles, top) {
        const gap = 20;
        const larguraTotal = W - 128;
        const larguraTile = (larguraTotal - gap * (tiles.length - 1)) / tiles.length;
        const altura = 150;

        tiles.forEach(function (tile, i) {
            const x = 64 + i * (larguraTile + gap);
            ctx.fillStyle = 'rgba(255,255,255,0.07)';
            arredondar(ctx, x, top, larguraTile, altura, 20);
            ctx.fill();
            ctx.strokeStyle = 'rgba(255,255,255,0.12)';
            ctx.lineWidth = 1;
            arredondar(ctx, x, top, larguraTile, altura, 20);
            ctx.stroke();

            ctx.textAlign = 'center';
            ctx.font = '700 46px Arial, sans-serif';
            ctx.fillStyle = '#ffffff';
            ctx.fillText(String(tile.valor), x + larguraTile / 2, top + 70);

            ctx.font = '400 22px Arial, sans-serif';
            ctx.fillStyle = 'rgba(255,255,255,0.65)';
            ctx.fillText(tile.rotulo, x + larguraTile / 2, top + 112);
        });

        ctx.textAlign = 'left';
        return top + altura;
    }

    // ---------------------------------------------------------------
    // CALENDÁRIO
    // ---------------------------------------------------------------
    async function desenharCalendario(ctx, dados, topoInicial) {
        let y = topoInicial + 74;

        ctx.font = '700 66px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(dados.mesAno, 64, y);

        y += 56;
        y = desenharTiles(ctx, [
            { valor: dados.diasTreinados, rotulo: 'dias treinados' },
            { valor: dados.sequencia, rotulo: 'sequência atual' },
            { valor: dados.volumeKg, rotulo: 'kg no mês' }
        ], y);

        // Mini calendário -- grade de dias do mês, marcando os treinados.
        y += 56;
        const diasSemana = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
        const gridX = 64;
        const gridW = W - 128;
        const cel = gridW / 7;

        ctx.textAlign = 'center';
        ctx.font = '600 22px Arial, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        diasSemana.forEach(function (d, i) {
            ctx.fillText(d, gridX + cel * i + cel / 2, y);
        });

        y += 34;
        const raio = Math.min(cel, 84) * 0.34;
        dados.semanas.forEach(function (semana) {
            semana.forEach(function (dia, col) {
                if (!dia) return;
                const cx = gridX + cel * col + cel / 2;
                const cy = y + raio;
                ctx.beginPath();
                ctx.arc(cx, cy, raio, 0, Math.PI * 2);
                if (dia.treinou) {
                    const g = ctx.createLinearGradient(cx - raio, cy - raio, cx + raio, cy + raio);
                    g.addColorStop(0, LARANJA);
                    g.addColorStop(1, LARANJA_CLARO);
                    ctx.fillStyle = g;
                } else {
                    ctx.fillStyle = 'rgba(255,255,255,0.06)';
                }
                ctx.fill();

                ctx.font = (dia.treinou ? '700 ' : '400 ') + '22px Arial, sans-serif';
                ctx.fillStyle = dia.treinou ? '#1a1a1a' : 'rgba(255,255,255,0.55)';
                ctx.textBaseline = 'middle';
                ctx.fillText(String(dia.numero), cx, cy + 1);
                ctx.textBaseline = 'alphabetic';
            });
            y += raio * 2 + 14;
        });
        ctx.textAlign = 'left';
    }

    async function compartilharCalendario(dados) {
        const canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d');

        desenharBackground(ctx);
        const topo = await desenharCabecalho(ctx, dados.nomeUsuario);
        await desenharCalendario(ctx, dados, topo);
        desenharRodape(ctx);

        abrirPreview(canvas, 'meu-calendario-fitlog.png');
    }

    // ---------------------------------------------------------------
    // ESTATÍSTICAS
    // ---------------------------------------------------------------
    function desenharDonut(ctx, musculos, cx, cy, raioExterno, raioInterno) {
        const total = musculos.reduce(function (s, m) { return s + m.volume; }, 0);
        if (total <= 0) return;
        let anguloInicial = -Math.PI / 2;
        musculos.forEach(function (m, i) {
            const fatia = (m.volume / total) * Math.PI * 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.arc(cx, cy, raioExterno, anguloInicial, anguloInicial + fatia);
            ctx.closePath();
            ctx.fillStyle = PALETA_MUSCULOS[i % PALETA_MUSCULOS.length];
            ctx.fill();
            anguloInicial += fatia;
        });
        // Buraco do donut, na cor de fundo do card em volta pra "vazar"
        // pro fundo escuro por trás.
        ctx.beginPath();
        ctx.arc(cx, cy, raioInterno, 0, Math.PI * 2);
        ctx.fillStyle = '#232323';
        ctx.fill();
    }

    async function desenharEstatisticas(ctx, dados, topoInicial) {
        let y = topoInicial + 74;

        ctx.font = '700 54px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText('Minhas Estatísticas', 64, y);

        y += 20;
        ctx.font = '400 26px Arial, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.55)';
        ctx.fillText('Volume por músculo', 64, y + 34);

        // Donut de volume por músculo
        const cx = W / 2, cyDonut = y + 260;
        desenharDonut(ctx, dados.musculos, cx, cyDonut, 190, 118);

        ctx.textAlign = 'center';
        ctx.font = '700 40px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(dados.volumeTotalFormatado, cx, cyDonut + 6);
        ctx.font = '400 22px Arial, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.55)';
        ctx.fillText('kg no total', cx, cyDonut + 36);
        ctx.textAlign = 'left';

        // Ranking top 5
        let yList = cyDonut + 240;
        ctx.font = '700 30px Arial, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText('Top 5 músculos mais treinados', 64, yList);
        yList += 42;

        const maiorVolume = dados.musculos.length ? dados.musculos[0].volume : 0;
        dados.musculos.slice(0, 5).forEach(function (m, i) {
            const corBase = PALETA_MUSCULOS[i % PALETA_MUSCULOS.length];
            const barraX = 64, barraW = W - 128 - 170, barraY = yList + 8, barraH = 16;

            ctx.font = '600 26px Arial, sans-serif';
            ctx.fillStyle = '#ffffff';
            ctx.fillText((i + 1) + '. ' + m.nome, barraX, yList);

            ctx.textAlign = 'right';
            ctx.font = '600 24px Arial, sans-serif';
            ctx.fillStyle = 'rgba(255,255,255,0.6)';
            ctx.fillText(Math.round(m.volume) + ' kg', W - 64, yList);
            ctx.textAlign = 'left';

            ctx.fillStyle = 'rgba(255,255,255,0.08)';
            arredondar(ctx, barraX, barraY, barraW, barraH, 8);
            ctx.fill();

            const largura = maiorVolume > 0 ? Math.max(barraW * (m.volume / maiorVolume), 10) : 0;
            ctx.fillStyle = corBase;
            arredondar(ctx, barraX, barraY, largura, barraH, 8);
            ctx.fill();

            yList += 62;
        });
    }

    async function compartilharEstatisticas(dados) {
        const canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d');

        desenharBackground(ctx);
        const topo = await desenharCabecalho(ctx, dados.nomeUsuario);
        await desenharEstatisticas(ctx, dados, topo);
        desenharRodape(ctx);

        abrirPreview(canvas, 'minhas-estatisticas-fitlog.png');
    }

    // ---------------------------------------------------------------
    // Modal de preview (baixar / compartilhar) -- injetado 1x sob
    // demanda, reaproveitado pelas duas telas.
    // ---------------------------------------------------------------
    let modalEl = null;

    function garantirModal() {
        if (modalEl) return modalEl;
        const div = document.createElement('div');
        div.className = 'modal fade';
        div.id = 'fitlogShareModal';
        div.tabIndex = -1;
        div.innerHTML =
            '<div class="modal-dialog modal-dialog-centered">' +
                '<div class="modal-content" style="border-radius:20px; overflow:hidden; border:none;">' +
                    '<div class="modal-header" style="background: linear-gradient(135deg, #F28C33 0%, #FFB366 100%); color:white; border:none;">' +
                        '<h5 class="modal-title"><i class="bi bi-share-fill me-2"></i>Compartilhar</h5>' +
                        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>' +
                    '</div>' +
                    '<div class="modal-body text-center" style="background:#161616; padding:20px;">' +
                        '<img id="fitlogSharePreview" src="" style="max-width:100%; border-radius:14px; box-shadow:0 10px 30px rgba(0,0,0,0.4);">' +
                    '</div>' +
                    '<div class="modal-footer justify-content-center" style="background:#161616; border:none; padding-bottom:24px;">' +
                        '<button type="button" class="btn btn-outline-light" id="fitlogShareBaixar">' +
                            '<i class="bi bi-download"></i> Baixar imagem' +
                        '</button>' +
                        '<button type="button" class="btn" id="fitlogShareNativo" style="display:none; background:#F28C33; color:white;">' +
                            '<i class="bi bi-share-fill"></i> Compartilhar' +
                        '</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(div);
        modalEl = div;
        return div;
    }

    function abrirPreview(canvas, nomeArquivo) {
        const modal = garantirModal();
        const dataUrl = canvas.toDataURL('image/png');
        modal.querySelector('#fitlogSharePreview').src = dataUrl;

        const btnBaixar = modal.querySelector('#fitlogShareBaixar');
        btnBaixar.onclick = function () {
            const a = document.createElement('a');
            a.href = dataUrl;
            a.download = nomeArquivo;
            a.click();
        };

        const btnNativo = modal.querySelector('#fitlogShareNativo');
        canvas.toBlob(function (blob) {
            if (!blob) return;
            const arquivo = new File([blob], nomeArquivo, { type: 'image/png' });
            if (navigator.canShare && navigator.canShare({ files: [arquivo] })) {
                btnNativo.style.display = 'inline-block';
                btnNativo.onclick = function () {
                    navigator.share({
                        files: [arquivo],
                        title: 'FitLog',
                        text: 'Confira meu progresso no FitLog! @fitlog.vip'
                    }).catch(function () { /* usuário cancelou, sem problema */ });
                };
            }
        }, 'image/png');

        if (window.bootstrap) {
            new bootstrap.Modal(modal).show();
        }
    }

    window.FitLogShare = {
        compartilharCalendario: compartilharCalendario,
        compartilharEstatisticas: compartilharEstatisticas
    };
})();