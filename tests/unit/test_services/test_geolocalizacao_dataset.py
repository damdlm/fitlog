"""O dataset de municípios é carregado em produção a cada processo; um JSON
malformado derrubou /api/professores/mapa/buscar-cidade em 01/10 (500) sem
nenhum teste pegar. Estes testes falham antes do deploy."""
from services.geolocalizacao_service import GeolocalizacaoService

CHAVES = {'nome', 'uf', 'lat', 'lng', 'capital', 'busca'}


def _carregar():
    GeolocalizacaoService._cidades_br_cache = None
    return GeolocalizacaoService._cidades_br()


def test_dataset_carrega_como_lista_com_todos_os_municipios():
    cidades = _carregar()
    assert isinstance(cidades, list)
    assert len(cidades) > 5000


def test_todo_registro_tem_o_formato_esperado():
    for c in _carregar():
        assert isinstance(c, dict) and set(c) == CHAVES, c
        assert isinstance(c['busca'], str) and c['busca'] == c['busca'].lower()
        assert isinstance(c['capital'], bool)
        assert -35 < c['lat'] < 6 and -75 < c['lng'] < -30, c


def test_busca_por_prefixo_funciona_de_ponta_a_ponta(app):
    GeolocalizacaoService._cidades_br_cache = None
    nomes = [c['nome'] for c in GeolocalizacaoService.buscar_cidades('sao pau')]
    assert 'São Paulo' in nomes