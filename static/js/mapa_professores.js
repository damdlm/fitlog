/**
 * Mapa de professores do FitLog (/aluno/mapa).
 * Busca por área visível (bounding box) e agrupa em bolhas quando o
 * zoom está afastado. O popup de cada professor só tem "Visualizar"
 * (abre o modal da página do professor); o pedido de vínculo
 * (aluno.enviar_solicitacao) fica no rodapé desse modal.
 */
(function () {
    'use strict';

    var limitesBrasil = [[-34.0, -74.5], [5.5, -32.0]];
    var limitesNavegacao = [[-40, -80], [10, -26]];
    var esperaMs = 250;

    var mapa = L.map('mapa', {
        minZoom: 4,
        maxBounds: limitesNavegacao,
        maxBoundsViscosity: 0.8
    });
    mapa.fitBounds(limitesBrasil);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap'
    }).addTo(mapa);

    var camada = L.layerGroup().addTo(mapa);
    var mensagem = document.getElementById('msg');
    var temporizador = null;
    var idRequisicao = 0;

    function escapar(texto) {
        var div = document.createElement('div');
        div.textContent = texto;
        return div.innerHTML;
    }

    function classeCluster(total) {
        // Mesmos limiares do _defaultIconCreateFunction do plugin oficial
        if (total < 10) { return 'marker-cluster-small'; }
        if (total < 100) { return 'marker-cluster-medium'; }
        return 'marker-cluster-large';
    }

    function criarBolha(item) {
        var icone = L.divIcon({
            html: '<div><span>' + item.total + '</span></div>',
            className: 'marker-cluster ' + classeCluster(item.total),
            iconSize: [40, 40]
        });
        return L.marker([item.lat, item.lng], { icon: icone }).on('click', function () {
            mapa.setView([item.lat, item.lng], Math.min(mapa.getZoom() + 2, 18));
        });
    }

    function htmlAvatar(prof) {
        if (prof.foto) {
            return '<img class="mapa-prof__avatar" src="' + escapar(prof.foto) + '" alt="" loading="lazy"' +
                (prof.foto_posicao ? ' style="object-position: ' + escapar(prof.foto_posicao) + '"' : '') + '>';
        }
        return '<span class="mapa-prof__avatar mapa-prof__avatar--iniciais" aria-hidden="true">' +
               escapar(prof.iniciais || '?') + '</span>';
    }

    function criarPino(item) {
        var html = item.professores.map(function (prof) {
            var local = prof.cidade
                ? '<div class="mapa-prof__local"><i class="bi bi-geo-alt-fill"></i> ' +
                  escapar(prof.cidade) + (prof.uf ? '/' + escapar(prof.uf) : '') + '</div>'
                : '';
            // O pedido de vínculo não fica mais aqui: vive no rodapé do
            // modal que este botão abre (templates/professor/_modal_ver_pagina.html),
            // que descobre qual professor é pelos data-professor-* abaixo.
            var botao = prof.slug
                ? '<button type="button" class="mapa-prof__btn" ' +
                  'data-bs-toggle="modal" data-bs-target="#ppVerPaginaModal" ' +
                  'data-professor-slug="' + escapar(prof.slug) + '" ' +
                  'data-professor-id="' + escapar(String(prof.id)) + '">' +
                  '<i class="bi bi-eye"></i> Visualizar</button>'
                : '<span class="mapa-prof__indisponivel">Perfil ainda indisponível</span>';
            return (
                '<div class="mapa-prof">' +
                htmlAvatar(prof) +
                '<div class="mapa-prof__nome">' + escapar(prof.nome) + '</div>' +
                local + botao +
                '</div>'
            );
        }).join('');
        return L.marker([item.lat, item.lng]).bindPopup(html, {
            minWidth: 200,
            maxWidth: 260,
            className: 'mapa-popup'
        });
    }

    function carregar() {
        var b = mapa.getBounds();
        var id = ++idRequisicao;
        var params = new URLSearchParams({
            sul: b.getSouth(),
            oeste: b.getWest(),
            norte: b.getNorth(),
            leste: b.getEast(),
            zoom: mapa.getZoom()
        });

        fetch('/api/professores/mapa?' + params.toString())
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                if (id !== idRequisicao) { return; }
                camada.clearLayers();
                if (dados.erro) { mensagem.textContent = dados.erro; return; }

                var total = 0;
                dados.itens.forEach(function (item) {
                    if (item.tipo === 'cluster') {
                        total += item.total;
                        criarBolha(item).addTo(camada);
                    } else {
                        total += item.professores.length;
                        criarPino(item).addTo(camada);
                    }
                });
                mensagem.textContent = total
                    ? total + ' professor(es) nesta área'
                    : 'Nenhum professor nesta área ainda.';
            })
            .catch(function () {
                if (id === idRequisicao) { mensagem.textContent = 'Erro de conexão'; }
            });
    }

    mapa.on('moveend', function () {
        clearTimeout(temporizador);
        temporizador = setTimeout(carregar, esperaMs);
    });
    carregar();

    // Busca por cidade -- lista local dos municípios do IBGE
    // (routes/api_routes.py:api_mapa_buscar_cidade), não um serviço
    // externo: mais rápido, sem rate-limit, e cada sugestão já vem
    // marcada se tem professor visível no mapa ali ou não. Dispara
    // sozinha a partir de 4 letras (com debounce), sem precisar
    // apertar Enter; Enter escolhe a primeira sugestão da lista.
    var formBusca = document.getElementById('mapaBuscaCidadeForm');
    var inputBusca = document.getElementById('mapaBuscaCidadeInput');
    var resultadosBusca = document.getElementById('mapaBuscaResultados');
    var erroBusca = document.getElementById('mapa-busca-erro');
    var ZOOM_CIDADE = 12;
    var MIN_CARACTERES_BUSCA = 4;
    var ESPERA_BUSCA_MS = 300;
    var temporizadorBusca = null;
    var idBuscaCidade = 0;
    var ultimasSugestoes = [];

    function fecharResultadosBusca() {
        resultadosBusca.innerHTML = '';
        resultadosBusca.style.display = 'none';
        ultimasSugestoes = [];
    }

    function escolherCidade(cidade) {
        mapa.setView([cidade.lat, cidade.lng], ZOOM_CIDADE);
        inputBusca.value = cidade.nome + '/' + cidade.uf;
        fecharResultadosBusca();
    }

    function renderizarSugestoes(cidades) {
        ultimasSugestoes = cidades;
        if (!cidades.length) {
            resultadosBusca.innerHTML = '<div class="mapa-busca-vazio">Nenhuma cidade encontrada</div>';
            resultadosBusca.style.display = 'block';
            return;
        }
        resultadosBusca.innerHTML = cidades.map(function (cidade, i) {
            var pontoClasse = cidade.tem_professor ? 'mapa-busca-dot--com' : 'mapa-busca-dot--sem';
            var titulo = cidade.tem_professor ? 'Tem professor' : 'Sem professor ainda';
            return (
                '<button type="button" class="mapa-busca-item" data-indice="' + i + '">' +
                '<span class="mapa-busca-dot ' + pontoClasse + '" title="' + titulo + '"></span>' +
                escapar(cidade.nome) + '/' + escapar(cidade.uf) +
                '</button>'
            );
        }).join('');
        resultadosBusca.style.display = 'block';
    }

    function buscarCidade(texto) {
        texto = texto.trim();
        if (!texto) { fecharResultadosBusca(); return; }

        var id = ++idBuscaCidade;
        erroBusca.style.display = 'none';
        fetch('/api/professores/mapa/buscar-cidade?q=' + encodeURIComponent(texto))
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                if (id !== idBuscaCidade) { return; } // o usuário já digitou outra coisa
                renderizarSugestoes(dados.cidades || []);
            })
            .catch(function () {
                if (id === idBuscaCidade) {
                    erroBusca.textContent = 'Erro de conexão';
                    erroBusca.style.display = 'block';
                }
            });
    }

    if (formBusca && inputBusca && resultadosBusca) {
        formBusca.addEventListener('submit', function (ev) {
            ev.preventDefault();
            if (ultimasSugestoes.length) { escolherCidade(ultimasSugestoes[0]); }
        });

        inputBusca.addEventListener('input', function () {
            clearTimeout(temporizadorBusca);
            var texto = inputBusca.value.trim();
            if (texto.length < MIN_CARACTERES_BUSCA) { fecharResultadosBusca(); return; }
            temporizadorBusca = setTimeout(function () { buscarCidade(texto); }, ESPERA_BUSCA_MS);
        });

        resultadosBusca.addEventListener('click', function (ev) {
            var botao = ev.target.closest('.mapa-busca-item');
            if (!botao) { return; }
            var cidade = ultimasSugestoes[Number(botao.dataset.indice)];
            if (cidade) { escolherCidade(cidade); }
        });

        document.addEventListener('click', function (ev) {
            if (!formBusca.contains(ev.target) && !resultadosBusca.contains(ev.target)) {
                fecharResultadosBusca();
            }
        });
    }
})();