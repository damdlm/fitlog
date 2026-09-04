"""Testes para utils/exercise_utils.py -- normalização de texto, busca
de músculo no catálogo (banco de dados) e cálculos de série/volume
usados em várias telas de estatística.
"""
from models import db, ExercicioSistema
from utils.exercise_utils import (
    buscar_musculo_no_catalogo,
    calcular_media_series,
    calcular_volume_total,
    get_series_from_registro,
    remover_acentos,
)


class TestRemoverAcentos:

    def test_remove_acentos_comuns(self):
        assert remover_acentos('Perná Direta') == 'Perna Direta'

    def test_string_sem_acento_fica_igual(self):
        assert remover_acentos('Supino Reto') == 'Supino Reto'

    def test_string_vazia(self):
        assert remover_acentos('') == ''

    def test_none_retorna_none(self):
        assert remover_acentos(None) is None

    def test_cedilha(self):
        assert remover_acentos('Flexão') == 'Flexao'


class TestBuscarMusculoNoCatalogo:

    def test_correspondencia_exata(self, app, db):
        db.session.add(ExercicioSistema(id_original='sys-1', nome='Supino Reto', grupo_muscular='Peito'))
        db.session.commit()

        assert buscar_musculo_no_catalogo('Supino Reto') == 'Peito'

    def test_correspondencia_exata_case_insensitive(self, app, db):
        db.session.add(ExercicioSistema(id_original='sys-2', nome='Agachamento', grupo_muscular='Pernas'))
        db.session.commit()

        assert buscar_musculo_no_catalogo('agachamento') == 'Pernas'

    def test_correspondencia_parcial_catalogo_contem_busca(self, app, db):
        db.session.add(ExercicioSistema(id_original='sys-3', nome='Supino Reto com Barra', grupo_muscular='Peito'))
        db.session.commit()

        # busca por um termo menor que está contido no nome do catálogo
        assert buscar_musculo_no_catalogo('Supino Reto') == 'Peito'

    def test_correspondencia_inversa_e_inalcancavel_na_pratica(self, app, db):
        """Achado ao escrever este teste: o passo 3 (nome buscado
        CONTÉM o nome do catálogo) existe no código mas nunca dispara
        de verdade -- o pré-filtro SQL do passo 2 já é
        `ExercicioSistema.nome.ilike(f'%{nome_exercicio}%')`, ou seja,
        só traz do banco linhas cujo nome no catálogo contenha o termo
        buscado INTEIRO. Quando o termo buscado é mais longo que o nome
        cadastrado (exatamente o cenário que o passo 3 deveria cobrir),
        a query já devolve uma lista vazia antes mesmo de chegar no
        loop do passo 3. Documentando o comportamento atual (None) em
        vez de silenciar o achado -- não corrigido aqui por estar fora
        do escopo desta rodada de testes."""
        db.session.add(ExercicioSistema(id_original='sys-4', nome='Rosca', grupo_muscular='Bíceps'))
        db.session.commit()

        assert buscar_musculo_no_catalogo('Rosca Direta com Barra Livre') is None

    def test_nao_encontrado_retorna_none(self, app, db):
        assert buscar_musculo_no_catalogo('Exercicio Que Nao Existe Nunca') is None

    def test_exercicio_sem_grupo_muscular_e_ignorado(self, app, db):
        db.session.add(ExercicioSistema(id_original='sys-5', nome='Sem Grupo', grupo_muscular=None))
        db.session.commit()

        assert buscar_musculo_no_catalogo('Sem Grupo') is None


class TestGetSeriesFromRegistro:

    def test_registro_sem_atributo_series_retorna_vazio(self):
        class _SemSeries:
            pass
        assert get_series_from_registro(_SemSeries()) == []

    def test_registro_com_series_vazia_retorna_vazio(self):
        class _ComSeriesVazia:
            series = []
        assert get_series_from_registro(_ComSeriesVazia()) == []

    def test_registro_com_series_converte_carga_pra_float(self):
        class _Serie:
            def __init__(self, carga, repeticoes):
                self.carga = carga
                self.repeticoes = repeticoes

        class _ComSeries:
            series = [_Serie('40.5', 10), _Serie('42.0', 8)]

        resultado = get_series_from_registro(_ComSeries())
        assert resultado == [
            {'carga': 40.5, 'repeticoes': 10},
            {'carga': 42.0, 'repeticoes': 8},
        ]


class TestCalcularMediaSeries:

    def test_media_de_varias_series(self):
        series = [
            {'carga': 40, 'repeticoes': 10},
            {'carga': 60, 'repeticoes': 8},
        ]
        media_carga, media_reps = calcular_media_series(series)
        assert media_carga == 50.0
        assert media_reps == 9.0

    def test_lista_vazia_retorna_zero_zero(self):
        assert calcular_media_series([]) == (0, 0)

    def test_arredonda_para_uma_casa_decimal(self):
        series = [{'carga': 10, 'repeticoes': 10}, {'carga': 10, 'repeticoes': 11}, {'carga': 10, 'repeticoes': 11}]
        _, media_reps = calcular_media_series(series)
        assert media_reps == 10.7


class TestCalcularVolumeTotal:

    def test_soma_carga_vezes_repeticoes_de_todas_as_series(self):
        series = [
            {'carga': 40, 'repeticoes': 10},  # 400
            {'carga': 50, 'repeticoes': 8},   # 400
        ]
        assert calcular_volume_total(series) == 800

    def test_lista_vazia_retorna_zero(self):
        assert calcular_volume_total([]) == 0
