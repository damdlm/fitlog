(function () {
    'use strict';

    var formatador = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

    function formatarCentavos(centavos) {
        if (centavos === null || centavos === undefined) return '--';
        return formatador.format(centavos / 100);
    }

    var LABELS_FORMA = { cartao: 'Cartão de crédito', pix: 'Pix', desconhecida: 'Não identificada' };
    var LABELS_TIPO = { aluno: 'Aluno', professor: 'Professor', desconhecido: 'Não identificado' };

    function renderLista(elId, linhas, labelMap) {
        var el = document.getElementById(elId);
        if (!linhas || linhas.length === 0) {
            el.innerHTML = '<div class="fin-empty">Sem pagamentos no período.</div>';
            return;
        }
        var maior = Math.max.apply(null, linhas.map(function (l) { return l.total_centavos; }));
        el.innerHTML = linhas.map(function (linha) {
            var rotulo = (labelMap && labelMap[linha.chave]) || linha.nome || linha.chave;
            var pct = maior > 0 ? Math.max(4, Math.round((linha.total_centavos / maior) * 100)) : 0;
            return '' +
                '<div class="fin-report-row">' +
                '  <div class="fin-report-row-top">' +
                '    <span class="fin-report-row-label">' + rotulo + '<span class="fin-report-row-qtd">' + linha.qtd + 'x</span></span>' +
                '    <span class="fin-report-row-value">' + formatarCentavos(linha.total_centavos) + '</span>' +
                '  </div>' +
                '  <div class="fin-bar-track"><div class="fin-bar-fill" style="width:' + pct + '%"></div></div>' +
                '</div>';
        }).join('');
    }

    function mostrarErro(msg) {
        var el = document.getElementById('fin-erro');
        el.textContent = msg;
        el.classList.remove('d-none');
    }

    function limparErro() {
        document.getElementById('fin-erro').classList.add('d-none');
    }

    function carregar(dataInicio, dataFim) {
        limparErro();
        var url = window.FIN_API_URL + '?data_inicio=' + encodeURIComponent(dataInicio) + '&data_fim=' + encodeURIComponent(dataFim);

        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function (resp) {
                if (resp.status === 401) {
                    window.location.href = window.FIN_LOGIN_URL;
                    return null;
                }
                return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
            })
            .then(function (result) {
                if (!result) return;
                if (!result.ok) {
                    mostrarErro(result.data.erro || 'Não foi possível carregar os dados.');
                    return;
                }
                var resumo = result.data.resumo;
                var saldo = result.data.saldo;

                document.getElementById('fin-total-bruto').textContent = formatarCentavos(resumo.total_bruto_centavos);
                document.getElementById('fin-qtd-pagamentos').textContent = resumo.qtd_pagamentos + ' pagamento(s)';
                document.getElementById('fin-total-taxa').textContent = formatarCentavos(resumo.total_taxa_centavos);
                document.getElementById('fin-qtd-sem-taxa').textContent = resumo.qtd_sem_taxa_conhecida > 0
                    ? resumo.qtd_sem_taxa_conhecida + ' sem taxa informada'
                    : 'todos com taxa informada';
                document.getElementById('fin-total-liquido').textContent = formatarCentavos(resumo.total_liquido_centavos);

                var saldoEl = document.getElementById('fin-saldo-asaas');
                saldoEl.textContent = saldo.erro ? 'indisponível' : formatarCentavos(saldo.saldo_centavos);

                renderLista('fin-lista-forma', resumo.por_forma_pagamento, LABELS_FORMA);
                renderLista('fin-lista-plano', resumo.por_plano, null);
                renderLista('fin-lista-tipo', resumo.por_tipo_usuario, LABELS_TIPO);
            })
            .catch(function () {
                mostrarErro('Erro de conexão ao carregar os dados financeiros.');
            });
    }

    function marcarPresetAtivo(botao) {
        document.querySelectorAll('.fin-preset').forEach(function (b) { b.classList.remove('active'); });
        if (botao) botao.classList.add('active');
    }

    function aplicarPreset(preset, botao) {
        var hoje = new Date();
        var inicio, fim;
        if (preset === 'mes-atual') {
            inicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
            fim = hoje;
        } else if (preset === 'mes-passado') {
            inicio = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
            fim = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
        } else {
            fim = hoje;
            inicio = new Date(hoje);
            inicio.setDate(inicio.getDate() - 30);
        }
        document.getElementById('fin-data-inicio').value = paraISO(inicio);
        document.getElementById('fin-data-fim').value = paraISO(fim);
        marcarPresetAtivo(botao);
        carregar(paraISO(inicio), paraISO(fim));
    }

    function paraISO(data) {
        return data.toISOString().slice(0, 10);
    }

    document.getElementById('fin-filtro-form').addEventListener('submit', function (e) {
        e.preventDefault();
        marcarPresetAtivo(null);
        carregar(document.getElementById('fin-data-inicio').value, document.getElementById('fin-data-fim').value);
    });

    document.querySelectorAll('.fin-preset').forEach(function (btn) {
        btn.addEventListener('click', function () {
            aplicarPreset(btn.getAttribute('data-preset'), btn);
        });
    });

    carregar(window.FIN_DATAS_PADRAO.inicio, window.FIN_DATAS_PADRAO.fim);
})();
