/**
 * Mapa muscular da tela Progresso: abas Séries, Recuperação e Força.
 *
 * Segue o modelo de tela do openGym, com implementação própria (o código do
 * openGym é AGPL e não foi copiado). O desenho do corpo é o do MuscleMap
 * (MIT), sem alterações: static/vendor/musclemap/corpo-fitlog.js.
 * Regras dos números: services/mapa_muscular_service.py.
 *
 * Visual de uma cor só (escala de laranja) e linhas curtas; cada número diz
 * o que é:
 *  - Séries: "Feito na semana" ou "Previsto na ficha". Cada músculo mostra
 *    "9 de 6–14" (séries x meta recomendada) e, embaixo, "✓ na meta" /
 *    "faltam 8" / "acima da meta". No previsto, os treinos por semana são
 *    escolhidos num seletor (− 3 +).
 *  - Recuperação: quanto falta para cada músculo descansar ("em ~8 h ·
 *    amanhã, 4h26") e quais já podem ser treinados.
 *  - Força: carga máxima estimada (1RM) do último exercício feito em que o
 *    músculo é o principal e há quantos dias foi feito; níveis de força dos
 *    levantamentos com barra, com o peso corporal informado ali mesmo.
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
    var editandoPeso = false;
    var urlBase = '';
    var urlForcaBase = '';
    var req = 0;

    var el = function (s) { return raiz.querySelector(s); };
    var vistas = el('.mm-vistas');
    var legenda = el('.mm-legenda');
    var explica = el('.mm-explica');
    var painel = el('.mm-painel');

    function esc(t) {
        return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }
    function fmt(n) { return String(Math.round(n * 10) / 10).replace('.', ','); }
    function dataCurta(iso) {
        var p = iso.slice(0, 10).split('-');
        return +p[2] + ' ' + MESES[+p[1] - 1];
    }
    function diaSemana(iso) { return DIAS[new Date(iso.slice(0, 10) + 'T12:00:00').getDay()]; }
    // dias de hoje até a data (negativo = passado)
    function diasAte(iso) {
        var d = new Date(iso.slice(0, 10) + 'T12:00:00'), h = new Date();
        h.setHours(12, 0, 0, 0);
        return Math.round((d - h) / 864e5);
    }
    function diasDesde(iso) { return Math.max(0, -diasAte(iso)); }
    // "hoje, 4h26" / "amanhã, 18h" / "sáb, 8h31"
    function quando(isoLocal) {
        var p = isoLocal.split('T'), hm = (p[1] || '00:00').split(':');
        var dif = diasAte(p[0]);
        var dia = dif === 0 ? 'hoje' : dif === 1 ? 'amanhã' : diaSemana(p[0]);
        return dia + ', ' + (+hm[0]) + 'h' + (hm[1] !== '00' ? hm[1] : '');
    }
    // "~40 min" / "~8 h" / "~1d 12h"
    function duracao(h) {
        if (h < 1) return '~' + Math.max(1, Math.round(h * 60)) + ' min';
        if (h < 24) return '~' + Math.round(h) + ' h';
        var d = Math.floor(h / 24), r = Math.round(h - d * 24);
        if (r === 24) { d += 1; r = 0; }
        return '~' + d + 'd' + (r ? ' ' + r + 'h' : '');
    }
    function feitoHa(dias) {
        return dias === 0 ? 'feito hoje' : dias === 1 ? 'feito ontem' : 'feito há ' + dias + ' dias';
    }
    function regioesOrdenadas(f) {
        return Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; }).filter(f || function () { return true; });
    }

    // ---------------- valores e cores por aba ----------------

    // Séries na tela são inteiras (a série do músculo secundário conta 0,5);
    // status e cor usam o MESMO número que aparece, senão "6 de 6–16" vinha
    // com "faltam 1" (5,5 séries).
    function valorSeries(r) {
        if (sub === 'planejado') {
            var t = dados.planejado.treinos || 0;
            return t ? Math.round(r.planejado_ciclo * (treinosSemana || t) / t) : 0;
        }
        return Math.round(r.series);
    }
    // pouco (menos da metade da meta) / quase na meta / na meta / acima
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
    function classeRecuperacao(r) {
        return { fatigado: 'mm-f-fatigado', recuperando: 'mm-f-recuperando', pronto: 'mm-f-pronto' }[r.estado] || 'mm-c-vazio';
    }
    // Força: há quanto tempo o músculo foi treinado
    function classeForca(r) {
        if (!r.ultimo_treino) return 'mm-c-vazio';
        var d = diasDesde(r.ultimo_treino);
        return d <= 7 ? 'mm-s3' : d <= 14 ? 'mm-s2' : 'mm-s1';
    }
    function classeDe(r) {
        return aba === 'series' ? classeSeries(r) : aba === 'fadiga' ? classeRecuperacao(r) : classeForca(r);
    }
    // Exercício que representa o músculo: o que o aluno fez POR ÚLTIMO entre
    // os que têm o músculo como PRINCIPAL e carga registrada (empate: maior
    // 1RM). Antes era o de maior 1RM dos 6 meses -- aparecia um exercício de
    // meses atrás ao lado de "treinou há 3 dias", que era a data do músculo.
    // Um exercício em que o músculo é só secundário (mergulho para ombros,
    // p.ex.) não diz quanto ele levanta. Só os últimos dias_forca (60) dias:
    // um 1RM de meses atrás não é a força de hoje.
    function exercicioDoMusculo(r) {
        var ex = null, janela = dados.dias_forca || 60;
        r.exercicios.forEach(function (e) {
            if (e.papel !== 'principal' || !e.e1rm || diasDesde(e.data) > janela) return;
            if (!ex || e.data > ex.data || (e.data === ex.data && e.e1rm > ex.e1rm)) ex = e;
        });
        return ex;
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
        var p = dados.planejado;
        el('.mm-sub').hidden = aba !== 'series';
        el('.mm-semana').hidden = sub !== 'feito';
        var nota = el('.mm-nota-planejado');
        nota.hidden = sub !== 'planejado';
        nota.innerHTML = p.treinos
            ? 'Séries por semana se você cumprir a ficha' + (p.ficha ? ' <b>' + esc(p.ficha) + '</b>' : '') + '.'
            : 'Não há ficha ativa, então não há séries previstas para mostrar.';
        var s = dados.semana;
        el('.mm-semana-rotulo').textContent = (s.offset === 0 ? 'Esta semana' : 'Semana') + ' · ' + dataCurta(s.inicio) + ' a ' + dataCurta(s.fim);
        el('.mm-semana-prox').disabled = s.offset >= 0;
        if (aba === 'series') {
            legenda.innerHTML = '<span><i class="mm-s1"></i>pouco</span><span><i class="mm-s2"></i>quase na meta</span>'
                + '<span><i class="mm-s3"></i>na meta</span><span><i class="mm-s4"></i>acima</span>';
            explica.textContent = '';
        } else if (aba === 'fadiga') {
            legenda.innerHTML = '<span><i class="mm-f-fatigado"></i>cansado</span><span><i class="mm-f-recuperando"></i>recuperando</span>'
                + '<span><i class="mm-f-pronto"></i>pronto</span><span><i class="mm-c-vazio"></i>sem treino recente</span>';
            explica.textContent = 'Quanto tempo falta para cada músculo descansar do último treino.';
        } else {
            legenda.innerHTML = '<span><i class="mm-s3"></i>treinou nos últimos 7 dias</span><span><i class="mm-s2"></i>8 a 14 dias</span>'
                + '<span><i class="mm-s1"></i>mais de 14 dias</span><span><i class="mm-c-vazio"></i>sem treino</span>';
            explica.textContent = 'A carga máxima estimada (1RM) do último exercício que você fez para cada músculo.';
        }
    }

    // ---------------- listas ----------------

    function barra(pct, faixa) {
        var html = '<span class="mm-barra" aria-hidden="true">';
        if (faixa) html += '<span class="mm-barra-faixa" style="left:' + faixa[0].toFixed(1) + '%;width:' + (faixa[1] - faixa[0]).toFixed(1) + '%"></span>';
        return html + '<span class="mm-barra-valor" style="width:' + Math.min(100, pct).toFixed(1) + '%"></span></span>';
    }

    function mostrarMais(total) {
        if (total <= 6) return '';
        return '<button type="button" class="mm-mais">' + (mostrarTodos ? 'Mostrar menos' : 'Mostrar mais') + ' <i class="bi bi-chevron-' + (mostrarTodos ? 'up' : 'down') + '"></i></button>';
    }

    function listaSeries() {
        var plan = sub === 'planejado';
        if (plan && !dados.planejado.treinos) return '';
        var itens = regioesOrdenadas(function (it) { return it[1].faixa || valorSeries(it[1]) > 0; });
        itens.sort(function (a, b) { return valorSeries(b[1]) - valorSeries(a[1]) || a[1].nome.localeCompare(b[1].nome); });
        var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
        var feitas = plan ? 'previstas' : 'feitas';
        var html = '<div class="mm-marcas"><span><i class="mm-m-valor"></i>séries ' + feitas + '</span><span><i class="mm-m-faixa"></i>meta recomendada</span></div>'
            + '<div class="mm-cab"><span>Músculo</span><span>Séries ' + feitas + ' · meta</span></div>'
            + '<ul class="mm-lista">' + visiveis.map(function (it) {
                var r = it[1], v = valorSeries(r), f = r.faixa, n = v;
                var topo = Math.max(f ? f[1] * 1.12 : 0, v * 1.05, 1);
                var pf = f ? [f[0] / topo * 100, f[1] / topo * 100] : null;
                var st = '';
                if (f) {
                    if (v >= f[0] && v <= f[1]) st = '<small class="mm-ok">✓ na meta</small>';
                    else if (v > f[1]) st = '<small class="mm-falta">acima da meta</small>';
                    // "faltam N" só na semana em andamento; semana fechada ou ficha: "abaixo da meta"
                    else st = '<small class="mm-falta">' + (plan || dados.semana.offset < 0 ? 'abaixo da meta' : 'faltam ' + (f[0] - v)) + '</small>';
                }
                return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                    + '<span class="mm-lista-nome">' + esc(r.nome) + '</span>' + barra(v / topo * 100, pf)
                    + '<span class="mm-lista-num"><b>' + n + '</b>' + (f ? ' de ' + f[0] + '–' + f[1] : '') + st + '</span></li>';
            }).join('') + '</ul>' + mostrarMais(itens.length);
        if (plan) {
            html += '<p class="mm-treinos">Considerando <span class="mm-stepper" role="group" aria-label="Treinos por semana">'
                + '<button type="button" class="mm-treinos-menos" aria-label="Menos um treino por semana"' + (treinosSemana <= 1 ? ' disabled' : '') + '>−</button>'
                + '<b class="mm-treinos-valor" aria-live="polite">' + treinosSemana + '</b>'
                + '<button type="button" class="mm-treinos-mais" aria-label="Mais um treino por semana"' + (treinosSemana >= 14 ? ' disabled' : '') + '>+</button>'
                + '</span> ' + (treinosSemana === 1 ? 'treino' : 'treinos') + ' por semana</p>';
        }
        return html;
    }

    function listaRecuperacao() {
        var pendentes = regioesOrdenadas(function (it) { return it[1].estado === 'fatigado' || it[1].estado === 'recuperando'; });
        pendentes.sort(function (a, b) { return a[1].horas_restantes - b[1].horas_restantes; });
        var prontos = regioesOrdenadas(function (it) { return it[1].estado === 'pronto'; });
        prontos.sort(function (a, b) { return a[1].nome.localeCompare(b[1].nome); });
        if (!pendentes.length && !prontos.length) return '<p class="mm-vazio-txt">Nenhum músculo treinado nas últimas 3 semanas.</p>';
        var html = '';
        if (prontos.length) {
            html += '<p class="mm-ja"><b>Já pode treinar:</b> ' + prontos.map(function (it) { return esc(it[1].nome); }).join(', ') + '</p>';
        }
        if (pendentes.length) {
            html += '<div class="mm-cab"><span>Ainda recuperando</span><span>Fica pronto</span></div><ul class="mm-lista mm-lista-fadiga">'
                + pendentes.map(function (it) {
                    var r = it[1];
                    return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '><i class="mm-ponto ' + classeRecuperacao(r) + '"></i>'
                        + '<span class="mm-lista-nome">' + esc(r.nome) + '</span><span class="mm-lista-num">em <b>' + duracao(r.horas_restantes) + '</b></span>'
                        + '<span class="mm-lista-quando">' + (r.pronto_em ? quando(r.pronto_em) : '') + '</span></li>';
                }).join('') + '</ul>';
        } else {
            html += '<p class="mm-vazio-txt">Todos os músculos treinados já recuperaram.</p>';
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
                html += '<ul class="mm-lista mm-lista-ex">' + r.exercicios.map(function (e) {
                    return '<li><span class="mm-ex"><span class="mm-ex-nome">' + esc(e.nome)
                        + (e.papel === 'secundario' ? ' <small>secundário</small>' : '') + '</span>'
                        + '<span class="mm-ex-sub">' + feitoHa(diasDesde(e.data)) + ' · ' + diaSemana(e.data) + ' ' + dataCurta(e.data) + '</span></span>'
                        + '<span class="mm-lista-num">' + (e.e1rm ? '<b>' + fmt(e.e1rm) + ' kg</b>' : 'sem carga') + '</span></li>';
                }).join('') + '</ul>';
            }
        }
        var itens = [], sem = [];
        regioesOrdenadas().forEach(function (it) {
            var ex = exercicioDoMusculo(it[1]);
            if (ex) itens.push([it[0], it[1], ex]); else sem.push(it[1].nome);
        });
        itens.sort(function (a, b) { return b[2].e1rm - a[2].e1rm || a[1].nome.localeCompare(b[1].nome); });
        sem.sort(function (a, b) { return a.localeCompare(b); });
        if (itens.length) {
            var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
            html += '<div class="mm-cab"><span>Músculo · último exercício</span><span>1RM estimado</span></div>'
                + '<ul class="mm-lista mm-lista-forca">' + visiveis.map(function (it) {
                    var r = it[1], ex = it[2];
                    return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                        + '<span class="mm-ex"><span class="mm-lista-nome">' + esc(r.nome) + '</span><span class="mm-ex-sub">' + esc(ex.nome) + '</span></span>'
                        + '<span class="mm-lista-num"><b>' + fmt(ex.e1rm) + ' kg</b>'
                        + '<small>' + feitoHa(diasDesde(ex.data)) + '</small></span></li>';
                }).join('') + '</ul>' + mostrarMais(itens.length);
        }
        if (sem.length) {
            html += '<p class="mm-sem-carga"><b>Sem exercício principal com carga nos últimos ' + (dados.dias_forca || 60) + ' dias:</b> ' + sem.map(esc).join(', ') + '</p>';
        }
        return html + montarNiveis();
    }

    function blocoPeso() {
        if (!forca.e_o_proprio) {
            return forca.peso_kg ? '' : '<p class="mm-vazio-txt">O aluno ainda não informou o peso corporal.</p>';
        }
        if (forca.peso_kg && !editandoPeso) {
            return '<p class="mm-peso-linha">Peso corporal: <b>' + fmt(forca.peso_kg) + ' kg</b> · <button type="button" class="mm-link mm-peso-editar">alterar</button></p>';
        }
        return '<form class="mm-peso" novalidate><label for="mmPeso">Seu peso corporal</label>'
            + '<input id="mmPeso" type="text" inputmode="decimal" autocomplete="off" placeholder="ex.: 70" value="' + (forca.peso_kg ? fmt(forca.peso_kg) : '') + '"> kg'
            + '<button type="submit">Ver níveis</button><span class="mm-peso-msg" role="status"></span></form>';
    }

    function montarNiveis() {
        var html = '<div class="mm-niveis"><div class="mm-titulo">Níveis de força</div>';
        if (!forca) return html + '<p class="mm-vazio-txt">Carregando…</p></div>';
        if (!forca.levantamentos.length) {
            return html + '<p class="mm-vazio-txt">Aparecem quando você registra um levantamento com barra (supino reto, agachamento, terra, desenvolvimento ou remada curvada).</p></div>';
        }
        html += blocoPeso() + '<ul class="mm-lista mm-lista-niveis">' + forca.levantamentos.map(function (l) {
            var sub = l.nivel
                ? '<b>' + esc(l.nivel) + '</b> · ' + l.razao.toFixed(2).replace('.', ',') + '× o peso'
                    + (l.proximo ? '<small>' + esc(l.proximo) + ': faltam ' + fmt(l.faltam_kg) + ' kg</small>' : '')
                : '<small>informe o peso para ver o nível</small>';
            return '<li><span class="mm-ex"><span class="mm-lista-nome">' + esc(l.nome) + '</span><span class="mm-ex-sub">1RM estimado: ' + fmt(l.e1rm) + ' kg</span></span>'
                + '<span class="mm-lista-num">' + sub + '</span></li>';
        }).join('') + '</ul><p class="mm-nota-niveis">Nível = 1RM estimado ÷ peso corporal. Referência aproximada para adultos, não é meta.</p></div>';
        return html;
    }

    function render() {
        if (!dados) return;
        montarTopo();
        pintar();
        painel.innerHTML = aba === 'series' ? listaSeries() : aba === 'fadiga' ? listaRecuperacao() : listaForca();
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
        var passo = e.target.closest('.mm-treinos-menos') ? -1 : e.target.closest('.mm-treinos-mais') ? 1 : 0;
        if (passo) {
            treinosSemana = Math.max(1, Math.min(14, treinosSemana + passo));
            render();
            var b = painel.querySelector(passo < 0 ? '.mm-treinos-menos' : '.mm-treinos-mais');
            if (b && !b.disabled) b.focus();
            return;
        }
        if (e.target.closest('.mm-peso-editar')) {
            editandoPeso = true; render();
            var campo = painel.querySelector('#mmPeso');
            if (campo) campo.focus();
            return;
        }
        var li = e.target.closest('li[data-r]');
        if (li) escolher(li.getAttribute('data-r'));
    });
    painel.addEventListener('submit', function (e) {
        var form = e.target.closest('.mm-peso');
        if (!form) return;
        e.preventDefault();
        var campo = form.querySelector('#mmPeso'), msg = form.querySelector('.mm-peso-msg'), botao = form.querySelector('button');
        botao.disabled = true;
        msg.textContent = '';
        fetch('/api/peso-corporal', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ peso_kg: campo.value })
        }).then(function (r) { return r.json().then(function (j) { return [r.ok, j]; }); })
            .then(function (res) {
                if (!res[0]) { msg.textContent = res[1].erro || 'Não foi possível salvar.'; botao.disabled = false; return; }
                editandoPeso = false;
                return carregarForca();
            })
            .catch(function () { msg.textContent = 'Sem conexão. Tente de novo.'; botao.disabled = false; });
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
    grupo('.mm-sub-modo', 'sub', function (v) { sub = v; mostrarTodos = false; });
    el('.mm-semana-ant').addEventListener('click', function () { buscar(semana - 1); });
    el('.mm-semana-prox').addEventListener('click', function () { if (semana < 0) buscar(semana + 1); });

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
                    // média das últimas 4 semanas, arredondada (o seletor anda de 1 em 1)
                    treinosSemana = Math.max(1, Math.min(14, Math.round(j.planejado.sessoes_semana || j.planejado.treinos || 3)));
                }
                if (redesenhar) desenhar();
                render();
            })
            .catch(function () { /* a seção fica como está */ });
    }

    function carregarForca() {
        return fetch(urlForcaBase, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) { if (j) { forca = j; if (aba === 'forca') render(); } })
            .catch(function () {});
    }

    function carregar(urlMapa, urlForca) {
        urlBase = urlMapa;
        urlForcaBase = urlForca || '';
        if (!dados) buscar(semana);
        if (urlForcaBase && !forca) carregarForca();
    }

    window.FitLogMapaMuscular = { carregar: carregar };
})();