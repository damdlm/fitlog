"""
Testes unitários de services/financeiro_service.py (painel financeiro do admin).

- resumo_periodo: agregação SOBRE O BANCO LOCAL (tabela pagamentos_recebidos).
- obter_saldo_asaas / obter_taxas_conta_asaas: chamadas à API do Asaas, aqui
  SEMPRE mockadas (requests.get substituído) -- nenhum teste sai pra rede.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from models import db, PagamentoRecebido, Plano
from services import financeiro_service
from services.financeiro_service import FinanceiroService


def _dt(dia, hora=12, minuto=0, segundo=0, mes=3):
    return datetime(2026, mes, dia, hora, minuto, segundo, tzinfo=timezone.utc)


def _add(gw, bruto, quando, plano='aluno_fit', forma='pix', tipo='aluno', taxa=None, liquido=None):
    db.session.add(PagamentoRecebido(
        gateway_payment_id=gw, plano_codigo=plano, tipo_usuario=tipo, forma_pagamento=forma,
        valor_bruto_centavos=bruto, taxa_asaas_centavos=taxa, valor_liquido_centavos=liquido,
        confirmado_em=quando,
    ))
    db.session.commit()


@pytest.fixture
def planos(app):
    db.session.add_all([
        Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=1990),
        Plano(codigo='professor_pro', nome='Plano Pro', tipo_usuario='professor', preco_centavos=4990),
    ])
    db.session.commit()


# ------------------------------------------------------------------
# resumo_periodo
# ------------------------------------------------------------------

class TestResumoPeriodo:

    def test_periodo_vazio_retorna_zeros_e_listas_vazias(self, app):
        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r == {
            'total_bruto_centavos': 0, 'total_taxa_centavos': 0, 'total_liquido_centavos': 0,
            'qtd_pagamentos': 0, 'qtd_sem_taxa_conhecida': 0,
            'por_forma_pagamento': [], 'por_plano': [], 'por_tipo_usuario': [],
        }

    def test_totais_somam_bruto_taxa_e_liquido(self, app, planos):
        _add('p1', 2000, _dt(5), taxa=100, liquido=1900)
        _add('p2', 5000, _dt(6), taxa=250, liquido=4750)

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r['qtd_pagamentos'] == 2
        assert r['total_bruto_centavos'] == 7000
        assert r['total_taxa_centavos'] == 350
        assert r['total_liquido_centavos'] == 6650
        assert r['qtd_sem_taxa_conhecida'] == 0

    def test_pagamento_sem_taxa_entra_no_bruto_mas_nao_na_taxa(self, app, planos):
        """Webhook sem netValue: conta no bruto, fica fora de taxa/líquido e
        é sinalizado em qtd_sem_taxa_conhecida (total pago ao Asaas pode
        estar subestimado)."""
        _add('p1', 2000, _dt(5), taxa=100, liquido=1900)
        _add('p2', 3000, _dt(6), taxa=None, liquido=None)

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r['total_bruto_centavos'] == 5000
        assert r['total_taxa_centavos'] == 100
        assert r['total_liquido_centavos'] == 1900
        assert r['qtd_sem_taxa_conhecida'] == 1

    def test_taxa_zero_nao_e_confundida_com_taxa_desconhecida(self, app, planos):
        _add('p1', 2000, _dt(5), taxa=0, liquido=2000)

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r['qtd_sem_taxa_conhecida'] == 0
        assert r['total_liquido_centavos'] == 2000

    def test_limites_do_periodo_sao_inclusivos(self, app, planos):
        inicio, fim = _dt(10, 0, 0, 0), _dt(20, 23, 59, 59)
        _add('antes', 111, _dt(9, 23, 59, 59))
        _add('no_inicio', 222, inicio)
        _add('no_fim', 333, fim)
        _add('depois', 444, _dt(21, 0, 0, 0))

        r = FinanceiroService.resumo_periodo(inicio, fim)

        assert r['qtd_pagamentos'] == 2
        assert r['total_bruto_centavos'] == 555

    def test_agrupa_por_forma_de_pagamento_ordenado_do_maior_para_o_menor(self, app, planos):
        _add('p1', 1000, _dt(5), forma='pix')
        _add('p2', 1000, _dt(6), forma='pix')
        _add('p3', 5000, _dt(7), forma='cartao')

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r['por_forma_pagamento'] == [
            {'chave': 'cartao', 'total_centavos': 5000, 'qtd': 1},
            {'chave': 'pix', 'total_centavos': 2000, 'qtd': 2},
        ]

    def test_agrupa_por_tipo_de_usuario(self, app, planos):
        _add('p1', 1990, _dt(5), tipo='aluno')
        _add('p2', 4990, _dt(6), tipo='professor', plano='professor_pro')

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert [(g['chave'], g['total_centavos']) for g in r['por_tipo_usuario']] == [
            ('professor', 4990), ('aluno', 1990),
        ]

    def test_por_plano_traz_o_nome_legivel_do_catalogo(self, app, planos):
        _add('p1', 1990, _dt(5), plano='aluno_fit')
        _add('p2', 4990, _dt(6), plano='professor_pro', tipo='professor')

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        nomes = {g['chave']: g['nome'] for g in r['por_plano']}
        assert nomes == {'aluno_fit': 'Plano Fit', 'professor_pro': 'Plano Pro'}

    def test_plano_fora_do_catalogo_usa_o_proprio_codigo_como_nome(self, app, planos):
        _add('p1', 1000, _dt(5), plano='plano_antigo_removido')

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert r['por_plano'][0]['chave'] == 'plano_antigo_removido'
        assert r['por_plano'][0]['nome'] == 'plano_antigo_removido'

    def test_campos_nulos_viram_desconhecida_ou_desconhecido(self, app, planos):
        _add('p1', 1000, _dt(5), plano=None, tipo=None, forma='pix')
        # forma_pagamento é NOT NULL no banco; o "or 'desconhecida'" cobre
        # string vazia -- caso de dado legado/importado.
        _add('p2', 2000, _dt(6), plano='aluno_fit', tipo='aluno', forma='')

        r = FinanceiroService.resumo_periodo(_dt(1, 0), _dt(31, 23, 59, 59))

        assert {g['chave'] for g in r['por_forma_pagamento']} == {'pix', 'desconhecida'}
        assert {g['chave'] for g in r['por_tipo_usuario']} == {'aluno', 'desconhecido'}
        assert {g['chave'] for g in r['por_plano']} == {'aluno_fit', 'desconhecido'}


class TestAgrupar:

    def test_lista_vazia_retorna_lista_vazia(self):
        assert FinanceiroService._agrupar([], lambda p: p) == []

    def test_empate_de_total_mantem_todos_os_grupos(self):
        itens = [MagicMock(valor_bruto_centavos=100, k='a'), MagicMock(valor_bruto_centavos=100, k='b')]

        grupos = FinanceiroService._agrupar(itens, lambda p: p.k)

        assert {g['chave'] for g in grupos} == {'a', 'b'}
        assert all(g['qtd'] == 1 and g['total_centavos'] == 100 for g in grupos)


# ------------------------------------------------------------------
# Asaas (HTTP mockado)
# ------------------------------------------------------------------

@pytest.fixture
def asaas(app, monkeypatch):
    """Configura chave/ambiente e devolve o mock de requests.get usado pelo service."""
    app.config['ASAAS_API_KEY'] = 'chave-de-teste'
    app.config['ASAAS_ENV'] = 'sandbox'
    mock_get = MagicMock()
    monkeypatch.setattr(financeiro_service.requests, 'get', mock_get)
    return mock_get


def _resposta(json_data=None, erro_http=None):
    resp = MagicMock()
    resp.json.return_value = json_data
    if erro_http:
        resp.raise_for_status.side_effect = erro_http
    return resp


class TestObterSaldoAsaas:

    def test_converte_reais_para_centavos(self, asaas):
        asaas.return_value = _resposta({'balance': 123.45})
        assert FinanceiroService.obter_saldo_asaas() == {'saldo_centavos': 12345}

    def test_arredonda_em_vez_de_truncar_erro_de_ponto_flutuante(self, asaas):
        """0.29 * 100 == 28.999999999999996 em float -- int() daria 28."""
        asaas.return_value = _resposta({'balance': 0.29})
        assert FinanceiroService.obter_saldo_asaas() == {'saldo_centavos': 29}

    def test_saldo_zero_e_valido(self, asaas):
        asaas.return_value = _resposta({'balance': 0})
        assert FinanceiroService.obter_saldo_asaas() == {'saldo_centavos': 0}

    def test_saldo_negativo_e_preservado(self, asaas):
        asaas.return_value = _resposta({'balance': -10.5})
        assert FinanceiroService.obter_saldo_asaas() == {'saldo_centavos': -1050}

    def test_resposta_sem_balance_retorna_none_sem_quebrar(self, asaas):
        asaas.return_value = _resposta({})
        assert FinanceiroService.obter_saldo_asaas() == {'saldo_centavos': None}

    def test_chama_o_endpoint_certo_com_token_e_timeout(self, asaas):
        asaas.return_value = _resposta({'balance': 1})
        FinanceiroService.obter_saldo_asaas()

        args, kwargs = asaas.call_args
        assert args[0].endswith('/finance/balance')
        assert kwargs['headers']['access_token'] == 'chave-de-teste'
        assert kwargs['timeout'] == financeiro_service.REQUEST_TIMEOUT_SECONDS

    def test_ambiente_producao_usa_a_url_de_producao(self, app, asaas):
        app.config['ASAAS_ENV'] = 'production'
        asaas.return_value = _resposta({'balance': 1})
        FinanceiroService.obter_saldo_asaas()

        assert 'sandbox' not in asaas.call_args[0][0]

    @pytest.mark.parametrize('excecao', [
        requests.exceptions.Timeout('lento demais'),
        requests.exceptions.ConnectionError('sem rede'),
    ])
    def test_erro_de_rede_vira_mensagem_amigavel(self, asaas, excecao):
        asaas.side_effect = excecao

        r = FinanceiroService.obter_saldo_asaas()

        assert r == {'erro': 'Não foi possível consultar o saldo no Asaas agora.'}

    def test_http_4xx_5xx_vira_mensagem_amigavel(self, asaas):
        asaas.return_value = _resposta(erro_http=requests.exceptions.HTTPError('401 Unauthorized'))

        r = FinanceiroService.obter_saldo_asaas()

        assert 'erro' in r and 'saldo_centavos' not in r

    def test_json_invalido_vira_mensagem_amigavel(self, asaas):
        resp = _resposta()
        resp.json.side_effect = ValueError('not json')
        asaas.return_value = resp

        assert 'erro' in FinanceiroService.obter_saldo_asaas()

    def test_sem_api_key_nao_chama_a_rede_e_nao_vaza_detalhe(self, app, asaas):
        app.config['ASAAS_API_KEY'] = None

        r = FinanceiroService.obter_saldo_asaas()

        asaas.assert_not_called()
        assert r == {'erro': 'Não foi possível consultar o saldo no Asaas agora.'}
        assert 'ASAAS_API_KEY' not in r['erro']


class TestObterTaxasContaAsaas:

    def test_retorna_o_json_do_asaas_em_dados(self, asaas):
        payload = {'creditCard': {'operationValue': 0.49}, 'pix': {'fixedFee': 0.99}}
        asaas.return_value = _resposta(payload)

        assert FinanceiroService.obter_taxas_conta_asaas() == {'dados': payload}

    def test_chama_o_endpoint_de_taxas(self, asaas):
        asaas.return_value = _resposta({})
        FinanceiroService.obter_taxas_conta_asaas()
        assert asaas.call_args[0][0].endswith('/myAccount/fees')

    def test_erro_de_rede_vira_mensagem_amigavel(self, asaas):
        asaas.side_effect = requests.exceptions.ConnectionError('sem rede')

        r = FinanceiroService.obter_taxas_conta_asaas()

        assert r == {'erro': 'Não foi possível consultar as taxas da conta no Asaas agora.'}

    def test_http_error_vira_mensagem_amigavel(self, asaas):
        asaas.return_value = _resposta(erro_http=requests.exceptions.HTTPError('500'))
        assert 'erro' in FinanceiroService.obter_taxas_conta_asaas()

    def test_sem_api_key_nao_chama_a_rede(self, app, asaas):
        app.config['ASAAS_API_KEY'] = ''

        r = FinanceiroService.obter_taxas_conta_asaas()

        asaas.assert_not_called()
        assert 'erro' in r
