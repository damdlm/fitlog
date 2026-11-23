/* ==========================================================
   Aviso de valor digitado errado (registrar treino).

   Um número muito fora do histórico costuma ser um dedo escorregado
   (300 no lugar de 30, 3 no lugar de 30). Ele vira a "última vez" que
   pré-preenche o próximo treino e um recorde falso nas estatísticas e
   no ranking. Antes de marcar o exercício como feito, e antes de salvar
   o treino, conferimos os valores e, se algum parece engano,
   perguntamos -- sem travar: "Está certo" segue normalmente.

   Referências (data-* no .exercise-row, de _linha_exercicio.html):
     data-recorde-carga / data-recorde-reps  maior carga / maior nº de
                                             reps já registrados
                                             (ExercicioService.
                                             get_recordes_em_lote)
     data-ultima-carga                       carga da última vez

   Regras (só com histórico; exercício novo nunca é questionado):
     carga  > 2 × recorde de carga e pelo menos 10 kg acima dele
     carga  < metade da última vez e pelo menos 10 kg abaixo dela
            (carga 0 não conta: exercício com peso do corpo)
     reps   > 2 × recorde de reps e pelo menos 10 acima dele

   Valores conferidos: os únicos (carga_/reps_) ou, no modo série a
   série (modo_series_<id> = "individual"), cada série até o número de
   séries escolhido. Um valor confirmado ("Está certo") não é
   perguntado de novo enquanto não mudar.

   window.FitLogValorSuspeito = {
     conferirAntesDeSalvar(continuar) -> true se pode salvar agora;
                                         false se abriu o aviso (e chama
                                         continuar() no "Está certo")
     suspeitasDaLinha(row)            -> lista de avisos (para testes)
   }
   ========================================================== */
(function () {
    'use strict';

    function num(v) {
        if (v === undefined || v === null || v === '') return null;
        const n = parseFloat(String(v).replace(',', '.'));
        return isNaN(n) ? null : n;
    }

    function fmtKg(n) {
        return (Math.round(n * 10) / 10).toLocaleString('pt-BR') + ' kg';
    }

    function nomeDe(row) {
        const el = row.querySelector('.exercicio-nome-trunc');
        return ((el && (el.dataset.fullNome || el.textContent)) || 'Exercício').trim();
    }

    function ativa(row) {
        if (row.classList.contains('is-desativado')) return false;
        if (row.classList.contains('exercise-row--cardio')) return false;
        const sw = row.querySelector('.exercicio-switch');
        return !sw || sw.checked;
    }

    // Valores digitados: [{serie (1..n ou null), carga, reps, campoCarga, campoReps}]
    function valoresDe(row) {
        const id = row.dataset.exercicioId;
        const wrap = row.closest('.exercise-row-wrap') || row.parentElement || document;
        const flag = wrap.querySelector('.modo-series-flag');
        const sel = row.querySelector('select[name^="num_series_"]');
        const nSeries = sel ? (parseInt(sel.value, 10) || 1) : 1;
        if (flag && flag.value === 'individual') {
            const box = wrap.querySelector('.series-individuais-inputs[data-exercicio-id="' + id + '"]');
            const out = [];
            for (let n = 1; box && n <= nSeries; n++) {
                const c = box.querySelector('.carga-serie-input[data-serie="' + n + '"]');
                const r = box.querySelector('.reps-serie-input[data-serie="' + n + '"]');
                out.push({ serie: n, carga: num(c && c.value), reps: num(r && r.value), campoCarga: c, campoReps: r });
            }
            return out;
        }
        const c = row.querySelector('.carga-input');
        const r = row.querySelector('.reps-input');
        return [{ serie: null, carga: num(c && c.value), reps: num(r && r.value), campoCarga: c, campoReps: r }];
    }

    function suspeitasDaLinha(row) {
        const recC = num(row.dataset.recordeCarga);
        const recR = num(row.dataset.recordeReps);
        const ultC = num(row.dataset.ultimaCarga);
        const avisos = [];
        valoresDe(row).forEach(function (v) {
            const onde = v.serie ? ' (série ' + v.serie + ')' : '';
            if (v.carga !== null && recC !== null && recC > 0 && v.carga > recC * 2 && v.carga - recC >= 10) {
                avisos.push({ campo: v.campoCarga, texto: fmtKg(v.carga) + onde + ' é mais que o dobro do seu recorde (' + fmtKg(recC) + ').' });
            } else if (v.carga !== null && v.carga > 0 && ultC !== null && v.carga < ultC / 2 && ultC - v.carga >= 10) {
                avisos.push({ campo: v.campoCarga, texto: fmtKg(v.carga) + onde + ' é menos da metade da última vez (' + fmtKg(ultC) + ').' });
            }
            if (v.reps !== null && recR !== null && recR > 0 && v.reps > recR * 2 && v.reps - recR >= 10) {
                avisos.push({ campo: v.campoReps, texto: v.reps + ' repetições' + onde + ' é mais que o dobro do seu máximo (' + recR + ').' });
            }
        });
        return avisos;
    }

    function assinatura(row) {
        return JSON.stringify(valoresDe(row).map(function (v) { return [v.carga, v.reps]; }));
    }

    function pendentes(rows) {
        const out = [];
        rows.forEach(function (row) {
            if (!ativa(row)) return;
            if (row.dataset.valorConfirmado && row.dataset.valorConfirmado === assinatura(row)) return;
            const avisos = suspeitasDaLinha(row);
            if (avisos.length) out.push({ row: row, avisos: avisos });
        });
        return out;
    }

    // ---------- modal ----------
    const modalEl = document.getElementById('modalValorSuspeito');
    let aoConfirmar = null;
    let alvoCorrigir = null;
    let confirmando = [];

    function mostrar(lista, continuar) {
        if (!modalEl || !window.bootstrap) { continuar(); return; }
        confirmando = lista;
        aoConfirmar = continuar;
        alvoCorrigir = lista[0];
        const corpo = modalEl.querySelector('[data-valor-suspeito-lista]');
        corpo.innerHTML = '';
        lista.slice(0, 4).forEach(function (item) {
            item.avisos.forEach(function (a) {
                const p = document.createElement('p');
                p.className = 'valor-suspeito-item';
                const b = document.createElement('strong');
                b.textContent = nomeDe(item.row) + ': ';
                p.appendChild(b);
                p.appendChild(document.createTextNode(a.texto));
                corpo.appendChild(p);
            });
        });
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    function focarCampo(item) {
        if (!item) return;
        const row = item.row;
        const aviso = item.avisos[0];
        const campo = aviso && aviso.campo;
        // Campo da tabela série a série (escondido): abre a tabela do exercício.
        if (campo && campo.closest('.series-individuais-inputs')) {
            const wrap = row.closest('.exercise-row-wrap');
            const seta = wrap && wrap.querySelector('.btn-series-toggle');
            if (seta) { seta.click(); return; }
        }
        const alvo = (campo && !campo.closest('.series-individuais-inputs')) ? campo : row.querySelector('.carga-input');
        if (alvo) {
            alvo.scrollIntoView({ block: 'center', behavior: 'smooth' });
            setTimeout(function () { alvo.focus(); if (alvo.select) alvo.select(); }, 250);
        }
    }

    if (modalEl) {
        modalEl.querySelector('[data-valor-suspeito-ok]').addEventListener('click', function () {
            confirmando.forEach(function (item) { item.row.dataset.valorConfirmado = assinatura(item.row); });
            const seguir = aoConfirmar;
            aoConfirmar = null;
            alvoCorrigir = null;
            bootstrap.Modal.getOrCreateInstance(modalEl).hide();
            if (seguir) seguir();
        });
        modalEl.querySelector('[data-valor-suspeito-corrigir]').addEventListener('click', function () {
            aoConfirmar = null;
            bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        });
        modalEl.addEventListener('hidden.bs.modal', function () {
            const item = alvoCorrigir;
            alvoCorrigir = null;
            aoConfirmar = null;
            focarCampo(item);
        });
    }

    // ---------- ao marcar o exercício como feito ----------
    // Na captura: roda antes do handler do botão (que para a propagação).
    document.addEventListener('click', function (evt) {
        const btn = evt.target.closest && evt.target.closest('.exercise-row .btn-marcar-feito');
        if (!btn || btn.classList.contains('is-ativo')) return; // desmarcar não pergunta
        const row = btn.closest('.exercise-row');
        const lista = pendentes([row]);
        if (!lista.length) return;
        evt.preventDefault();
        evt.stopImmediatePropagation();
        mostrar(lista, function () { btn.click(); });
    }, true);

    window.FitLogValorSuspeito = {
        conferirAntesDeSalvar: function (continuar) {
            const lista = pendentes(Array.from(document.querySelectorAll('.exercise-row[data-exercicio-id]')));
            if (!lista.length) return true;
            mostrar(lista, continuar);
            return false;
        },
        suspeitasDaLinha: suspeitasDaLinha
    };
})();
