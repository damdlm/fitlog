"""Testes para utils/date_utils.py -- utilitários de data usados em
services/versao_service.py, routes/register_routes.py,
routes/calendar_routes.py e routes/stats_routes.py. Todas as funções
aqui são puras (sem banco, sem I/O), então os testes não precisam de
app/db.
"""
from datetime import date, datetime

from utils.date_utils import (
    calcular_diferenca_dias,
    converter_periodo_para_data,
    data_para_periodo,
    data_para_semana,
    extrair_mes_ano,
    formatar_data_br,
    nome_do_mes,
    numero_do_mes,
    obter_dias_do_mes,
    obter_semanas_do_mes,
    ordenar_periodos,
    primeiro_dia_do_mes,
    ultimo_dia_do_mes,
    validar_data,
)


class TestConverterPeriodoParaData:

    def test_mes_barra_ano_completo(self):
        assert converter_periodo_para_data("Janeiro/2024") == "2024-01-01"

    def test_mes_hifen_ano(self):
        assert converter_periodo_para_data("Março-2024") == "2024-03-01"

    def test_mes_espaco_ano(self):
        assert converter_periodo_para_data("Fevereiro 2024") == "2024-02-01"

    def test_abreviacao_do_mes(self):
        assert converter_periodo_para_data("Dez/2024") == "2024-12-01"

    def test_ano_de_2_digitos_menor_ou_igual_a_50_vira_2000(self):
        assert converter_periodo_para_data("Março/24") == "2024-03-01"

    def test_ano_de_2_digitos_maior_que_50_vira_1900(self):
        assert converter_periodo_para_data("Março/99") == "1999-03-01"

    def test_so_o_mes_assume_ano_atual(self):
        resultado = converter_periodo_para_data("Julho")
        ano_atual = datetime.now().year
        assert resultado == f"{ano_atual}-07-01"

    def test_string_vazia_retorna_data_de_hoje(self):
        resultado = converter_periodo_para_data("")
        assert resultado == datetime.now().strftime("%Y-%m-%d")

    def test_none_retorna_data_de_hoje(self):
        resultado = converter_periodo_para_data(None)
        assert resultado == datetime.now().strftime("%Y-%m-%d")

    def test_mes_nao_reconhecido_cai_no_fallback(self):
        resultado = converter_periodo_para_data("Blergh/2024")
        assert resultado == datetime.now().strftime("%Y-%m-%d")

    def test_case_insensitive(self):
        assert converter_periodo_para_data("JANEIRO/2024") == "2024-01-01"


class TestOrdenarPeriodos:

    def test_ordena_do_mais_recente_pro_mais_antigo(self):
        periodos = ["Janeiro/2024", "Dezembro/2023", "Março/2024"]
        resultado = ordenar_periodos(periodos)
        assert resultado == ["Março/2024", "Janeiro/2024", "Dezembro/2023"]

    def test_periodo_mal_formado_vai_pro_topo_ordenado_como_ano_9999(self):
        periodos = ["Janeiro/2024", "formato-invalido"]
        resultado = ordenar_periodos(periodos)
        assert resultado[0] == "formato-invalido"

    def test_lista_vazia(self):
        assert ordenar_periodos([]) == []


class TestFormatarDataBr:

    def test_converte_iso_para_br(self):
        assert formatar_data_br("2024-03-15") == "15/03/2024"

    def test_aceita_objeto_date(self):
        assert formatar_data_br(date(2024, 3, 15)) == "15/03/2024"

    def test_string_vazia_retorna_vazio(self):
        assert formatar_data_br("") == ""

    def test_none_retorna_vazio(self):
        assert formatar_data_br(None) == ""

    def test_formato_invalido_retorna_a_propria_string(self):
        assert formatar_data_br("data-invalida") == "data-invalida"


class TestDataParaPeriodo:

    def test_converte_date_para_mes_barra_ano(self):
        assert data_para_periodo(date(2024, 3, 15)) == "Março/2024"

    def test_none_retorna_vazio(self):
        assert data_para_periodo(None) == ""

    def test_dezembro(self):
        assert data_para_periodo(date(2024, 12, 1)) == "Dezembro/2024"


class TestDataParaSemana:

    def test_retorna_semana_iso(self):
        assert data_para_semana(date(2024, 3, 15)) == 11

    def test_none_retorna_1(self):
        assert data_para_semana(None) == 1


class TestValidarData:

    def test_data_valida_no_passado(self):
        sucesso, resultado = validar_data("2024-03-15")
        assert sucesso is True
        assert resultado == date(2024, 3, 15)

    def test_data_futura_e_invalida(self):
        ano_futuro = datetime.now().year + 5
        sucesso, resultado = validar_data(f"{ano_futuro}-01-01")
        assert sucesso is False
        assert "futura" in resultado

    def test_formato_invalido(self):
        sucesso, resultado = validar_data("15/03/2024")
        assert sucesso is False
        assert "inválido" in resultado

    def test_string_vazia(self):
        sucesso, resultado = validar_data("")
        assert sucesso is False
        assert resultado == "Data não fornecida"

    def test_none(self):
        sucesso, resultado = validar_data(None)
        assert sucesso is False


class TestObterSemanasDoMes:

    def test_marco_2024_retorna_semanas_iso_corretas(self):
        assert obter_semanas_do_mes(2024, 3) == [9, 10, 11, 12, 13]

    def test_sempre_ordenado_e_sem_duplicatas(self):
        semanas = obter_semanas_do_mes(2024, 2)
        assert semanas == sorted(set(semanas))


class TestObterDiasDoMes:

    def test_fevereiro_bissexto_tem_29_dias(self):
        dias = obter_dias_do_mes(2024, 2)
        assert len(dias) == 29
        assert dias[0] == date(2024, 2, 1)
        assert dias[-1] == date(2024, 2, 29)

    def test_fevereiro_nao_bissexto_tem_28_dias(self):
        assert len(obter_dias_do_mes(2023, 2)) == 28

    def test_todos_sao_objetos_date(self):
        dias = obter_dias_do_mes(2024, 1)
        assert all(isinstance(d, date) for d in dias)


class TestCalcularDiferencaDias:

    def test_diferenca_positiva(self):
        assert calcular_diferenca_dias(date(2024, 3, 1), date(2024, 3, 15)) == 14

    def test_diferenca_negativa_quando_fim_e_antes_do_inicio(self):
        assert calcular_diferenca_dias(date(2024, 3, 15), date(2024, 3, 1)) == -14

    def test_sem_data_inicio_retorna_zero(self):
        assert calcular_diferenca_dias(None, date(2024, 3, 1)) == 0

    def test_sem_data_fim_retorna_zero(self):
        assert calcular_diferenca_dias(date(2024, 3, 1), None) == 0


class TestPrimeiroUltimoDiaDoMes:

    def test_primeiro_dia(self):
        assert primeiro_dia_do_mes(2024, 3) == date(2024, 3, 1)

    def test_ultimo_dia_mes_31(self):
        assert ultimo_dia_do_mes(2024, 3) == date(2024, 3, 31)

    def test_ultimo_dia_fevereiro_bissexto(self):
        assert ultimo_dia_do_mes(2024, 2) == date(2024, 2, 29)


class TestNomeENumeroDoMes:

    def test_nome_do_mes_valido(self):
        assert nome_do_mes(1) == "Janeiro"
        assert nome_do_mes(12) == "Dezembro"

    def test_nome_do_mes_invalido_retorna_vazio(self):
        assert nome_do_mes(13) == ""
        assert nome_do_mes(0) == ""

    def test_numero_do_mes_valido(self):
        assert numero_do_mes("Janeiro") == 1
        assert numero_do_mes("dezembro") == 12

    def test_numero_do_mes_abreviado(self):
        assert numero_do_mes("jan") == 1

    def test_numero_do_mes_invalido_retorna_zero(self):
        assert numero_do_mes("mesinventado") == 0


class TestExtrairMesAno:

    def test_periodo_valido(self):
        assert extrair_mes_ano("Janeiro/2024") == (1, 2024)

    def test_sem_barra_retorna_none_none(self):
        assert extrair_mes_ano("Janeiro 2024") == (None, None)

    def test_mes_invalido_retorna_none_none(self):
        assert extrair_mes_ano("MesInvalido/2024") == (None, None)

    def test_ano_nao_numerico_retorna_none_none(self):
        assert extrair_mes_ano("Janeiro/abcd") == (None, None)

    def test_string_vazia(self):
        assert extrair_mes_ano("") == (None, None)

    def test_none(self):
        assert extrair_mes_ano(None) == (None, None)

    def test_com_espacos_extras(self):
        assert extrair_mes_ano(" Março / 2024 ") == (3, 2024)
