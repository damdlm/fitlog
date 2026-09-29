/**
 * Mapa de professores do FitLog (/aluno/mapa).
 * Busca por área visível (bounding box) e agrupa em bolhas quando o
 * zoom está afastado. O popup de cada professor usa o mesmo endpoint
 * aluno.enviar_solicitacao já usado em buscar_professores.html.
 */
(function () {
    'use strict';

    var limitesBrasil = [[-34.0, -74.5], [5.5, -32.0]];
    var limitesNavegacao = [[-40, -80], [10, -26]];
    var esperaMs = 250;

    // window.FITLOG_MAPA_URL_SOLICITACAO vem do template com professor_id=0;
    // trocamos o "0" final pelo id real de cada professor.
    var urlSolicitacaoBase = window.FITLOG_MAPA_URL_SOLICITACAO || '';
    var csrfToken = window.FITLOG_MAPA_CSRF_TOKEN || '';

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

    function urlSolicitacao(professorId) {
        return urlSolicitacaoBase.replace(/\/0(?:$|\?)/, '/' + professorId);
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

    function criarPino(item) {
        var html = item.professores.map(function (prof) {
            var linkPerfil = prof.slug
                ? ' &middot; <a href="/professor/pagina/' + encodeURIComponent(prof.slug) + '" target="_blank">ver perfil</a>'
                : '';
            var cidadeUf = prof.cidade
                ? '<br><small class="text-muted">' + escapar(prof.cidade) + (prof.uf ? '/' + escapar(prof.uf) : '') + '</small>'
                : '';
            return (
                '<div class="mb-2">' +
                '<b>' + escapar(prof.nome) + '</b>' + linkPerfil + cidadeUf + '<br>' +
                '<form method="post" action="' + urlSolicitacao(prof.id) + '" class="mt-1">' +
                '<input type="hidden" name="csrf_token" value="' + csrfToken + '">' +
                '<button type="submit" class="btn btn-sm btn-primary">' +
                '<i class="bi bi-person-plus"></i> Solicitar vínculo</button>' +
                '</form></div>'
            );
        }).join('');
        return L.marker([item.lat, item.lng]).bindPopup(html);
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
                    if (dados.modo === 'clusters') {
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
})();