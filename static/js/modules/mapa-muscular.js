/**
 * Mapa muscular da tela Progresso.
 *
 * Desenha o corpo (frente e costas) a partir de window.FitLogCorpo
 * (static/vendor/musclemap/corpo-fitlog.js, caminhos adaptados de
 * MuscleMap, MIT) com o estilo do FitLog: silhueta própria (todas as
 * partes com contorno grosso e cantos arredondados, sem o cabelo) e os
 * músculos por cima, separados por um vão suave.
 *
 * Abas:
 *  - Séries: Feito (média por semana no período) ou Planejado (pela ficha
 *    ativa × treinos por semana), com a faixa de referência por músculo.
 *  - Recuperação: estimativa por hora, com "Pronto de novo".
 *  - Força: nível por levantamento com barra (precisa do peso corporal).
 * Regras em services/mapa_muscular_service.py.
 *
 * Uso: FitLogMapaMuscular.carregar(urlMapa, urlForca, fraseDoPeriodo)
 */
(function () {
    'use strict';

    var raiz = document.getElementById('mapaMuscular');
    if (!raiz || !window.FitLogCorpo) return;

    var NS = 'http://www.w3.org/2000/svg';
    var aba = 'series';
    var sub = 'feito';
    var dados = null;
    var forca = null;
    var selecionada = null;
    var req = 0;
    var frase = '';
    var treinosSemana = null;
    var mostrarTodos = false;
    var DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

    var el = function (sel) { return raiz.querySelector(sel); };
    var vistas = el('.mm-vistas');
    var detalhe = el('.mm-detalhe');
    var legenda = el('.mm-legenda');
    var painel = el('.mm-painel');
    var vazio = el('.mm-vazio');
    var subModos = el('.mm-sub');
    var campoTreinos = el('.mm-treinos-semana');
    var notaPlanejado = el('.mm-nota-planejado');

    function esc(t) {
        return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }
    function fmt(n) { return String(Math.round(n * 10) / 10).replace('.', ','); }

    function valorSeries(r) {
        if (sub === 'planejado') {
            var t = dados.planejado.treinos || 0;
            return t ? r.planejado_ciclo * (treinosSemana || t) / t : 0;
        }
        return r.series_semana;
    }

    function nivelSeries(r) {
        var v = valorSeries(r);
        if (!v) return 0;
        if (r.faixa) {
            if (v < r.faixa[0] / 2) return 1;
            if (v < r.faixa[0]) return 2;
            return v <= r.faixa[1] ? 3 : 4;
        }
        var max = 0;
        Object.keys(dados.regioes).forEach(function (k) { max = Math.max(max, valorSeries(dados.regioes[k])); });
        var x = max ? v / max : 0;
        return x < 0.25 ? 1 : x < 0.5 ? 2 : 3;
    }

    function classeRecuperacao(r) {
        return { sem_treino: 'mm-rec-sem', recuperado: 'mm-rec-ok', quase: 'mm-rec-quase', cedo: 'mm-rec-cedo' }[r.status];
    }

    function quandoPronto(r) {
        if (!r.pronto_em) return '';
        var p = r.pronto_em.split('T');
        var d = new Date(p[0] + 'T12:00:00');
        return DIAS[d.getDay()] + ' ' + p[1];
    }

    function textoRecuperacao(r) {
        if (r.status === 'sem_treino') return 'sem treino nos últimos 14 dias';
        var h = r.horas_desde;
        var quando = h < 1 ? 'treinou há menos de 1 h' : (h < 48 ? 'treinou há ' + Math.round(h) + ' h' : 'treinou há ' + Math.round(h / 24) + ' dias');
        if (r.status === 'recuperado') return quando + ' · recuperado';
        return quando + ' · pronto em ~' + Math.max(1, Math.round(r.horas_restantes)) + ' h (' + quandoPronto(r) + ')';
    }

    function textoSeries(r) {
        var v = valorSeries(r);
        var t = fmt(v) + ' série' + (Math.round(v * 10) === 10 ? '' : 's') + ' por semana';
        t += sub === 'planejado' ? ' na ficha' : ' ' + frase;
        if (r.faixa) t += ' · faixa ' + r.faixa[0] + '–' + r.faixa[1];
        return t;
    }

    // ------------------------------------------------------------------
    // Desenho
    // ------------------------------------------------------------------

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
    }

    function pintar() {
        var emForca = aba === 'forca';
        el('.mm-layout').classList.toggle('is-forca', emForca);
        subModos.hidden = aba !== 'series';
        notaPlanejado.hidden = !(aba === 'series' && sub === 'planejado');
        if (!emForca && dados) {
            vistas.querySelectorAll('[data-r]').forEach(function (g) {
                var slug = g.getAttribute('data-r');
                var r = dados.regioes[slug];
                var classe = aba === 'series' ? 'mm-vol-' + nivelSeries(r) : classeRecuperacao(r);
                g.setAttribute('class', 'mm-r ' + classe + (slug === selecionada ? ' is-sel' : ''));
                g.setAttribute('aria-label', r.nome + ': ' + (aba === 'series' ? textoSeries(r) : textoRecuperacao(r)));
                g.setAttribute('aria-pressed', slug === selecionada ? 'true' : 'false');
            });
        }
        legenda.hidden = emForca;
        detalhe.hidden = emForca;
        legenda.innerHTML = aba === 'series'
            ? '<span><i class="mm-vol-1"></i><i class="mm-vol-2"></i>abaixo da faixa</span><span><i class="mm-vol-3"></i>na faixa</span><span><i class="mm-vol-4"></i>acima</span><span><i class="mm-vol-0"></i>nada</span>'
            : '<span><i class="mm-rec-cedo"></i>cansado</span><span><i class="mm-rec-quase"></i>recuperando</span><span><i class="mm-rec-ok"></i>pronto</span><span><i class="mm-rec-sem"></i>sem treino recente</span>';
        if (aba === 'series') montarBarras();
        else if (aba === 'recuperacao') montarProntos();
        else montarForca();
        mostrarDetalhe();
    }

    function mostrarDetalhe() {
        if (aba === 'forca' || !dados) return;
        if (!selecionada) {
            detalhe.innerHTML = '<span class="mm-detalhe-dica">Toque num músculo para ver os detalhes.</span>';
            return;
        }
        var r = dados.regioes[selecionada];
        if (aba === 'recuperacao') {
            detalhe.innerHTML = '<strong>' + esc(r.nome) + '</strong><div>' + esc(textoRecuperacao(r)) + '</div>'
                + '<div>Janela estimada: ' + r.janela_h + ' h</div>';
            return;
        }
        var html = '<strong>' + esc(r.nome) + '</strong><div>' + esc(textoSeries(r)) + '</div>';
        if (sub === 'feito' && r.series) {
            html += '<div>' + fmt(r.series) + ' séries no total' + (r.volume ? ' · ' + r.volume.toLocaleString('pt-BR') + ' kg' : '') + '</div>';
        }
        html += '<div>' + esc(textoRecuperacao(r)) + '</div>';
        if (r.principais && r.principais.length && sub === 'feito') {
            html += '<div class="mm-detalhe-ex">' + r.principais.map(esc).join(' · ') + '</div>';
        }
        detalhe.innerHTML = html;
    }

    // ------------------------------------------------------------------
    // Listas de cada aba
    // ------------------------------------------------------------------

    function montarBarras() {
        var itens = Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; })
            .filter(function (it) { return it[1].faixa || valorSeries(it[1]) > 0; });
        if (sub === 'planejado' && !dados.planejado.treinos) { painel.innerHTML = ''; return; }
        itens.sort(function (a, b) { return valorSeries(b[1]) - valorSeries(a[1]) || a[1].nome.localeCompare(b[1].nome); });
        var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
        var html = '<ul class="mm-barras">' + visiveis.map(function (it) {
            var r = it[1], v = valorSeries(r), f = r.faixa;
            var topo = Math.max(f ? f[1] * 1.15 : 0, v * 1.05, 1);
            var pct = function (x) { return Math.min(100, x / topo * 100).toFixed(1) + '%'; };
            var na = f && v >= f[0] && v <= f[1];
            var acima = f && v > f[1];
            return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                + '<span class="mm-barra-nome">' + esc(r.nome) + '</span>'
                + '<span class="mm-barra" aria-hidden="true">'
                + (f ? '<span class="mm-barra-faixa" style="left:' + pct(f[0]) + ';width:calc(' + pct(f[1]) + ' - ' + pct(f[0]) + ')"></span>' : '')
                + '<span class="mm-barra-valor' + (na ? ' is-na-faixa' : (acima ? ' is-acima' : '')) + '" style="width:' + pct(v) + '"></span>'
                + '<span class="mm-barra-marca" style="left:' + pct(v) + '"></span></span>'
                + '<span class="mm-barra-num"><b>' + fmt(v) + '</b>' + (f ? ' / ' + f[0] + '–' + f[1] : '') + '</span></li>';
        }).join('') + '</ul>';
        if (itens.length > 6) {
            html += '<button type="button" class="mm-mais">' + (mostrarTodos ? 'Mostrar menos' : 'Mostrar todos (' + itens.length + ')') + '</button>';
        }
        painel.innerHTML = html;
    }

    function montarProntos() {
        var itens = Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; })
            .filter(function (it) { return it[1].status !== 'sem_treino'; });
        // quem ainda está recuperando primeiro (o que fica pronto antes no topo); prontos no fim
        itens.sort(function (a, b) {
            var pa = a[1].status === 'recuperado', pb = b[1].status === 'recuperado';
            if (pa !== pb) return pa ? 1 : -1;
            return pa ? a[1].nome.localeCompare(b[1].nome) : a[1].horas_restantes - b[1].horas_restantes;
        });
        if (!itens.length) {
            painel.innerHTML = '<p class="mm-painel-vazio">Nenhum músculo treinado nos últimos 14 dias.</p>';
            return;
        }
        painel.innerHTML = '<div class="mm-painel-titulo">Pronto de novo</div><ul class="mm-prontos">' + itens.map(function (it) {
            var r = it[1];
            var tempo = r.status === 'recuperado' ? 'pronto' : '~' + Math.max(1, Math.round(r.horas_restantes)) + ' h';
            return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                + '<i class="' + classeRecuperacao(r) + '"></i><span class="mm-pronto-nome">' + esc(r.nome) + '</span>'
                + '<span class="mm-pronto-tempo">' + tempo + '</span>'
                + '<span class="mm-pronto-quando">' + (r.status === 'recuperado' ? '' : quandoPronto(r)) + '</span></li>';
        }).join('') + '</ul>';
    }

    function montarForca() {
        if (!forca) {
            painel.innerHTML = '<p class="mm-painel-vazio">Carregando…</p>';
            return;
        }
        var html = '';
        if (!forca.peso_kg) {
            html += '<div class="mm-forca-peso">' + (forca.e_o_proprio
                ? 'Informe seu peso corporal para ver o nível de força. <a href="/auth/profile#peso">Informar meu peso</a>'
                : 'O aluno ainda não informou o peso corporal no perfil, por isso o nível não aparece.') + '</div>';
        }
        if (!forca.levantamentos.length) {
            html += '<p class="mm-painel-vazio">Nenhum levantamento com barra nos últimos 6 meses. Entram: supino reto, agachamento livre, levantamento terra (e romeno), desenvolvimento e remada curvada, todos com barra.</p>';
        } else {
            html += '<ul class="mm-forca">' + forca.levantamentos.map(function (l) {
                var topo = l.nivel ? '<span class="mm-nivel mm-nivel-' + l.nivel_idx + '">' + esc(l.nivel) + '</span><span class="mm-razao">' + l.razao.toFixed(2).replace('.', ',') + '× o peso</span>' : '';
                var sub2 = '1RM estimado ' + fmt(l.e1rm) + ' kg (' + fmt(l.carga) + ' kg × ' + l.reps + ' em ' + l.data + ')';
                if (l.proximo) sub2 += ' · faltam ~' + fmt(l.faltam_kg) + ' kg para ' + l.proximo;
                return '<li><div class="mm-forca-topo"><span class="mm-forca-nome">' + esc(l.nome) + '</span>' + topo + '</div>'
                    + '<div class="mm-forca-sub">' + esc(sub2) + '</div></li>';
            }).join('') + '</ul>';
            html += '<p class="mm-forca-nota">Níveis pela carga estimada para 1 repetição dividida pelo peso corporal, nos últimos 6 meses. Referência aproximada para adultos: serve para acompanhar a evolução, não é meta.</p>';
        }
        painel.innerHTML = html;
    }

    // ------------------------------------------------------------------
    // Eventos
    // ------------------------------------------------------------------

    function escolher(slug) {
        selecionada = selecionada === slug ? null : slug;
        pintar();
    }
    vistas.addEventListener('click', function (e) {
        var g = e.target.closest('[data-r]');
        if (g) escolher(g.getAttribute('data-r'));
    });
    vistas.addEventListener('keydown', function (e) {
        var g = e.target.closest('[data-r]');
        if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); escolher(g.getAttribute('data-r')); }
    });
    painel.addEventListener('click', function (e) {
        if (e.target.closest('.mm-mais')) { mostrarTodos = !mostrarTodos; pintar(); return; }
        var li = e.target.closest('li[data-r]');
        if (li) escolher(li.getAttribute('data-r'));
    });

    function grupoDeBotoes(seletor, attr, aoEscolher) {
        raiz.querySelectorAll(seletor).forEach(function (b) {
            b.addEventListener('click', function () {
                raiz.querySelectorAll(seletor).forEach(function (x) {
                    x.classList.toggle('is-ativo', x === b);
                    x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
                });
                aoEscolher(b.dataset[attr]);
                if (dados) pintar();
            });
        });
    }
    grupoDeBotoes('.mm-aba', 'aba', function (v) { aba = v; });
    grupoDeBotoes('.mm-sub-modo', 'sub', function (v) { sub = v; });
    campoTreinos.addEventListener('input', function () {
        var n = parseFloat(String(campoTreinos.value).replace(',', '.'));
        if (n > 0 && n <= 14) { treinosSemana = n; if (dados) pintar(); }
    });

    function carregar(urlMapa, urlForca, fraseDoPeriodo) {
        var minha = ++req;
        frase = fraseDoPeriodo || '';
        fetch(urlMapa, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) {
                if (minha !== req || !j || !j.regioes) return;
                var redesenhar = !dados || dados.genero !== j.genero;
                dados = j;
                var p = j.planejado || {};
                if (treinosSemana === null) {
                    treinosSemana = p.sessoes_semana || p.treinos || null;
                    if (treinosSemana) campoTreinos.value = String(treinosSemana).replace('.', ',');
                }
                el('.mm-ficha-nome').textContent = p.ficha ? '"' + p.ficha + '" (' + p.treinos + ' treino' + (p.treinos === 1 ? '' : 's') + ')' : '';
                el('.mm-com-ficha').hidden = !p.treinos;
                el('.mm-sem-ficha').hidden = !!p.treinos;
                vazio.hidden = Object.keys(j.regioes).some(function (k) {
                    var r = j.regioes[k];
                    return r.series || r.planejado_ciclo || r.status !== 'sem_treino';
                });
                if (!selecionada) {
                    selecionada = Object.keys(j.regioes).reduce(function (a, b) {
                        return j.regioes[b].series > j.regioes[a].series ? b : a;
                    });
                    if (!j.regioes[selecionada].series) selecionada = null;
                }
                if (redesenhar) desenhar();
                pintar();
            })
            .catch(function () { /* a seção fica como está; as outras continuam */ });
        if (urlForca && !forca) {
            fetch(urlForca, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (j) { if (j) { forca = j; if (aba === 'forca') pintar(); } })
                .catch(function () {});
        }
    }

    window.FitLogMapaMuscular = { carregar: carregar };
})();