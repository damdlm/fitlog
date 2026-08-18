"""Testes unitários para schemas/treino_schema.py e schemas/versao_schema.py"""
from datetime import date

import pytest
from marshmallow import ValidationError

from models import db, User, Treino, VersaoGlobal
from schemas.treino_schema import TreinoSchema, TreinoSimplificadoSchema
from schemas.versao_schema import VersaoSchema, VersaoSimplificadoSchema, VersaoDetalhadaSchema


def _criar_usuario(username):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


class TestTreinoSchemaDump:
    def test_dump_completo_falha_bug_conhecido(self, app):
        """
        NOTA (bug conhecido): TreinoSchema.get_qtd_exercicios acessa
        obj.exercicios, mas o relacionamento em Treino se chama 'versoes'
        (não 'exercicios'). Dump de uma instância real sempre lança
        AttributeError. Este teste documenta o comportamento atual.
        """
        with app.app_context():
            u = _criar_usuario('schema_treino_dump_1')
            t = Treino(codigo='A', nome='Treino A', descricao='desc', user_id=u.id)
            db.session.add(t)
            db.session.commit()

            with pytest.raises(AttributeError):
                TreinoSchema().dump(t)

    def test_dump_simplificado_funciona(self, app):
        with app.app_context():
            u = _criar_usuario('schema_treino_dump_2')
            t = Treino(codigo='B', nome='Treino B', descricao='desc', user_id=u.id)
            db.session.add(t)
            db.session.commit()

            resultado = TreinoSimplificadoSchema().dump(t)
            assert resultado['codigo'] == 'B'
            assert resultado['nome'] == 'Treino B'
            # qtd_exercicios não existe como atributo real no modelo Treino
            # -- marshmallow omite campos ausentes do dump silenciosamente.
            assert 'qtd_exercicios' not in resultado


class TestTreinoSchemaLoad:
    def test_load_cria_instancia_treino(self, app):
        with app.app_context():
            resultado = TreinoSchema().load(
                {'codigo': 'C', 'nome': 'Treino C', 'descricao': 'desc'}
            )
            assert isinstance(resultado, Treino)
            assert resultado.codigo == 'C'

    def test_load_falha_sem_campos_obrigatorios(self, app):
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                TreinoSchema().load({})

            erros = exc_info.value.messages
            assert 'codigo' in erros
            assert 'nome' in erros

    def test_load_falha_codigo_com_mais_de_1_caractere(self, app):
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                TreinoSchema().load({'codigo': 'AB', 'nome': 'Treino'})

            assert 'codigo' in exc_info.value.messages

    def test_load_falha_nome_vazio(self, app):
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                TreinoSchema().load({'codigo': 'A', 'nome': ''})

            assert 'nome' in exc_info.value.messages

    def test_load_rejeita_campos_dump_only_como_desconhecidos(self, app):
        with app.app_context():
            # id/user_id são dump_only -- marshmallow (unknown=RAISE, o
            # padrão) os trata como campos desconhecidos na entrada e
            # rejeita o load inteiro.
            with pytest.raises(ValidationError) as exc_info:
                TreinoSchema().load(
                    {'codigo': 'D', 'nome': 'Treino D', 'id': 999, 'user_id': 888}
                )
            assert 'id' in exc_info.value.messages
            assert 'user_id' in exc_info.value.messages


class TestVersaoSchemaDump:
    def test_dump_completo(self, app):
        with app.app_context():
            u = _criar_usuario('schema_versao_dump_1')
            v = VersaoGlobal(numero_versao=1, descricao='Versao 1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), user_id=u.id)
            db.session.add(v)
            db.session.commit()

            resultado = VersaoSchema().dump(v)
            assert resultado['descricao'] == 'Versao 1'
            assert resultado['data_inicio_formatada'] == '01/01/2024'
            assert resultado['data_fim_formatada'] == ''
            assert resultado['qtd_treinos'] == 0
            assert resultado['qtd_exercicios'] == 0
            assert resultado['is_ativa'] is True
            assert resultado['periodo'] == '01/01/2024 até Atual'

    def test_dump_versao_finalizada(self, app):
        with app.app_context():
            u = _criar_usuario('schema_versao_dump_2')
            v = VersaoGlobal(numero_versao=1, descricao='Versao 1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), data_fim=date(2024, 2, 1),
                              user_id=u.id)
            db.session.add(v)
            db.session.commit()

            resultado = VersaoSchema().dump(v)
            assert resultado['is_ativa'] is False
            assert resultado['data_fim_formatada'] == '01/02/2024'
            assert resultado['periodo'] == '01/01/2024 até 01/02/2024'

    def test_dump_simplificado_omite_campos_calculados(self, app):
        with app.app_context():
            u = _criar_usuario('schema_versao_dump_3')
            v = VersaoGlobal(numero_versao=1, descricao='Versao 1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), user_id=u.id)
            db.session.add(v)
            db.session.commit()

            resultado = VersaoSimplificadoSchema().dump(v)
            assert resultado['descricao'] == 'Versao 1'
            # is_ativa/data_inicio_formatada não são atributos reais do
            # modelo (só existem como Method em VersaoSchema) -- omitidos.
            assert 'is_ativa' not in resultado
            assert 'data_inicio_formatada' not in resultado


class TestVersaoSchemaLoad:
    def test_load_cria_instancia_versao(self, app):
        with app.app_context():
            resultado = VersaoSchema().load(
                {'descricao': 'Nova versao', 'data_inicio': '2024-01-01'}
            )
            assert isinstance(resultado, VersaoGlobal)
            assert resultado.descricao == 'Nova versao'

    def test_load_falha_sem_descricao(self, app):
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                VersaoSchema().load({'data_inicio': '2024-01-01'})

            assert 'descricao' in exc_info.value.messages

    def test_load_falha_sem_data_inicio(self, app):
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                VersaoSchema().load({'descricao': 'Versao'})

            assert 'data_inicio' in exc_info.value.messages

    def test_pre_load_converte_data_fim_vazia_para_none(self, app):
        with app.app_context():
            resultado = VersaoSchema().load(
                {'descricao': 'Versao', 'data_inicio': '2024-01-01', 'data_fim': ''}
            )
            assert resultado.data_fim is None

    def test_load_aceita_data_fim_preenchida(self, app):
        with app.app_context():
            resultado = VersaoSchema().load(
                {'descricao': 'Versao', 'data_inicio': '2024-01-01', 'data_fim': '2024-03-01'}
            )
            assert resultado.data_fim == date(2024, 3, 1)


class TestVersaoDetalhadaSchema:
    def test_load_cria_instancia(self, app):
        with app.app_context():
            resultado = VersaoDetalhadaSchema().load(
                {'descricao': 'Versao detalhada', 'data_inicio': '2024-01-01'}
            )
            assert isinstance(resultado, VersaoGlobal)

    def test_dump_falha_bug_conhecido_campo_treinos(self, app):
        """
        NOTA (bug conhecido): VersaoDetalhadaSchema declara 'treinos' como
        fields.Dict, mas VersaoGlobal.treinos é uma lista (db.relationship
        para TreinoVersao), não um dict -- marshmallow tenta chamar
        .items() nela e lança AttributeError. Dump de uma instância real
        sempre falha. Este teste documenta o comportamento atual.
        """
        with app.app_context():
            u = _criar_usuario('schema_versao_detalhada')
            v = VersaoGlobal(numero_versao=1, descricao='Versao 1', divisao='ABC',
                              data_inicio=date(2024, 1, 1), user_id=u.id)
            db.session.add(v)
            db.session.commit()

            with pytest.raises(AttributeError):
                VersaoDetalhadaSchema().dump(v)
