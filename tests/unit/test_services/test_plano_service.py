"""
Testes de PlanoService -- edição do PREÇO DE TABELA dos planos Fit/Pró/Premium
pelo admin (/admin/telas-controladas). Dinheiro: cada regra de validação aqui
evita cobrar um valor errado de todos os assinantes novos.
"""

import pytest

from models import db, Plano
from services.plano_service import (
    CODIGOS_EDITAVEIS, PlanoService, ResultadoAtualizacaoPrecos,
)


def _plano(codigo, nome, tipo='professor', preco=1000, ativo=True):
    p = Plano(codigo=codigo, nome=nome, tipo_usuario=tipo, preco_centavos=preco, ativo=ativo)
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def tres_planos(app):
    """Criados fora da ordem de exibição de propósito."""
    premium = _plano('professor_premium', 'Plano Premium', preco=9990)
    fit = _plano('aluno_fit', 'Plano Fit', tipo='aluno', preco=599)
    pro = _plano('professor_pro', 'Plano Pró', preco=2990)
    return fit, pro, premium


def _preco(codigo):
    db.session.expire_all()
    return Plano.query.filter_by(codigo=codigo).one().preco_centavos


# ------------------------------------------------------------------
# listar_editaveis
# ------------------------------------------------------------------

class TestListarEditaveis:

    def test_ordem_fixa_fit_pro_premium_independente_da_ordem_de_criacao(self, tres_planos):
        assert [p.codigo for p in PlanoService.listar_editaveis()] == list(CODIGOS_EDITAVEIS)
        assert list(CODIGOS_EDITAVEIS) == ['aluno_fit', 'professor_pro', 'professor_premium']

    def test_plano_ausente_no_banco_e_pulado_sem_derrubar(self, app):
        _plano('professor_pro', 'Plano Pró')

        assert [p.codigo for p in PlanoService.listar_editaveis()] == ['professor_pro']

    def test_banco_sem_planos_retorna_lista_vazia(self, app):
        assert PlanoService.listar_editaveis() == []

    def test_planos_fora_da_lista_editavel_nao_aparecem(self, tres_planos):
        _plano('plano_legado', 'Legado')
        _plano('professor_gratis', 'Grátis', preco=0)

        assert {p.codigo for p in PlanoService.listar_editaveis()} == set(CODIGOS_EDITAVEIS)


# ------------------------------------------------------------------
# _parse_valor_para_centavos
# ------------------------------------------------------------------

class TestParseValor:

    @pytest.mark.parametrize('texto,centavos', [
        ('10.90', 1090),        # <input type=number> do HTML
        ('10,90', 1090),        # formato brasileiro digitado/colado
        ('10,9', 1090),
        ('10.9', 1090),
        ('10', 1000),
        ('5', 500),
        ('  29.90  ', 2990),    # espaços nas pontas
        ('0.29', 29),           # 0.29*100 == 28.999... em float: tem que ARREDONDAR
        ('19.99', 1999),
        ('1234', 123400),
        ('0', 0),
        ('0,00', 0),
        ('99999.99', 9999999),
    ])
    def test_converte_valores_validos(self, texto, centavos):
        assert PlanoService._parse_valor_para_centavos(texto) == centavos

    @pytest.mark.parametrize('texto', [
        None, '', '   ', 'abc', 'R$ 10', '-5', '-0.50', '+5', '10.', '.5', ',5',
        '10.999', '0.005', '1e3', '1.234,56', '1,234.56', '10 90', '10,90,1',
        '10.90\n20', "10'; DROP TABLE planos;--",
    ])
    def test_rejeita_o_que_nao_e_valor_monetario_valido(self, texto):
        assert PlanoService._parse_valor_para_centavos(texto) is None

    @pytest.mark.xfail(strict=True, reason=(
        'BUG menor: o regex usa \\d, que casa dígitos Unicode (árabe-índico etc.) '
        'e int() os converte -> "١٢" vira R$ 12,00. Corrigir com [0-9] ou re.ASCII.'))
    def test_rejeita_digitos_unicode_nao_ascii(self):
        assert PlanoService._parse_valor_para_centavos('١٢') is None


# ------------------------------------------------------------------
# atualizar_precos
# ------------------------------------------------------------------

VALIDO = {'preco_aluno_fit': '6.90', 'preco_professor_pro': '31,90', 'preco_professor_premium': '109'}


class TestAtualizarPrecos:

    def test_valores_validos_salvam_os_tres_planos(self, tres_planos):
        r = PlanoService.atualizar_precos(VALIDO)

        assert r.ok is True and r.erros == []
        assert _preco('aluno_fit') == 690
        assert _preco('professor_pro') == 3190
        assert _preco('professor_premium') == 10900

    def test_resultado_ok_depende_so_da_lista_de_erros(self):
        assert ResultadoAtualizacaoPrecos().ok is True
        assert ResultadoAtualizacaoPrecos(erros=['x']).ok is False

    def test_tudo_ou_nada_um_valor_invalido_impede_salvar_todos(self, tres_planos):
        r = PlanoService.atualizar_precos({**VALIDO, 'preco_professor_pro': 'abc'})

        assert r.ok is False and len(r.erros) == 1
        assert _preco('aluno_fit') == 599
        assert _preco('professor_pro') == 2990
        assert _preco('professor_premium') == 9990

    def test_mensagem_de_erro_nomeia_o_plano_e_mostra_o_valor_digitado(self, tres_planos):
        r = PlanoService.atualizar_precos({**VALIDO, 'preco_professor_pro': 'abc'})

        assert r.erros == ['Valor inválido para Plano Pró: "abc".']

    @pytest.mark.parametrize('zero', ['0', '0,00', '0.00'])
    def test_preco_zero_e_recusado(self, tres_planos, zero):
        """Um preço 0 viraria plano de graça por engano."""
        r = PlanoService.atualizar_precos({**VALIDO, 'preco_aluno_fit': zero})

        assert r.ok is False
        assert _preco('aluno_fit') == 599

    def test_preco_negativo_e_recusado(self, tres_planos):
        assert PlanoService.atualizar_precos({**VALIDO, 'preco_aluno_fit': '-5'}).ok is False
        assert _preco('aluno_fit') == 599

    def test_campo_ausente_do_formulario_e_erro(self, tres_planos):
        form = {k: v for k, v in VALIDO.items() if k != 'preco_professor_premium'}

        r = PlanoService.atualizar_precos(form)

        assert r.ok is False
        assert 'Plano Premium' in r.erros[0] and 'None' in r.erros[0]
        assert _preco('aluno_fit') == 599                  # nada salvo

    def test_varios_invalidos_geram_um_erro_por_plano(self, tres_planos):
        r = PlanoService.atualizar_precos({'preco_aluno_fit': '', 'preco_professor_pro': 'x',
                                           'preco_professor_premium': '0'})

        assert len(r.erros) == 3

    def test_so_planos_existentes_no_banco_sao_exigidos(self, app):
        _plano('aluno_fit', 'Plano Fit', tipo='aluno', preco=599)

        r = PlanoService.atualizar_precos({'preco_aluno_fit': '7'})

        assert r.ok is True
        assert _preco('aluno_fit') == 700

    def test_nao_mexe_em_planos_fora_da_lista_editavel(self, tres_planos):
        _plano('plano_legado', 'Legado', preco=1234)

        PlanoService.atualizar_precos({**VALIDO, 'preco_plano_legado': '1'})

        assert _preco('plano_legado') == 1234

    def test_campos_extras_do_formulario_sao_ignorados(self, tres_planos):
        r = PlanoService.atualizar_precos({**VALIDO, 'acao': 'planos', 'csrf_token': 'x', 'preco_inexistente': '9'})
        assert r.ok is True

    def test_mesmo_valor_atual_nao_da_erro(self, tres_planos):
        r = PlanoService.atualizar_precos({'preco_aluno_fit': '5.99', 'preco_professor_pro': '29.90',
                                           'preco_professor_premium': '99.90'})
        assert r.ok is True
        assert _preco('aluno_fit') == 599
