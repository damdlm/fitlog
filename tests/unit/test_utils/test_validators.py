"""Testes unitários para utils/validators.py"""
import pytest
from utils.validators import (
    validar_treino_id,
    validar_semana,
    validar_carga,
    validar_repeticoes,
    validar_num_series,
    validar_periodo,
    validar_email,
    validar_senha,
)


class TestValidarTreinoId:
    def test_valido_maiuscula(self):
        ok, valor = validar_treino_id('A')
        assert ok is True
        assert valor == 'A'

    def test_valido_minuscula_e_convertido(self):
        ok, valor = validar_treino_id('b')
        assert ok is True
        assert valor == 'B'

    def test_vazio_invalido(self):
        ok, msg = validar_treino_id('')
        assert ok is False
        assert 'obrigatório' in msg

    def test_none_invalido(self):
        ok, msg = validar_treino_id(None)
        assert ok is False

    def test_mais_de_um_caractere_invalido(self):
        ok, msg = validar_treino_id('AB')
        assert ok is False
        assert '1 caractere' in msg

    def test_nao_alfabetico_invalido(self):
        ok, msg = validar_treino_id('1')
        assert ok is False
        assert 'letra' in msg

    def test_com_espacos_e_normalizado(self):
        ok, valor = validar_treino_id('  c  ')
        assert ok is True
        assert valor == 'C'


class TestValidarSemana:
    def test_valida_minimo(self):
        ok, valor = validar_semana(1)
        assert ok is True
        assert valor == 1

    def test_valida_maximo(self):
        ok, valor = validar_semana(52)
        assert ok is True
        assert valor == 52

    def test_abaixo_do_minimo(self):
        ok, msg = validar_semana(0)
        assert ok is False
        assert 'entre 1 e 52' in msg

    def test_acima_do_maximo(self):
        ok, msg = validar_semana(53)
        assert ok is False

    def test_string_numerica_valida(self):
        ok, valor = validar_semana('10')
        assert ok is True
        assert valor == 10

    def test_nao_numerico_invalido(self):
        ok, msg = validar_semana('abc')
        assert ok is False
        assert 'número válido' in msg

    def test_none_invalido(self):
        ok, msg = validar_semana(None)
        assert ok is False


class TestValidarCarga:
    def test_valida_positiva(self):
        ok, valor = validar_carga(50.5)
        assert ok is True
        assert valor == 50.5

    def test_valida_zero(self):
        ok, valor = validar_carga(0)
        assert ok is True
        assert valor == 0.0

    def test_negativa_invalida(self):
        ok, msg = validar_carga(-1)
        assert ok is False
        assert 'negativa' in msg

    def test_acima_do_maximo_invalida(self):
        ok, msg = validar_carga(1000)
        assert ok is False
        assert 'máx 999kg' in msg

    def test_limite_maximo_valido(self):
        ok, valor = validar_carga(999)
        assert ok is True

    def test_nao_numerico_invalido(self):
        ok, msg = validar_carga('pesado')
        assert ok is False

    def test_string_numerica_valida(self):
        ok, valor = validar_carga('72.5')
        assert ok is True
        assert valor == 72.5


class TestValidarRepeticoes:
    def test_valida(self):
        ok, valor = validar_repeticoes(12)
        assert ok is True
        assert valor == 12

    def test_negativa_invalida(self):
        ok, msg = validar_repeticoes(-1)
        assert ok is False
        assert 'negativas' in msg

    def test_acima_do_maximo_invalida(self):
        ok, msg = validar_repeticoes(101)
        assert ok is False
        assert 'máx 100' in msg

    def test_limite_maximo_valido(self):
        ok, valor = validar_repeticoes(100)
        assert ok is True

    def test_zero_valido(self):
        ok, valor = validar_repeticoes(0)
        assert ok is True

    def test_nao_numerico_invalido(self):
        ok, msg = validar_repeticoes('muitas')
        assert ok is False


class TestValidarNumSeries:
    def test_valida_minimo(self):
        ok, valor = validar_num_series(1)
        assert ok is True
        assert valor == 1

    def test_valida_maximo(self):
        ok, valor = validar_num_series(10)
        assert ok is True
        assert valor == 10

    def test_abaixo_do_minimo_invalida(self):
        ok, msg = validar_num_series(0)
        assert ok is False
        assert 'entre 1 e 10' in msg

    def test_acima_do_maximo_invalida(self):
        ok, msg = validar_num_series(11)
        assert ok is False

    def test_nao_numerico_invalido(self):
        ok, msg = validar_num_series('varias')
        assert ok is False


class TestValidarPeriodo:
    def test_valido_com_barra(self):
        ok, valor = validar_periodo('Janeiro/2024')
        assert ok is True
        assert valor == 'Janeiro/2024'

    def test_valido_com_espaco(self):
        ok, valor = validar_periodo('Janeiro 2024')
        assert ok is True

    def test_valido_com_acentos(self):
        ok, valor = validar_periodo('Março/2024')
        assert ok is True

    def test_vazio_invalido(self):
        ok, msg = validar_periodo('')
        assert ok is False
        assert 'obrigatório' in msg

    def test_none_invalido(self):
        ok, msg = validar_periodo(None)
        assert ok is False

    def test_formato_invalido(self):
        ok, msg = validar_periodo('2024')
        assert ok is False
        assert 'Formato inválido' in msg

    def test_com_espacos_extras_normalizado(self):
        ok, valor = validar_periodo('  Janeiro/2024  ')
        assert ok is True
        assert valor == 'Janeiro/2024'


class TestValidarEmail:
    def test_valido(self):
        ok, valor = validar_email('teste@teste.com')
        assert ok is True
        assert valor == 'teste@teste.com'

    def test_valido_com_subdominio(self):
        ok, valor = validar_email('user.name+tag@sub.dominio.com.br')
        assert ok is True

    def test_vazio_invalido(self):
        ok, msg = validar_email('')
        assert ok is False
        assert 'obrigatório' in msg

    def test_none_invalido(self):
        ok, msg = validar_email(None)
        assert ok is False

    def test_sem_arroba_invalido(self):
        ok, msg = validar_email('teste.com')
        assert ok is False
        assert 'inválido' in msg

    def test_sem_dominio_invalido(self):
        ok, msg = validar_email('teste@')
        assert ok is False

    def test_sem_tld_invalido(self):
        ok, msg = validar_email('teste@dominio')
        assert ok is False


class TestValidarSenha:
    def test_valida(self):
        ok, valor = validar_senha('senha123')
        assert ok is True
        assert valor == 'senha123'

    def test_vazia_invalida(self):
        ok, msg = validar_senha('')
        assert ok is False
        assert 'obrigatória' in msg

    def test_none_invalida(self):
        ok, msg = validar_senha(None)
        assert ok is False

    def test_curta_invalida(self):
        ok, msg = validar_senha('abc123')
        assert ok is False
        assert '8 caracteres' in msg

    def test_sem_letra_invalida(self):
        ok, msg = validar_senha('12345678')
        assert ok is False
        assert 'letra' in msg

    def test_sem_numero_invalida(self):
        ok, msg = validar_senha('abcdefgh')
        assert ok is False
        assert 'número' in msg

    def test_limite_minimo_valido(self):
        ok, valor = validar_senha('abcdefg1')
        assert ok is True
