/**
 * Mapa muscular da tela Progresso: abas Séries, Fadiga e Força.
 *
 * Segue o modelo de tela do openGym, com implementação própria (o código do
 * openGym é AGPL e não foi copiado). O desenho do corpo é o do MuscleMap
 * (MIT), sem alterações: static/vendor/musclemap/corpo-fitlog.js.
 * Regras dos números: services/mapa_muscular_service.py.
 *
 * Uso: FitLogMapaMuscular.carregar(urlMapa, urlForca)
 *   urlMapa recebe "&semana=N" (0 = semana atual).
 */
(function () {
    'use strict';

    var raiz = document.getElementById('mapaMuscular');
    if (!raiz || !window.FitLogCorpo) return;

    var NS = 'http://www.w3.org/2000/svg';
    var MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
    var DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
    var aba = 'series';
    var sub = 'feito';
    var semana = 0;
    var dados = null;
    var forca = null;
    var selecionada = null;
    var mostrarTodos = false;
    var treinosSemana = null;
    var urlBase = '';
    var req = 0;

    var el = function (s) { return raiz.querySelector(s); };
    var vistas = el('.mm-vistas');
    var legenda = el('.mm-legenda');
    var explica = el('.mm-explica');
    var painel = el('.mm-painel');
    var campoTreinos = el('.mm-treinos-semana');

    function esc(t) {
        return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }
    function fmt(n) { return String(Math.round(n * 10) / 10).replace('.', ','); }
    function dataCurta(iso) {
        var p = iso.split('-');
        return +p[2] + ' ' + MESES[+p[1] - 1];
    }
    function diaHora(isoLocal) {
        var p = isoLocal.split('T');
        return DIAS[new Date(p[0] + 'T12:00:00').getDay()] + ' ' + p[1];
    }
    function duracao(h) {
        if (h < 1) return '~' + Math.max(1, Math.round(h * 60)) + ' min';
        if (h < 48) return '~' + Math.round(h) + ' h';
        return '~' + Math.round(h / 24) + ' d';
    }
    function regioesOrdenadas(f) {
        return Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; }).filter(f || function () { return true; });
    }

    // ---------------- valores e cores por aba ----------------

    function valorSeries(r) {
        if (sub === 'planejado') {
            var t = dados.planejado.treinos || 0;
            return t ? r.planejado_ciclo * (treinosSemana || t) / t : 0;
        }
        return r.series;
    }
    function classeSeries(r) {
        var v = valorSeries(r);
        if (!v) return 'mm-c-vazio';
        if (r.faixa) {
            if (v < r.faixa[0] / 2) return 'mm-s1';
            if (v < r.faixa[0]) return 'mm-s2';
            return v <= r.faixa[1] ? 'mm-s3' : 'mm-s4';
        }
        return v < 2 ? 'mm-s1' : 'mm-s2';
    }
    function classeFadiga(r) {
        return { fatigado: 'mm-f-fatigado', recuperando: 'mm-f-recuperando', pronto: 'mm-f-pronto' }[r.estado] || 'mm-c-vazio';
    }
    function classeForca(r) {
        if (!r.ultimo_treino) return 'mm-c-vazio';
        var x = r.retida;
        return x >= 0.95 ? 'mm-r1' : x >= 0.8 ? 'mm-r2' : x >= 0.65 ? 'mm-r3' : x > 0.5 ? 'mm-r4' : 'mm-c-vazio';
    }
    function classeDe(r) {
        return aba === 'series' ? classeSeries(r) : aba === 'fadiga' ? classeFadiga(r) : classeForca(r);
    }

    // ---------------- corpo ----------------

    function desenhar() {
        var corpo = window.FitLogCorpo[dados.genero] || window.FitLogCorpo.M;
        vistas.innerHTML = '';
        [['frente', 'Frente'], ['costas', 'Costas']].forEach(function (par) {
            var v = corpo[par[0]];
            var vb = v.viewBox;
            var svg = document.createElementNS(NS, 'svg');
            svg.setAttribute('viewBox', (vb[0] - 10) + ' ' + (vb[1] - 10) + ' ' + (vb[2] + 20) + ' ' + (vb[3] + 20));
            svg.setAttribute('class', 'mm-corpo');
            svg.setAttribute('role', 'group');
            svg.setAttribute('aria-label', 'Corpo, ' + par[1].toLowerCase());
            var grupos = {};
            v.partes.forEach(function (p) {
                var alvo = svg;
                if (p.r) {
                    alvo = grupos[p.r];
                    if (!alvo) {
                        alvo = grupos[p.r] = document.createElementNS(NS, 'g');
                        alvo.setAttribute('data-r', p.r);
                        alvo.setAttribute('tabindex', '0');
                        alvo.setAttribute('role', 'button');
                        svg.appendChild(alvo);
                    }
                }
                p.d.forEach(function (d) {
                    var path = document.createElementNS(NS, 'path');
                    path.setAttribute('d', d);
                    if (!p.r) path.setAttribute('class', 'mm-neutra');
                    alvo.appendChild(path);
                });
            });
            vistas.appendChild(svg);
        });
    }

    function pintar() {
        vistas.querySelectorAll('[data-r]').forEach(function (g) {
            var slug = g.getAttribute('data-r');
            var r = dados.regioes[slug];
            g.setAttribute('class', 'mm-r ' + classeDe(r) + (slug === selecionada ? ' is-sel' : ''));
            g.setAttribute('aria-label', r.nome);
            g.setAttribute('aria-pressed', slug === selecionada ? 'true' : 'false');
        });
    }

    // ---------------- cabeçalho de cada aba ----------------

    function montarTopo() {
        el('.mm-sub').hidden = aba !== 'series';
        el('.mm-semana').hidden = sub !== 'feito';
        el('.mm-nota-planejado').hidden = sub !== 'planejado';
        var s = dados.semana;
        el('.mm-semana-rotulo').textContent = s.offset === 0 ? 'Esta semana' : 'Semana de ' + dataCurta(s.inicio);
        el('.mm-semana-prox').disabled = s.offset >= 0;
        if (aba === 'series') {
            legenda.innerHTML = '<span class="mm-leg-txt">menos</span><i class="mm-s1"></i><i class="mm-s2"></i><i class="mm-s3"></i><i class="mm-s4"></i><span class="mm-leg-txt">mais</span>';
            explica.textContent = sub === 'planejado' ? 'Séries por semana previstas pela sua ficha.' : '';
        } else if (aba === 'fadiga') {
            legenda.innerHTML = '<span><i class="mm-f-fatigado"></i>Fatigado</span><span><i class="mm-f-recuperando"></i>Recuperando</span><span><i class="mm-f-pronto"></i>Pronto</span><span><i class="mm-c-vazio"></i></span>';
            explica.textContent = 'A fadiga mostra quão recente foi o treino de cada músculo. Alta quer dizer descanso.';
        } else {
            legenda.innerHTML = '<span class="mm-leg-txt">1 cheia</span><i class="mm-r1"></i><i class="mm-r2"></i><i class="mm-r3"></i><i class="mm-r4"></i><i class="mm-c-vazio"></i><span class="mm-leg-txt">0,5 piso</span>';
            explica.textContent = 'A força mostra o quanto cada músculo mantém da força. Treine de novo para renovar. Toque num músculo para ver os exercícios.';
        }
        var p = dados.planejado;
        el('.mm-com-ficha').hidden = !p.treinos;
        el('.mm-sem-ficha').hidden = !!p.treinos;
        el('.mm-ficha-nome').textContent = p.ficha ? '"' + p.ficha + '"' : '';
    }

    // ---------------- listas ----------------

    function barra(pct, faixa) {
        var html = '<span class="mm-barra" aria-hidden="true">';
        if (faixa) html += '<span class="mm-barra-faixa" style="left:' + faixa[0] + '%;width:' + (faixa[1] - faixa[0]) + '%"></span>';
        return html + '<span class="mm-barra-valor" style="width:' + Math.min(100, pct).toFixed(1) + '%"></span>'
            + (faixa ? '<span class="mm-barra-marca" style="left:' + Math.min(100, pct).toFixed(1) + '%"></span>' : '') + '</span>';
    }

    function listaSeries() {
        var itens = regioesOrdenadas(function (it) { return it[1].faixa || valorSeries(it[1]) > 0; });
        if (sub === 'planejado' && !dados.planejado.treinos) return '';
        itens.sort(function (a, b) { return valorSeries(b[1]) - valorSeries(a[1]) || a[1].nome.localeCompare(b[1].nome); });
        var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
        var html = '<ul class="mm-lista">' + visiveis.map(function (it) {
            var r = it[1], v = valorSeries(r), f = r.faixa;
            var topo = Math.max(f ? f[1] * 1.15 : 0, v * 1.05, 1);
            var pf = f ? [f[0] / topo * 100, f[1] / topo * 100] : null;
            return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                + '<span class="mm-lista-nome">' + esc(r.nome) + '</span>' + barra(v / topo * 100, pf)
                + '<span class="mm-lista-num"><b>' + fmt(v) + '</b>' + (f ? ' / ' + f[0] + '–' + f[1] : '') + '</span></li>';
        }).join('') + '</ul>';
        if (itens.length > 6) {
            html += '<button type="button" class="mm-mais">' + (mostrarTodos ? 'Mostrar menos' : 'Mostrar mais') + ' <i class="bi bi-chevron-' + (mostrarTodos ? 'up' : 'down') + '"></i></button>';
        }
        return html;
    }

    function listaFadiga() {
        var pendentes = regioesOrdenadas(function (it) { return it[1].estado === 'fatigado' || it[1].estado === 'recuperando'; });
        pendentes.sort(function (a, b) { return a[1].horas_restantes - b[1].horas_restantes; });
        var prontos = regioesOrdenadas(function (it) { return it[1].estado === 'pronto'; });
        if (!pendentes.length && !prontos.length) return '<p class="mm-vazio-txt">Nenhum músculo treinado nas últimas 3 semanas.</p>';
        var html = '';
        if (pendentes.length) {
            html += '<div class="mm-titulo">Pronto de novo</div><ul class="mm-lista mm-lista-fadiga">' + pendentes.map(function (it) {
                var r = it[1];
                return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '><i class="mm-ponto ' + classeFadiga(r) + '"></i>'
                    + '<span class="mm-lista-nome">' + esc(r.nome) + '</span><span class="mm-lista-num">' + duracao(r.horas_restantes) + '</span>'
                    + '<span class="mm-lista-quando">' + diaHora(r.pronto_em) + '</span></li>';
            }).join('') + '</ul>';
        }
        if (prontos.length) {
            html += '<div class="mm-titulo">Pronto</div><p class="mm-prontos">' + prontos.map(function (it) { return esc(it[1].nome); }).join(' · ') + '</p>';
        }
        return html;
    }

    function listaForca() {
        var html = '';
        if (selecionada) {
            var r = dados.regioes[selecionada];
            html += '<div class="mm-titulo">Exercícios · ' + esc(r.nome) + '</div>';
            if (!r.exercicios.length) {
                html += '<p class="mm-vazio-txt">Nenhum exercício para este músculo nos últimos 6 meses.</p>';
            } else {
                html += '<ul class="mm-lista mm-lista-ex mm-lista-forca">' + r.exercicios.map(function (e) {
                    var pct = Math.round(e.retida * 100);
                    return '<li><span class="mm-ex"><span class="mm-ex-nome">' + esc(e.nome)
                        + (e.papel === 'secundario' ? ' <small>secundário</small>' : '') + '</span>'
                        + '<span class="mm-ex-sub">' + (e.e1rm ? '1RM est.: ' + fmt(e.e1rm) + ' kg · ' : '') + diaHora(e.data + 'T00:00').split(' ')[0] + ' ' + dataCurta(e.data) + '</span></span>'
                        + barra(pct) + '<span class="mm-lista-num">' + (e.e1rm ? '<b>' + fmt(e.e1rm) + ' kg</b> · ' : '') + pct + '%</span></li>';
                }).join('') + '</ul>';
            }
        }
        var itens = regioesOrdenadas();
        itens.sort(function (a, b) {
            var ta = a[1].ultimo_treino ? 1 : 0, tb = b[1].ultimo_treino ? 1 : 0;
            return tb - ta || b[1].retida - a[1].retida || a[1].nome.localeCompare(b[1].nome);
        });
        html += '<ul class="mm-lista mm-lista-forca">' + itens.map(function (it) {
            var r = it[1], pct = Math.round(r.retida * 100);
            return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                + '<span class="mm-lista-nome">' + esc(r.nome) + '</span>' + barra(pct)
                + '<span class="mm-lista-num">' + (r.ultimo_treino ? '<b>' + pct + '%</b>' : 'não treinado') + '</span></li>';
        }).join('') + '</ul>';
        return html + montarNiveis();
    }

    function montarNiveis() {
        var html = '<div class="mm-niveis"><div class="mm-niveis-topo"><span class="mm-titulo">Níveis de força</span>'
            + (forca && forca.e_o_proprio ? '<a href="/auth/profile#peso" class="mm-sobre"><i class="bi bi-person"></i> Sobre você</a>' : '') + '</div>';
        if (!forca) return html + '<p class="mm-vazio-txt">Carregando…</p></div>';
        if (!forca.peso_kg) {
            html += '<p class="mm-vazio-txt">' + (forca.e_o_proprio ? 'Informe seu peso corporal em "Sobre você" para ver os níveis.' : 'O aluno ainda não informou o peso corporal.') + '</p>';
        }
        if (!forca.levantamentos.length) {
            return html + '<p class="mm-vazio-txt">Nenhum levantamento com barra nos últimos 6 meses (supino reto, agachamento, terra, desenvolvimento, remada curvada).</p></div>';
        }
        html += '<ul class="mm-lista mm-lista-niveis">' + forca.levantamentos.map(function (l) {
            return '<li><span class="mm-lista-nome">' + esc(l.nome) + '</span><span class="mm-lista-num">'
                + (l.nivel ? '<b>' + esc(l.nivel) + '</b> · ' + l.razao.toFixed(2).replace('.', ',') + '×' : fmt(l.e1rm) + ' kg') + '</span></li>';
        }).join('') + '</ul><p class="mm-nota-niveis">1RM estimado ÷ peso corporal. Referência aproximada para adultos, não é meta.</p></div>';
        return html;
    }

    function render() {
        if (!dados) return;
        montarTopo();
        pintar();
        painel.innerHTML = aba === 'series' ? listaSeries() : aba === 'fadiga' ? listaFadiga() : listaForca();
    }

    // ---------------- eventos ----------------

    function escolher(slug) {
        selecionada = selecionada === slug ? null : slug;
        render();
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
        if (e.target.closest('.mm-mais')) { mostrarTodos = !mostrarTodos; render(); return; }
        var li = e.target.closest('li[data-r]');
        if (li) escolher(li.getAttribute('data-r'));
    });
    function grupo(seletor, attr, aoEscolher) {
        raiz.querySelectorAll(seletor).forEach(function (b) {
            b.addEventListener('click', function () {
                raiz.querySelectorAll(seletor).forEach(function (x) {
                    x.classList.toggle('is-ativo', x === b);
                    x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
                });
                aoEscolher(b.dataset[attr]);
                render();
            });
        });
    }
    grupo('.mm-aba', 'aba', function (v) { aba = v; selecionada = null; mostrarTodos = false; });
    grupo('.mm-sub-modo', 'sub', function (v) { sub = v; });
    el('.mm-semana-ant').addEventListener('click', function () { buscar(semana - 1); });
    el('.mm-semana-prox').addEventListener('click', function () { if (semana < 0) buscar(semana + 1); });
    campoTreinos.addEventListener('input', function () {
        var n = parseFloat(String(campoTreinos.value).replace(',', '.'));
        if (n > 0 && n <= 14) { treinosSemana = n; render(); }
    });

    function buscar(novaSemana) {
        var minha = ++req;
        semana = Math.max(-52, Math.min(0, novaSemana));
        fetch(urlBase + (urlBase.indexOf('?') >= 0 ? '&' : '?') + 'semana=' + semana, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) {
                if (minha !== req || !j || !j.regioes) return;
                var redesenhar = !dados || dados.genero !== j.genero;
                dados = j;
                if (treinosSemana === null && j.planejado) {
                    treinosSemana = j.planejado.sessoes_semana || j.planejado.treinos || null;
                    if (treinosSemana) campoTreinos.value = String(treinosSemana).replace('.', ',');
                }
                if (redesenhar) desenhar();
                render();
            })
            .catch(function () { /* a seção fica como está */ });
    }

    function carregar(urlMapa, urlForca) {
        urlBase = urlMapa;
        if (!dados) buscar(semana);
        if (urlForca && !forca) {
            fetch(urlForca, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (j) { if (j) { forca = j; if (aba === 'forca') render(); } })
                .catch(function () {});
        }
    }

    window.FitLogMapaMuscular = { carregar: carregar };
})();
