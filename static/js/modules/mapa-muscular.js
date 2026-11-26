/**
 * Mapa muscular da tela Progresso: abas Séries, Recuperação e Força.
 *
 * Segue o modelo de tela do openGym, com implementação própria (o código do
 * openGym é AGPL e não foi copiado). O desenho do corpo é o do MuscleMap
 * (MIT), sem alterações: static/vendor/musclemap/corpo-fitlog.js.
 * Regras dos números: services/mapa_muscular_service.py.
 *
 * Cada aba responde uma pergunta, escrita no topo dela:
 *  - Séries: quantas séries cada músculo recebeu na semana, comparado com a
 *    ficha e com a faixa recomendada. O corpo é pintado pelo RESULTADO (na
 *    faixa / faltando / acima), e cada músculo tem uma barra só com o feito
 *    (preenchido), o previsto na ficha (tracejado) e a faixa (fundo).
 *  - Recuperação: o que já descansou ("Pronto para treinar hoje") e quanto
 *    falta para o resto, com dia e hora.
 *  - Força: carga máxima estimada (1RM) de cada músculo e a evolução nas
 *    últimas 4 semanas, os níveis de força dos levantamentos com barra (o
 *    peso corporal é informado ali mesmo) e um aviso para músculo da ficha
 *    parado há mais de uma semana.
 * Tocar num músculo (no corpo ou na lista) abre o resumo dele.
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
    var NIVEIS = ['Iniciante', 'Novato', 'Intermediário', 'Avançado', 'Elite'];
    var DIAS_PARADO = 7;
    var aba = 'series';
    var semana = 0;
    var dados = null;
    var forca = null;
    var selecionada = null;
    var mostrarTodos = false;
    var treinosSemana = null;
    var ajustandoTreinos = false;
    var urlBase = '';
    var urlForcaBase = '';
    var req = 0;

    var el = function (s) { return raiz.querySelector(s); };
    var vistas = el('.mm-vistas');
    var legenda = el('.mm-legenda');
    var pergunta = el('.mm-pergunta');
    var resumo = el('.mm-resumo');
    var painel = el('.mm-painel');

    function esc(t) {
        return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }
    function fmt(n) { return String(Math.round(n * 10) / 10).replace('.', ','); }
    function inteiro(n) { return Math.round(n || 0); }
    function dataCurta(iso) {
        var p = iso.slice(0, 10).split('-');
        return +p[2] + ' ' + MESES[+p[1] - 1];
    }
    function diaSemana(iso) { return DIAS[new Date(iso.slice(0, 10) + 'T12:00:00').getDay()]; }
    function diasDesde(iso) {
        var d = new Date(iso.slice(0, 10) + 'T12:00:00'), h = new Date();
        h.setHours(12, 0, 0, 0);
        return Math.round((h - d) / 864e5);
    }
    // "hoje, 4h26" / "amanhã, 18h" / "sáb, 8h31"
    function quando(isoLocal) {
        var p = isoLocal.split('T'), hm = (p[1] || '00:00').split(':');
        var dif = -diasDesde(p[0]);
        var dia = dif === 0 ? 'hoje' : dif === 1 ? 'amanhã' : diaSemana(p[0]);
        return dia + ', ' + (+hm[0]) + 'h' + (hm[1] !== '00' ? hm[1] : '');
    }
    // "~40 min" / "~12 h" / "~1 dia e 16 h" / "~3 dias"
    function duracao(h) {
        if (h < 1) return '~' + Math.max(1, Math.round(h * 60)) + ' min';
        if (h < 24) return '~' + Math.round(h) + ' h';
        var d = Math.floor(h / 24), r = Math.round(h - d * 24);
        if (r === 24) { d += 1; r = 0; }
        return '~' + d + (d > 1 ? ' dias' : ' dia') + (r ? ' e ' + r + ' h' : '');
    }
    function regioes(f) {
        return Object.keys(dados.regioes).map(function (k) { return [k, dados.regioes[k]]; }).filter(f || function () { return true; });
    }

    // ---------------- Séries ----------------

    function plano(r) {
        var t = dados.planejado.treinos || 0;
        return t ? r.planejado_ciclo * (treinosSemana || t) / t : 0;
    }
    // ok | faltando (semana atual) | abaixo (semana fechada) | acima | fora
    function statusSeries(r) {
        var f = r.faixa, s = r.series;
        if (!f || (!s && !plano(r))) return 'fora';
        if (s > f[1]) return 'acima';
        if (s >= f[0]) return 'ok';
        return dados.semana.offset === 0 ? 'faltando' : 'abaixo';
    }
    var ROTULO_STATUS = { ok: 'Na faixa', faltando: 'Faltando', abaixo: 'Abaixo', acima: 'Acima', fora: 'Fora da ficha' };
    function naListaSeries(r) { return !!r.faixa && (r.series > 0 || plano(r) > 0); }

    function resumoSeries() {
        var c = { ok: 0, falta: 0, acima: 0 };
        regioes(function (it) { return naListaSeries(it[1]); }).forEach(function (it) {
            var s = statusSeries(it[1]);
            if (s === 'ok') c.ok++; else if (s === 'acima') c.acima++; else if (s !== 'fora') c.falta++;
        });
        var falta = dados.semana.offset === 0 ? 'faltando' : 'abaixo';
        return '<span class="mm-chip mm-chip-ok"><i></i>' + c.ok + ' na faixa</span>'
            + '<span class="mm-chip mm-chip-falta"><i></i>' + c.falta + ' ' + falta + '</span>'
            + '<span class="mm-chip mm-chip-acima"><i></i>' + c.acima + ' acima</span>';
    }

    function linhaSeries(slug, r) {
        var st = statusSeries(r), f = r.faixa, pl = plano(r);
        var topo = Math.max(f[1] * 1.15, r.series * 1.05, pl * 1.05, 1);
        var pct = function (v) { return (Math.min(v, topo) / topo * 100).toFixed(1) + '%'; };
        var falta = Math.max(0, inteiro(f[0] - r.series));
        var pill = st === 'faltando' ? 'Faltam ' + falta : ROTULO_STATUS[st];
        var nums = '<b>' + inteiro(r.series) + '</b> ' + (inteiro(r.series) === 1 ? 'série feita' : 'séries feitas')
            + (pl ? ' · ficha prevê ' + inteiro(pl) : '') + ' · recomendado ' + f[0] + '–' + f[1];
        var aviso = pl && inteiro(pl) < f[0]
            ? '<div class="mm-aviso-ficha"><i class="bi bi-exclamation-triangle-fill"></i> Mesmo cumprindo a ficha (' + inteiro(pl) + '), fica abaixo do recomendado</div>'
            : '';
        return '<li data-r="' + slug + '" class="mm-linha mm-st-' + st + (slug === selecionada ? ' is-sel' : '') + '">'
            + '<div class="mm-linha-topo"><span class="mm-lista-nome">' + esc(r.nome) + '</span><span class="mm-pill">' + pill + '</span></div>'
            + '<span class="mm-barra" aria-hidden="true"><span class="mm-barra-faixa" style="left:' + pct(f[0]) + ';width:calc(' + pct(f[1]) + ' - ' + pct(f[0]) + ')"></span>'
            + '<span class="mm-barra-valor" style="width:' + pct(r.series) + '"></span>'
            + (pl ? '<span class="mm-barra-ficha" style="left:' + pct(pl) + '"></span>' : '') + '</span>'
            + '<div class="mm-linha-num">' + nums + '</div>' + aviso + '</li>';
    }

    function listaSeries() {
        var ordem = { faltando: 0, abaixo: 0, acima: 1, ok: 2, fora: 3 };
        var itens = regioes(function (it) { return naListaSeries(it[1]); });
        itens.sort(function (a, b) {
            var sa = statusSeries(a[1]), sb = statusSeries(b[1]);
            return ordem[sa] - ordem[sb]
                || (b[1].faixa[0] - b[1].series) - (a[1].faixa[0] - a[1].series)
                || a[1].nome.localeCompare(b[1].nome);
        });
        if (!itens.length) {
            return '<p class="mm-vazio-txt">Nenhuma série nesta semana' + (dados.planejado.treinos ? '' : ' e nenhuma ficha ativa para comparar') + '.</p>' + linhaFicha();
        }
        var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
        var html = '<div class="mm-marcas"><span><i class="mm-m-feito"></i>feitas</span><span><i class="mm-m-ficha"></i>previsto na ficha</span>'
            + '<span><i class="mm-m-faixa"></i>faixa recomendada</span></div>'
            + '<ul class="mm-lista mm-lista-series">' + visiveis.map(function (it) { return linhaSeries(it[0], it[1]); }).join('') + '</ul>';
        if (itens.length > 6) {
            html += '<button type="button" class="mm-mais">' + (mostrarTodos ? 'Mostrar menos' : 'Ver todos os músculos') + ' <i class="bi bi-chevron-' + (mostrarTodos ? 'up' : 'down') + '"></i></button>';
        }
        return html + linhaFicha();
    }

    // "Ficha "X" · 2,8 treinos/semana (média das últimas 4 semanas) · Ajustar"
    function linhaFicha() {
        var p = dados.planejado;
        if (!p.treinos) {
            return '<p class="mm-ficha-linha mm-sem-ficha">Não há ficha ativa, então não há séries previstas para comparar.</p>';
        }
        var origem = treinosSemana === p.sessoes_semana && p.sessoes_semana
            ? ' (média das últimas 4 semanas)'
            : treinosSemana === p.treinos ? ' (um de cada treino da ficha)' : '';
        var ficha = p.ficha ? 'Ficha "' + esc(p.ficha) + '" · ' : '';
        if (ajustandoTreinos) {
            return '<p class="mm-ficha-linha">' + ficha + '<label>Treinos por semana <input type="number" class="mm-treinos-semana" min="1" max="14" step="0.5" inputmode="decimal" value="'
                + String(treinosSemana).replace(',', '.') + '"></label> <button type="button" class="mm-link mm-treinos-ok">OK</button></p>';
        }
        return '<p class="mm-ficha-linha">' + ficha + fmt(treinosSemana) + ' treinos/semana' + origem
            + ' · <button type="button" class="mm-link mm-treinos-ajustar">Ajustar</button></p>';
    }

    // ---------------- Recuperação ----------------

    function corRecuperacao(r) {
        return { fatigado: 'mm-f-fatigado', recuperando: 'mm-f-recuperando', pronto: 'mm-f-pronto' }[r.estado] || 'mm-c-vazio';
    }

    function resumoRecuperacao() {
        var prontos = regioes(function (it) { return it[1].estado === 'pronto'; });
        if (!prontos.length) return '';
        prontos.sort(function (a, b) { return a[1].nome.localeCompare(b[1].nome); });
        return '<div class="mm-prontos"><div class="mm-prontos-tit"><i class="bi bi-check-lg"></i> Pronto para treinar hoje</div><div class="mm-tags">'
            + prontos.map(function (it) {
                return '<button type="button" class="mm-tag" data-r="' + it[0] + '">' + esc(it[1].nome) + '</button>';
            }).join('') + '</div></div>';
    }

    function anel(progresso) {
        var c = 2 * Math.PI * 14, cheio = c * Math.max(0.04, Math.min(1, progresso));
        return '<svg class="mm-anel" viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="14" class="mm-anel-fundo"/>'
            + '<circle cx="17" cy="17" r="14" class="mm-anel-valor" stroke-dasharray="' + cheio.toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 17 17)"/></svg>';
    }

    function listaRecuperacao() {
        var pendentes = regioes(function (it) { return it[1].estado === 'fatigado' || it[1].estado === 'recuperando'; });
        pendentes.sort(function (a, b) { return a[1].horas_restantes - b[1].horas_restantes; });
        var treinados = regioes(function (it) { return it[1].estado !== 'sem_treino'; });
        if (!treinados.length) return '<p class="mm-vazio-txt">Nenhum músculo treinado nas últimas 3 semanas.</p>';
        if (!pendentes.length) return '<p class="mm-vazio-txt">Todos os músculos treinados já recuperaram.</p>';
        return '<div class="mm-titulo">Ainda recuperando</div><ul class="mm-lista mm-lista-rec">' + pendentes.map(function (it) {
            var r = it[1];
            // fadiga 1 = recém-treinado; abaixo de 0,25 já está pronto
            var progresso = (1 - r.fadiga) / 0.75;
            return '<li data-r="' + it[0] + '" class="mm-st-' + r.estado + (it[0] === selecionada ? ' is-sel' : '') + '">' + anel(progresso)
                + '<span class="mm-rec-txt"><span class="mm-lista-nome">' + esc(r.nome) + '</span>'
                + (r.ultimo_treino ? '<small>Treinado ' + diaSemana(r.ultimo_treino) + ', ' + dataCurta(r.ultimo_treino) + '</small>' : '') + '</span>'
                + '<span class="mm-rec-quando">Pronto em ' + duracao(r.horas_restantes) + (r.pronto_em ? '<small>' + quando(r.pronto_em) + '</small>' : '') + '</span></li>';
        }).join('') + '</ul>';
    }

    // ---------------- Força ----------------

    // Melhor exercício em que o músculo é o PRINCIPAL (maior 1RM; um
    // exercício em que ele é só secundário -- ex.: mergulho para ombros --
    // não diz quanto ele levanta) e a evolução: melhor das últimas 4
    // semanas x melhor de antes.
    function forcaDe(r) {
        var ex = null;
        for (var i = 0; i < r.exercicios.length; i++) {
            var e = r.exercicios[i];
            if (e.papel === 'principal' && e.e1rm && (!ex || e.e1rm > ex.e1rm)) ex = e;
        }
        if (!ex) return null;
        var evol = null;
        if (ex.e1rm_recente && ex.e1rm_antes) evol = (ex.e1rm_recente / ex.e1rm_antes - 1) * 100;
        var tend = !ex.e1rm_recente ? 'parado' : evol === null ? 'novo' : evol > 2 ? 'sobe' : evol < -2 ? 'cai' : 'estavel';
        return { ex: ex, kg: ex.e1rm_recente || ex.e1rm, evol: evol, tend: tend };
    }
    function corForca(r) {
        var f = forcaDe(r);
        if (!f) return 'mm-c-vazio';
        return { sobe: 'mm-t-sobe', novo: 'mm-t-sobe', estavel: 'mm-t-estavel', cai: 'mm-t-cai', parado: 'mm-t-parado' }[f.tend];
    }

    function avisoParados() {
        var parados = regioes(function (it) {
            var r = it[1];
            return r.planejado_ciclo > 0 && r.ultimo_treino && diasDesde(r.ultimo_treino) >= DIAS_PARADO;
        });
        if (!parados.length) return '';
        parados.sort(function (a, b) { return a[1].ultimo_treino.localeCompare(b[1].ultimo_treino); });
        return '<div class="mm-alerta"><b>Sem treino há mais de 1 semana:</b> ' + parados.map(function (it) {
            return esc(it[1].nome) + ' (' + diasDesde(it[1].ultimo_treino) + ' dias)';
        }).join(', ') + '. A partir de ~2 semanas parado o músculo começa a perder força.</div>';
    }

    function blocoPeso() {
        if (!forca || !forca.e_o_proprio) return '';
        if (forca.peso_kg && !blocoPeso.editando) {
            return '<p class="mm-peso-linha">Peso corporal: <b>' + fmt(forca.peso_kg) + ' kg</b> · <button type="button" class="mm-link mm-peso-editar">alterar</button></p>';
        }
        return '<form class="mm-peso" novalidate><label for="mmPeso">Seu peso corporal</label>'
            + '<input id="mmPeso" type="text" inputmode="decimal" autocomplete="off" placeholder="ex.: 70" value="' + (forca.peso_kg ? fmt(forca.peso_kg) : '') + '"> kg'
            + '<button type="submit">Salvar</button><span class="mm-peso-msg" role="status"></span></form>';
    }

    function listaForca() {
        var itens = regioes(function (it) { return !!forcaDe(it[1]); }).map(function (it) { return [it[0], it[1], forcaDe(it[1])]; });
        itens.sort(function (a, b) { return b[2].kg - a[2].kg; });
        var html = blocoPeso() + avisoParados();
        if (!itens.length) {
            html += '<p class="mm-vazio-txt">Nenhum exercício com carga e repetições nos últimos 6 meses.</p>';
        } else {
            var visiveis = mostrarTodos ? itens : itens.slice(0, 6);
            html += '<div class="mm-titulo">Carga máxima estimada · últimas 4 semanas</div><ul class="mm-lista mm-lista-forca">'
                + visiveis.map(function (it) {
                    var r = it[1], f = it[2], tend;
                    if (f.tend === 'parado') tend = '<span class="mm-tend mm-tend-parado">sem treino há ' + diasDesde(f.ex.data) + ' dias</span>';
                    else if (f.tend === 'novo') tend = '<span class="mm-tend mm-tend-novo">novo</span>';
                    else if (f.tend === 'estavel') tend = '<span class="mm-tend mm-tend-estavel">= estável</span>';
                    else tend = '<span class="mm-tend mm-tend-' + f.tend + '">' + (f.evol > 0 ? '▲ +' : '▼ ') + Math.round(f.evol) + '%</span>';
                    return '<li data-r="' + it[0] + '"' + (it[0] === selecionada ? ' class="is-sel"' : '') + '>'
                        + '<div class="mm-linha-topo"><span class="mm-lista-nome">' + esc(r.nome) + '</span>'
                        + '<span><b class="mm-kg">' + fmt(f.kg) + ' kg</b>' + tend + '</span></div>'
                        + '<div class="mm-ex-sub">' + esc(f.ex.nome) + (forca && forca.peso_kg ? ' · ' + (f.kg / forca.peso_kg).toFixed(2).replace('.', ',') + '× o peso corporal' : '') + '</div></li>';
                }).join('') + '</ul>';
            if (itens.length > 6) {
                html += '<button type="button" class="mm-mais">' + (mostrarTodos ? 'Mostrar menos' : 'Ver todos os músculos') + ' <i class="bi bi-chevron-' + (mostrarTodos ? 'up' : 'down') + '"></i></button>';
            }
        }
        return html + montarNiveis();
    }

    function montarNiveis() {
        var html = '<div class="mm-niveis"><div class="mm-titulo">Níveis de força</div>';
        if (!forca) return html + '<p class="mm-vazio-txt">Carregando…</p></div>';
        if (!forca.levantamentos.length) {
            return html + '<p class="mm-vazio-txt">Aparecem quando você registra um levantamento com barra (supino reto, agachamento, terra, desenvolvimento ou remada curvada).</p></div>';
        }
        if (!forca.peso_kg) {
            html += '<p class="mm-vazio-txt">' + (forca.e_o_proprio ? 'Informe seu peso corporal acima para ver o nível de cada levantamento.' : 'O aluno ainda não informou o peso corporal.') + '</p>';
        }
        html += '<ul class="mm-lista mm-lista-niveis">' + forca.levantamentos.map(function (l) {
            var nivel = l.nivel ? l.nivel_idx : -1;
            return '<li><div class="mm-linha-topo"><span class="mm-lista-nome">' + esc(l.nome) + '</span><b class="mm-kg">' + fmt(l.e1rm) + ' kg</b></div>'
                + (l.nivel
                    ? '<div class="mm-ex-sub">' + l.razao.toFixed(2).replace('.', ',') + '× o peso corporal</div>'
                    + '<div class="mm-niv" aria-label="Nível ' + esc(l.nivel) + '">' + NIVEIS.map(function (_n, i) { return '<span' + (i <= nivel ? ' class="on"' : '') + '></span>'; }).join('') + '</div>'
                    + '<div class="mm-niv-txt"><span>' + esc(l.nivel) + '</span>' + (l.proximo ? '<span>' + esc(l.proximo) + ': faltam ' + fmt(l.faltam_kg) + ' kg</span>' : '') + '</div>'
                    : '')
                + '</li>';
        }).join('') + '</ul><p class="mm-nota-niveis">1RM estimado ÷ peso corporal. Referência aproximada para adultos, não é meta.</p></div>';
        return html;
    }

    // ---------------- resumo do músculo tocado ----------------

    function detalhe() {
        if (!selecionada) return '';
        var r = dados.regioes[selecionada];
        var linhas = [];
        if (r.faixa) {
            var pl = plano(r);
            linhas.push('<b>Séries ' + (dados.semana.offset === 0 ? 'nesta semana' : 'na semana') + ':</b> ' + fmt(r.series)
                + (pl ? ' · ficha prevê ' + fmt(pl) : '') + ' · recomendado ' + r.faixa[0] + '–' + r.faixa[1]);
        }
        if (r.estado === 'pronto') linhas.push('<b>Recuperação:</b> pronto para treinar');
        else if (r.estado !== 'sem_treino') linhas.push('<b>Recuperação:</b> pronto em ' + duracao(r.horas_restantes) + (r.pronto_em ? ' (' + quando(r.pronto_em) + ')' : ''));
        linhas.push('<b>Último treino:</b> ' + (r.ultimo_treino ? diaSemana(r.ultimo_treino) + ', ' + dataCurta(r.ultimo_treino) : 'nenhum nos últimos 6 meses'));
        var ex = r.exercicios.slice(0, 4).map(function (e) {
            return '<li><span class="mm-ex-nome">' + esc(e.nome) + (e.papel === 'secundario' ? ' <small>secundário</small>' : '') + '</span>'
                + '<span class="mm-lista-num">' + (e.e1rm ? '<b>' + fmt(e.e1rm) + ' kg</b> · ' : '') + diaSemana(e.data) + ' ' + dataCurta(e.data) + '</span></li>';
        }).join('');
        return '<div class="mm-detalhe"><div class="mm-detalhe-topo"><span>' + esc(r.nome) + '</span>'
            + '<button type="button" class="mm-detalhe-fechar" aria-label="Fechar"><i class="bi bi-x-lg"></i></button></div>'
            + '<p>' + linhas.join('<br>') + '</p>'
            + (ex ? '<div class="mm-titulo">Exercícios (1RM estimado)</div><ul class="mm-lista mm-lista-ex">' + ex + '</ul>' : '') + '</div>';
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

    function classeDe(r) {
        if (aba === 'series') {
            var st = statusSeries(r);
            return st === 'fora' ? 'mm-c-vazio' : 'mm-s-' + (st === 'abaixo' ? 'faltando' : st);
        }
        return aba === 'fadiga' ? corRecuperacao(r) : corForca(r);
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

    // ---------------- topo de cada aba ----------------

    function montarTopo() {
        el('.mm-semana').hidden = aba !== 'series';
        var s = dados.semana;
        el('.mm-semana-rotulo').textContent = (s.offset === 0 ? 'Esta semana' : 'Semana') + ' · ' + dataCurta(s.inicio) + ' a ' + dataCurta(s.fim);
        el('.mm-semana-prox').disabled = s.offset >= 0;
        if (aba === 'series') {
            pergunta.textContent = 'Quantas séries cada músculo recebeu na semana, comparado com a sua ficha e com o recomendado.';
            resumo.innerHTML = resumoSeries();
            var falta = s.offset === 0 ? 'Faltando' : 'Abaixo';
            legenda.innerHTML = '<span><i class="mm-s-ok"></i>Na faixa</span><span><i class="mm-s-faltando"></i>' + falta + '</span>'
                + '<span><i class="mm-s-acima"></i>Acima</span><span><i class="mm-c-vazio"></i>Fora da ficha</span>';
        } else if (aba === 'fadiga') {
            pergunta.textContent = 'O que já descansou e pode ser treinado de novo.';
            resumo.innerHTML = resumoRecuperacao();
            legenda.innerHTML = '<span><i class="mm-f-fatigado"></i>Fatigado</span><span><i class="mm-f-recuperando"></i>Recuperando</span>'
                + '<span><i class="mm-f-pronto"></i>Pronto</span><span><i class="mm-c-vazio"></i>Não treinado</span>';
        } else {
            pergunta.textContent = 'Quanto você levanta em cada músculo (carga máxima estimada) e como isso evoluiu.';
            resumo.innerHTML = '';
            legenda.innerHTML = '<span><i class="mm-t-sobe"></i>Subindo</span><span><i class="mm-t-estavel"></i>Estável</span>'
                + '<span><i class="mm-t-cai"></i>Caindo</span><span><i class="mm-t-parado"></i>Parado</span><span><i class="mm-c-vazio"></i>Sem carga</span>';
        }
    }

    function render() {
        if (!dados) return;
        montarTopo();
        pintar();
        var lista = aba === 'series' ? listaSeries() : aba === 'fadiga' ? listaRecuperacao() : listaForca();
        painel.innerHTML = detalhe() + lista;
    }

    // ---------------- eventos ----------------

    function escolher(slug) {
        selecionada = selecionada === slug ? null : slug;
        render();
        if (selecionada) {
            var d = painel.querySelector('.mm-detalhe');
            if (d && d.getBoundingClientRect().top > window.innerHeight - 80) d.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
    vistas.addEventListener('click', function (e) {
        var g = e.target.closest('[data-r]');
        if (g) escolher(g.getAttribute('data-r'));
    });
    vistas.addEventListener('keydown', function (e) {
        var g = e.target.closest('[data-r]');
        if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); escolher(g.getAttribute('data-r')); }
    });
    resumo.addEventListener('click', function (e) {
        var t = e.target.closest('[data-r]');
        if (t) escolher(t.getAttribute('data-r'));
    });
    painel.addEventListener('click', function (e) {
        if (e.target.closest('.mm-mais')) { mostrarTodos = !mostrarTodos; render(); return; }
        if (e.target.closest('.mm-detalhe-fechar')) { selecionada = null; render(); return; }
        if (e.target.closest('.mm-treinos-ajustar')) {
            ajustandoTreinos = true; render();
            var c = painel.querySelector('.mm-treinos-semana');
            if (c) { c.focus(); c.select(); }
            return;
        }
        if (e.target.closest('.mm-treinos-ok')) { ajustandoTreinos = false; render(); return; }
        if (e.target.closest('.mm-peso-editar')) {
            blocoPeso.editando = true; render();
            var p = painel.querySelector('#mmPeso');
            if (p) p.focus();
            return;
        }
        var li = e.target.closest('li[data-r]');
        if (li) escolher(li.getAttribute('data-r'));
    });
    painel.addEventListener('input', function (e) {
        if (!e.target.classList.contains('mm-treinos-semana')) return;
        var n = parseFloat(String(e.target.value).replace(',', '.'));
        if (n > 0 && n <= 14) {
            treinosSemana = n;
            // atualiza resumo, corpo e barras sem perder o foco do campo
            montarTopo(); pintar();
            var lista = painel.querySelector('.mm-lista-series');
            if (lista) {
                var tmp = document.createElement('div');
                tmp.innerHTML = listaSeries();
                var nova = tmp.querySelector('.mm-lista-series');
                if (nova) lista.replaceWith(nova);
            }
        }
    });
    painel.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target.classList.contains('mm-treinos-semana')) {
            e.preventDefault(); ajustandoTreinos = false; render();
        }
    });
    painel.addEventListener('submit', function (e) {
        var form = e.target.closest('.mm-peso');
        if (!form) return;
        e.preventDefault();
        var campo = form.querySelector('#mmPeso'), msg = form.querySelector('.mm-peso-msg');
        var botao = form.querySelector('button');
        botao.disabled = true;
        msg.textContent = '';
        fetch('/api/peso-corporal', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ peso_kg: campo.value })
        }).then(function (r) { return r.json().then(function (j) { return [r.ok, j]; }); })
            .then(function (res) {
                if (!res[0]) { msg.textContent = res[1].erro || 'Não foi possível salvar.'; botao.disabled = false; return; }
                blocoPeso.editando = false;
                return carregarForca();
            })
            .catch(function () { msg.textContent = 'Sem conexão. Tente de novo.'; botao.disabled = false; });
    });
    raiz.querySelectorAll('.mm-aba').forEach(function (b) {
        b.addEventListener('click', function () {
            raiz.querySelectorAll('.mm-aba').forEach(function (x) {
                x.classList.toggle('is-ativo', x === b);
                x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
            });
            aba = b.dataset.aba;
            selecionada = null;
            mostrarTodos = false;
            render();
        });
    });
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
                    treinosSemana = j.planejado.sessoes_semana || j.planejado.treinos || null;
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
