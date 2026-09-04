"""Testes para utils/format_utils.py -- formatação de datas para
exibição (pt-BR) e para inputs HTML. Funções puras, sem banco.
"""
from datetime import date, datetime

from utils.format_utils import (
    data_atual_formatada,
    data_atual_iso,
    formatar_data,
    formatar_data_completa,
    formatar_data_para_input,
    formatar_horario,
)


class TestFormatarData:

    def test_string_iso_para_br(self):
        assert formatar_data('2024-03-15') == '15/03/2024'

    def test_aceita_objeto_date(self):
        assert formatar_data(date(2024, 3, 15)) == '15/03/2024'

    def test_aceita_objeto_datetime(self):
        assert formatar_data(datetime(2024, 3, 15, 10, 30)) == '15/03/2024'

    def test_none_retorna_vazio(self):
        assert formatar_data(None) == ''

    def test_string_vazia_retorna_vazio(self):
        assert formatar_data('') == ''

    def test_formato_invalido_retorna_a_propria_string(self):
        assert formatar_data('não é uma data') == 'não é uma data'


class TestFormatarDataParaInput:

    def test_br_para_iso(self):
        assert formatar_data_para_input('15/03/2024') == '2024-03-15'

    def test_aceita_objeto_date(self):
        assert formatar_data_para_input(date(2024, 3, 15)) == '2024-03-15'

    def test_none_retorna_vazio(self):
        assert formatar_data_para_input(None) == ''

    def test_string_vazia_retorna_vazio(self):
        assert formatar_data_para_input('') == ''

    def test_formato_invalido_retorna_a_propria_string(self):
        assert formatar_data_para_input('data-invalida') == 'data-invalida'


class TestDataAtual:

    def test_data_atual_formatada_no_padrao_br(self):
        resultado = data_atual_formatada()
        # DD/MM/AAAA
        assert len(resultado) == 10
        assert resultado[2] == '/' and resultado[5] == '/'

    def test_data_atual_iso_no_padrao_iso(self):
        resultado = data_atual_iso()
        assert len(resultado) == 10
        assert resultado[4] == '-' and resultado[7] == '-'
        # deve corresponder ao formato usado por formatar_data_para_input
        datetime.strptime(resultado, "%Y-%m-%d")


class TestFormatarDataCompleta:

    def test_data_por_extenso(self):
        assert formatar_data_completa('2024-03-15') == '15 de março de 2024'

    def test_aceita_objeto_date(self):
        assert formatar_data_completa(date(2024, 12, 25)) == '25 de dezembro de 2024'

    def test_none_retorna_vazio(self):
        assert formatar_data_completa(None) == ''

    def test_formato_invalido_retorna_a_propria_string(self):
        assert formatar_data_completa('inválido') == 'inválido'

    def test_todos_os_meses_tem_nome_em_portugues(self):
        nomes_esperados = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        for mes, nome_esperado in enumerate(nomes_esperados, start=1):
            resultado = formatar_data_completa(date(2024, mes, 1))
            assert nome_esperado in resultado


class TestFormatarHorario:

    def test_string_com_hora_formata_dd_mm_aaaa_hh_mm(self):
        assert formatar_horario('2024-03-15 14:30:00') == '15/03/2024 14:30'

    def test_aceita_objeto_datetime(self):
        assert formatar_horario(datetime(2024, 3, 15, 9, 5)) == '15/03/2024 09:05'

    def test_none_retorna_vazio(self):
        assert formatar_horario(None) == ''

    def test_string_vazia_retorna_vazio(self):
        assert formatar_horario('') == ''

    def test_formato_invalido_retorna_a_propria_string(self):
        assert formatar_horario('não é data/hora') == 'não é data/hora'
