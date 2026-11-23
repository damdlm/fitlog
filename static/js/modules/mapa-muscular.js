/**
 * Mapa muscular da tela Progresso (lote 5).
 *
 * Desenha o corpo (frente e costas) a partir de window.FitLogCorpo
 * (static/vendor/musclemap/corpo-fitlog.js, caminhos adaptados de
 * MuscleMap, MIT) com o estilo do FitLog: uma silhueta própria (todas as
 * partes com contorno grosso e cantos arredondados, sem o cabelo) e os
 * músculos por cima, separados por um vão suave.
 *
 * Dois modos:
 *  - Volume: cor pela quantidade de séries no período (relativa à região
 *    mais treinada).
 *  - Recuperação: estimativa (ver services/mapa_muscular_service.py).
 *
 * Uso: FitLogMapaMuscular.carregar(url, fraseDoPeriodo)
 */
(function () {
    'use strict';

    var raiz = document.getElementById('mapaMuscular');
    if (!raiz || !window.FitLogCorpo) return;

    var NS = 'http://www.w3.org/2000/svg';
    var modo = 'volume';
    var dados = null;
    var selecionada = null;
    var req = 0;
    var frase = '';

    var vistas = raiz.querySelector('.mm-vistas');
    var detalhe = raiz.querySelector('.mm-detalhe');
    var legenda = raiz.querySelector('.mm-legenda');
    var lista = raiz.querySelector('.mm-lista-corpo');
    var vazio = raiz.querySelector('.mm-vazio');

    function fmt(n) {
        return String(n).replace('.', ',');
    }

    function nivelVolume(r) {
        if (!r.series || !dados.max_series) return 0;
        var x = r.series / dados.max_series;
        return x < 0.25 ? 1 : x < 0.5 ? 2 : x < 0.75 ? 3 : 4;
    }

    function classeRecuperacao(r) {
        if (r.status === 'sem_treino') return 'mm-rec-sem';
        if (r.status === 'recuperado') return 'mm-rec-ok';
        return r.faltam === 1 ? 'mm-rec-quase' : 'mm-rec-cedo';
    }

    function textoRecuperacao(r) {
        if (r.status === 'sem_treino') return 'sem treino nos últimos 14 dias';
        var quando = r.dias_desde === 0 ? 'treinou hoje' : (r.dias_desde === 1 ? 'treinou ontem' : 'treinou há ' + r.dias_desde + ' dias');
        if (r.status === 'recuperado') return quando + ' · recuperado';
        return quando + ' · ' + (r.faltam === 1 ? 'falta cerca de 1 dia' : 'faltam cerca de ' + r.faltam + ' dias');
    }

    function textoVolume(r) {
        if (!r.series) return 'nenhuma série ' + frase;
        var t = fmt(r.series) + ' série' + (r.series === 1 ? '' : 's') + ' ' + frase;
        if (r.volume) t += ' · ' + r.volume.toLocaleString('pt-BR') + ' kg';
        return t;
    }

    function desenhar() {
        var corpo = window.FitLogCorpo[dados.genero] || window.FitLogCorpo.M;
        vistas.innerHTML = '';
        [['frente', 'Frente'], ['costas', 'Costas']].forEach(function (par) {
            var v = corpo[par[0]];
            var vb = v.viewBox;
            var fig = document.createElement('figure');
            fig.className = 'mm-vista';
            var svg = document.createElementNS(NS, 'svg');
            svg.setAttribute('viewBox', (vb[0] - 24) + ' ' + (vb[1] - 24) + ' ' + (vb[2] + 48) + ' ' + (vb[3] + 48));
            svg.setAttribute('role', 'group');
            svg.setAttribute('aria-label', 'Corpo, vista de ' + par[1].toLowerCase());

            var silhueta = document.createElementNS(NS, 'g');
            silhueta.setAttribute('class', 'mm-silhueta');
            silhueta.setAttribute('aria-hidden', 'true');
            var musculos = document.createElementNS(NS, 'g');
            musculos.setAttribute('class', 'mm-musculos');
            var grupos = {};
            v.partes.forEach(function (p) {
                p.d.forEach(function (d) {
                    var base = document.createElementNS(NS, 'path');
                    base.setAttribute('d', d);
                    silhueta.appendChild(base);
                    if (!p.r) return;
                    var g = grupos[p.r];
                    if (!g) {
                        g = grupos[p.r] = document.createElementNS(NS, 'g');
                        g.setAttribute('class', 'mm-r');
                        g.setAttribute('data-r', p.r);
                        g.setAttribute('tabindex', '0');
                        g.setAttribute('role', 'button');
                        musculos.appendChild(g);
                    }
                    var m = document.createElementNS(NS, 'path');
                    m.setAttribute('d', d);
                    g.appendChild(m);
                });
            });
            svg.appendChild(silhueta);
            svg.appendChild(musculos);
            fig.appendChild(svg);
            var cap = document.createElement('figcaption');
            cap.textContent = par[1];
            fig.appendChild(cap);
            vistas.appendChild(fig);
        });
        pintar();
    }

    function pintar() {
        vistas.querySelectorAll('.mm-r').forEach(function (g) {
            var r = dados.regioes[g.getAttribute('data-r')];
            var classe = modo === 'volume' ? 'mm-vol-' + nivelVolume(r) : classeRecuperacao(r);
            g.setAttribute('class', 'mm-r ' + classe + (g.getAttribute('data-r') === selecionada ? ' is-sel' : ''));
            g.setAttribute('aria-label', r.nome + ': ' + (modo === 'volume' ? textoVolume(r) : textoRecuperacao(r)));
            g.setAttribute('aria-pressed', g.getAttribute('data-r') === selecionada ? 'true' : 'false');
        });
        legenda.innerHTML = modo === 'volume'
            ? '<span class="mm-leg-txt">menos</span><i class="mm-vol-1"></i><i class="mm-vol-2"></i><i class="mm-vol-3"></i><i class="mm-vol-4"></i><span class="mm-leg-txt">mais séries</span><span class="mm-leg-sem"><i class="mm-vol-0"></i>sem treino</span>'
            : '<span><i class="mm-rec-cedo"></i>recuperando</span><span><i class="mm-rec-quase"></i>quase lá</span><span><i class="mm-rec-ok"></i>recuperado</span><span><i class="mm-rec-sem"></i>sem treino recente</span>';
        raiz.querySelector('.mm-aviso-estimativa').hidden = modo !== 'recuperacao';
        mostrarDetalhe();
        montarLista();
    }

    function mostrarDetalhe() {
        if (!selecionada) {
            detalhe.innerHTML = '<span class="mm-detalhe-dica">Toque num músculo para ver os detalhes.</span>';
            return;
        }
        var r = dados.regioes[selecionada];
        var html = '<strong>' + r.nome + '</strong><div>' + textoVolume(r) + '</div><div>' + textoRecuperacao(r) + '</div>';
        if (r.principais && r.principais.length) {
            html += '<div class="mm-detalhe-ex">' + r.principais.map(function (n) {
                return n.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
            }).join(' · ') + '</div>';
        }
        detalhe.innerHTML = html;
    }

    function montarLista() {
        var itens = Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; });
        itens.sort(function (a, b) { return b[1].series - a[1].series || a[1].nome.localeCompare(b[1].nome); });
        lista.innerHTML = itens.map(function (it) {
            var r = it[1];
            return '<li><span class="mm-lista-nome">' + r.nome + '</span><span class="mm-lista-val">'
                + (r.series ? fmt(r.series) + ' séries' : '—') + '</span><span class="mm-lista-rec">' + textoRecuperacao(r) + '</span></li>';
        }).join('');
    }

    function escolher(slug) {
        selecionada = selecionada === slug ? null : slug;
        pintar();
    }

    vistas.addEventListener('click', function (e) {
        var g = e.target.closest('.mm-r');
        if (g) escolher(g.getAttribute('data-r'));
    });
    vistas.addEventListener('keydown', function (e) {
        var g = e.target.closest('.mm-r');
        if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); escolher(g.getAttribute('data-r')); }
    });
    raiz.querySelectorAll('.mm-modo').forEach(function (b) {
        b.addEventListener('click', function () {
            modo = b.dataset.modo;
            raiz.querySelectorAll('.mm-modo').forEach(function (x) {
                x.classList.toggle('is-ativo', x === b);
                x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
            });
            if (dados) pintar();
        });
    });

    function carregar(url, fraseDoPeriodo) {
        var minha = ++req;
        frase = fraseDoPeriodo || '';
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) {
                if (minha !== req || !j || !j.regioes) return;
                var primeira = !dados || dados.genero !== j.genero;
                dados = j;
                var temAlgo = Object.keys(j.regioes).some(function (k) {
                    return j.regioes[k].series || j.regioes[k].status !== 'sem_treino';
                });
                vazio.hidden = temAlgo;
                if (!selecionada && j.max_series) {
                    selecionada = Object.keys(j.regioes).reduce(function (a, b) {
                        return j.regioes[b].series > j.regioes[a].series ? b : a;
                    });
                }
                if (primeira) desenhar(); else pintar();
            })
            .catch(function () { /* a seção fica como está; as outras continuam */ });
    }

    window.FitLogMapaMuscular = { carregar: carregar };
})();
