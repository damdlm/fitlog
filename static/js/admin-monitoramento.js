/**
 * Painel de monitoramento admin (/admin/monitoramento).
 * Renderiza os dados iniciais vindos do servidor e depois atualiza
 * via polling em window.MON_API_URL a cada MON_INTERVALO_MS.
 *
 * Cada bloco (processo/banco/cache/negocio) é tratado de forma
 * independente: se uma fonte estiver indisponível (ex: Redis fora do
 * ar), só aquele card mostra o aviso -- o resto do painel continua
 * atualizando normalmente.
 */
(function () {
    "use strict";

    const MON_INTERVALO_MS = 10000;
    // Histórico é 24h de dados -- não precisa (nem faz sentido) atualizar
    // no mesmo ritmo do resto do painel.
    const MON_HISTORICO_INTERVALO_MS = 5 * 60 * 1000;

    function formatarBytes(mb) {
        if (mb === null || mb === undefined) return "--";
        if (mb >= 1024) return (mb / 1024).toFixed(1) + " GB";
        return mb.toFixed(1) + " MB";
    }

    function formatarDuracao(segundos) {
        if (segundos === null || segundos === undefined) return "--";
        const h = Math.floor(segundos / 3600);
        const m = Math.floor((segundos % 3600) / 60);
        if (h > 0) return `${h}h ${m}min`;
        return `${m}min`;
    }

    function formatarPct(valor) {
        return (valor === null || valor === undefined) ? "--" : valor.toFixed(1) + "%";
    }

    function setBar(barId, valorId, pct, textoOverride) {
        const bar = document.getElementById(barId);
        const val = document.getElementById(valorId);
        const pctSeguro = Math.max(0, Math.min(100, pct || 0));
        if (bar) {
            bar.style.width = pctSeguro + "%";
            bar.classList.toggle("bg-danger", pctSeguro >= 90);
        }
        if (val) val.textContent = textoOverride !== undefined ? textoOverride : formatarPct(pct);
    }

    function alternarIndisponivel(prefixo, indisponivel, erro) {
        const avisoEl = document.getElementById(`mon-${prefixo}-indisponivel`);
        const conteudoEl = document.getElementById(`mon-${prefixo}-conteudo`);
        const erroEl = document.getElementById(`mon-${prefixo}-erro`);
        if (avisoEl) avisoEl.classList.toggle("d-none", !indisponivel);
        if (conteudoEl) conteudoEl.classList.toggle("d-none", !!indisponivel);
        if (erroEl && erro) erroEl.textContent = erro;
    }

    function renderizarProcesso(p) {
        if (!p || !p.disponivel) {
            alternarIndisponivel("processo", true, p && p.erro);
            return;
        }
        alternarIndisponivel("processo", false);
        setBar("mon-cpu-processo-bar", "mon-cpu-processo-val", p.cpu_processo_pct);
        setBar("mon-cpu-sistema-bar", "mon-cpu-sistema-val", p.cpu_sistema_pct);
        setBar("mon-mem-sistema-bar", "mon-mem-sistema-val", p.memoria_sistema_usada_pct);
        document.getElementById("mon-mem-processo-val").textContent = formatarBytes(p.memoria_processo_mb);
        document.getElementById("mon-threads-val").textContent = p.num_threads ?? "--";
        document.getElementById("mon-uptime-val").textContent = formatarDuracao(p.uptime_segundos);
        document.getElementById("mon-pid-val").textContent = p.pid ?? "--";

        const badge = document.getElementById("mon-num-workers");
        if (badge) {
            const n = p.num_workers ?? 0;
            badge.textContent = n === 1 ? "1 worker" : `${n} workers`;
        }

        const tbody = document.getElementById("mon-workers-tbody");
        if (tbody) {
            const workers = p.workers || [];
            if (workers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-muted">nenhum worker encontrado</td></tr>';
            } else {
                tbody.innerHTML = workers.map(w => {
                    const destaque = w.pid === p.pid ? ' <span class="badge bg-light text-dark border">este</span>' : '';
                    return `<tr>
                        <td>${w.pid}${destaque}</td>
                        <td class="text-end">${formatarPct(w.cpu_pct)}</td>
                        <td class="text-end">${formatarBytes(w.memoria_mb)}</td>
                        <td class="text-end">${w.threads ?? "--"}</td>
                    </tr>`;
                }).join("");
            }
        }
    }

    function renderizarBanco(b) {
        if (!b || !b.disponivel) {
            alternarIndisponivel("banco", true, b && b.erro);
            return;
        }
        alternarIndisponivel("banco", false);
        document.getElementById("mon-db-dialeto").textContent = b.dialeto ?? "--";
        document.getElementById("mon-db-tamanho").textContent = formatarBytes(b.tamanho_mb);

        if (b.dialeto === "postgresql") {
            document.getElementById("mon-db-conexoes").textContent =
                `${b.conexoes_total ?? "--"} / ${b.conexoes_ativas ?? "--"}`;
            document.getElementById("mon-db-max-conexoes").textContent = b.max_conexoes ?? "--";
            document.getElementById("mon-db-hit-ratio").textContent = formatarPct(b.cache_hit_ratio_pct);
        } else {
            document.getElementById("mon-db-conexoes").textContent = "n/d (SQLite)";
            document.getElementById("mon-db-max-conexoes").textContent = "n/d";
            document.getElementById("mon-db-hit-ratio").textContent = "n/d";
        }

        const pool = b.pool || {};
        document.getElementById("mon-db-pool").textContent =
            `${pool.em_uso ?? "--"} / ${pool.tamanho ?? "--"} / ${pool.overflow ?? "--"}`;
    }

    function renderizarCache(c) {
        if (!c || !c.disponivel) {
            alternarIndisponivel("cache", true, c && c.erro);
            return;
        }
        alternarIndisponivel("cache", false);
        document.getElementById("mon-cache-versao").textContent = c.versao_redis ?? "--";
        document.getElementById("mon-cache-memoria").textContent =
            `${formatarBytes(c.memoria_usada_mb)} (pico ${formatarBytes(c.memoria_pico_mb)})`;
        document.getElementById("mon-cache-clientes").textContent = c.clientes_conectados ?? "--";
        document.getElementById("mon-cache-chaves").textContent = c.total_chaves ?? "n/d";
        document.getElementById("mon-cache-hitrate").textContent =
            c.hit_rate_pct !== null && c.hit_rate_pct !== undefined ? formatarPct(c.hit_rate_pct) : "n/d";
        document.getElementById("mon-cache-uptime").textContent = formatarDuracao(c.uptime_segundos);
    }

    function renderizarRailway(r) {
        if (!r || !r.disponivel) {
            alternarIndisponivel("railway", true, r && r.erro);
            return;
        }
        alternarIndisponivel("railway", false);
        const tbody = document.getElementById("mon-railway-tbody");
        if (!tbody) return;
        const servicos = r.servicos || [];
        if (servicos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-muted">nenhum serviço configurado</td></tr>';
            return;
        }
        tbody.innerHTML = servicos.map(s => {
            if (!s.disponivel) {
                return `<tr><td>${s.nome}</td><td colspan="2" class="text-muted small">${s.erro || "indisponível"}</td></tr>`;
            }
            const cpu = s.cpu_vcpu !== null && s.cpu_vcpu !== undefined ? s.cpu_vcpu.toFixed(2) + " vCPU" : "--";
            const mem = s.memoria_gb !== null && s.memoria_gb !== undefined ? s.memoria_gb.toFixed(2) + " GB" : "--";
            return `<tr><td>${s.nome}</td><td class="text-end">${cpu}</td><td class="text-end">${mem}</td></tr>`;
        }).join("");
    }

    function renderizarFitbot(f) {
        if (!f || !f.disponivel) {
            alternarIndisponivel("fitbot", true, f && f.erro);
            return;
        }
        alternarIndisponivel("fitbot", false);
        const tbody = document.getElementById("mon-fitbot-tbody");
        if (!tbody) return;
        const provedores = f.provedores || [];
        if (provedores.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted">nenhuma chamada nas últimas 24h</td></tr>';
            return;
        }
        tbody.innerHTML = provedores.map(p => {
            const sucesso = p.taxa_sucesso_pct !== null && p.taxa_sucesso_pct !== undefined
                ? `${formatarPct(p.taxa_sucesso_pct)} <span class="text-muted">(${p.falhas} falha${p.falhas === 1 ? "" : "s"})</span>`
                : "--";
            const latencia = p.duracao_media_ms !== null && p.duracao_media_ms !== undefined ? `${p.duracao_media_ms} ms` : "--";
            const tokens = (p.tokens_entrada || p.tokens_saida) ? `${p.tokens_entrada || 0} / ${p.tokens_saida || 0}` : "n/d";
            return `<tr>
                <td>${p.provedor}</td>
                <td class="text-end">${p.chamadas}</td>
                <td class="text-end">${sucesso}</td>
                <td class="text-end">${latencia}</td>
                <td class="text-end">${tokens}</td>
            </tr>`;
        }).join("");
    }

    /**
     * Sparkline simples em SVG puro (sem lib de gráfico) -- monta uma
     * polyline normalizada pro viewBox 0..300 x 0..60. `serie` é um
     * array de números (null é ignorado). Propositalmente minimalista:
     * é só pra dar uma ideia de tendência, não um gráfico analítico.
     */
    function desenharSparkline(svgId, serie) {
        const svg = document.getElementById(svgId);
        if (!svg) return;
        const valores = serie.filter(v => v !== null && v !== undefined && !isNaN(v));
        if (valores.length < 2) {
            svg.innerHTML = "";
            return;
        }
        const min = Math.min(...valores);
        const max = Math.max(...valores);
        const amplitude = (max - min) || 1;
        const passoX = 300 / (serie.length - 1);

        const pontos = serie.map((v, i) => {
            if (v === null || v === undefined || isNaN(v)) return null;
            const x = i * passoX;
            const y = 58 - ((v - min) / amplitude) * 56;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).filter(Boolean);

        svg.innerHTML = `<polyline points="${pontos.join(" ")}"></polyline>`;
    }

    async function atualizarHistorico() {
        if (!window.MON_HISTORICO_API_URL) return;
        try {
            const resp = await fetch(window.MON_HISTORICO_API_URL + "?horas=24", {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!resp.ok) throw new Error("resposta HTTP " + resp.status);
            const dados = await resp.json();
            const pontos = (dados && dados.pontos) || [];

            const semDados = document.getElementById("mon-historico-indisponivel");
            const comDados = document.getElementById("mon-historico-conteudo");
            if (pontos.length < 2) {
                if (semDados) semDados.classList.remove("d-none");
                if (comDados) comDados.classList.add("d-none");
                return;
            }
            if (semDados) semDados.classList.add("d-none");
            if (comDados) comDados.classList.remove("d-none");

            desenharSparkline("mon-spark-cpu", pontos.map(p => p.cpu_processo_pct));
            desenharSparkline("mon-spark-mem", pontos.map(p => p.memoria_sistema_usada_pct));
            desenharSparkline("mon-spark-db", pontos.map(p => p.db_conexoes_ativas));
            desenharSparkline("mon-spark-cache", pontos.map(p => p.cache_hit_rate_pct));
        } catch (e) {
            console.error("[monitoramento] falha ao carregar histórico:", e);
        }
    }

    function renderizarNegocio(n) {
        if (!n || !n.disponivel) {
            alternarIndisponivel("negocio", true, n && n.erro);
            return;
        }
        alternarIndisponivel("negocio", false);
        document.getElementById("mon-total-usuarios").textContent = n.total_usuarios ?? "--";
        document.getElementById("mon-total-alunos").textContent = n.total_alunos ?? "--";
        document.getElementById("mon-total-professores").textContent = n.total_professores ?? "--";
        document.getElementById("mon-total-treinos").textContent = n.total_treinos ?? "--";
        document.getElementById("mon-registros-hoje").textContent = n.registros_hoje ?? "--";
        document.getElementById("mon-assinaturas-ativas").textContent = n.assinaturas_ativas ?? "--";
        document.getElementById("mon-assinaturas-trial").textContent = n.assinaturas_trial ?? "--";
        document.getElementById("mon-assinaturas-inadimplentes").textContent = n.assinaturas_inadimplentes ?? "--";
    }

    /**
     * Roda fn isoladamente: se um bloco (ex: cache) lançar uma
     * exceção -- por um dado inesperado vindo da API -- os demais
     * blocos continuam atualizando normalmente. Sem isso, um erro no
     * meio de renderizarTudo() travava tudo que vinha depois dele.
     */
    function renderizarBlocoSeguro(fn, rotulo) {
        try {
            fn();
        } catch (e) {
            console.error(`[monitoramento] falha ao renderizar bloco "${rotulo}":`, e);
        }
    }

    function renderizarTudo(metricas) {
        renderizarBlocoSeguro(() => renderizarProcesso(metricas.processo), "processo");
        renderizarBlocoSeguro(() => renderizarBanco(metricas.banco), "banco");
        renderizarBlocoSeguro(() => renderizarCache(metricas.cache), "cache");
        renderizarBlocoSeguro(() => renderizarRailway(metricas.railway), "railway");
        renderizarBlocoSeguro(() => renderizarFitbot(metricas.fitbot), "fitbot");
        renderizarBlocoSeguro(() => renderizarNegocio(metricas.negocio), "negocio");

        const atualizadoEm = document.getElementById("mon-atualizado-em");
        if (atualizadoEm) {
            const agora = new Date();
            atualizadoEm.textContent = agora.toLocaleTimeString("pt-BR");
        }
    }

    function marcarStatus(online) {
        const el = document.getElementById("mon-status");
        if (!el) return;
        el.classList.toggle("bg-success", online);
        el.classList.toggle("bg-secondary", !online);
        el.innerHTML = online
            ? '<i class="bi bi-broadcast"></i> ao vivo'
            : '<i class="bi bi-exclamation-triangle"></i> sem atualização';
    }

    async function atualizar() {
        try {
            const resp = await fetch(window.MON_API_URL, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!resp.ok) throw new Error("resposta HTTP " + resp.status);
            const dados = await resp.json();
            renderizarTudo(dados);
            marcarStatus(true);
        } catch (e) {
            marcarStatus(false);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.MON_METRICAS_INICIAIS) {
            renderizarTudo(window.MON_METRICAS_INICIAIS);
        }
        setInterval(atualizar, MON_INTERVALO_MS);

        atualizarHistorico();
        setInterval(atualizarHistorico, MON_HISTORICO_INTERVALO_MS);
    });
})();