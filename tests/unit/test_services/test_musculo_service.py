"""Testes para MusculoService -- CRUD simples sobre a tabela unificada
de músculos.
"""
from models import db, Musculo
from services.musculo_service import MusculoService


class TestGetAll:

    def test_retorna_todos_ordenados_por_nome_exibicao(self, app, db):
        db.session.add_all([
            Musculo(nome='costas', nome_exibicao='Costas'),
            Musculo(nome='abdomen', nome_exibicao='Abdômen'),
        ])
        db.session.commit()

        resultado = MusculoService.get_all()
        nomes = [m.nome_exibicao for m in resultado]
        assert nomes.index('Abdômen') < nomes.index('Costas')

    def test_sem_musculos_retorna_lista_vazia(self, app, db):
        assert MusculoService.get_all() == []


class TestGetAllNomes:

    def test_retorna_so_os_nomes_de_exibicao(self, app, db):
        db.session.add(Musculo(nome='peito', nome_exibicao='Peito'))
        db.session.commit()

        assert MusculoService.get_all_nomes() == ['Peito']


class TestGetById:

    def test_encontra_por_id(self, app, db):
        m = Musculo(nome='biceps', nome_exibicao='Bíceps')
        db.session.add(m)
        db.session.commit()

        assert MusculoService.get_by_id(m.id).nome_exibicao == 'Bíceps'

    def test_id_inexistente_retorna_none(self, app, db):
        assert MusculoService.get_by_id(999999) is None


class TestGetByNomeExibicao:

    def test_encontra_pelo_nome_de_exibicao_exato(self, app, db):
        db.session.add(Musculo(nome='triceps', nome_exibicao='Tríceps'))
        db.session.commit()

        assert MusculoService.get_by_nome_exibicao('Tríceps').nome == 'triceps'

    def test_nao_encontrado_retorna_none(self, app, db):
        assert MusculoService.get_by_nome_exibicao('Não Existe') is None


class TestGetByNome:

    def test_encontra_pelo_nome_em_minusculo(self, app, db):
        db.session.add(Musculo(nome='ombros', nome_exibicao='Ombros'))
        db.session.commit()

        assert MusculoService.get_by_nome('ombros').nome_exibicao == 'Ombros'

    def test_nao_encontrado_retorna_none(self, app, db):
        assert MusculoService.get_by_nome('inexistente') is None


class TestGetOrCreate:

    def test_cria_quando_nao_existe(self, app, db):
        resultado = MusculoService.get_or_create('Panturrilhas')

        assert resultado is not None
        assert resultado.nome == 'panturrilhas'
        assert resultado.nome_exibicao == 'Panturrilhas'
        assert Musculo.query.filter_by(nome_exibicao='Panturrilhas').count() == 1

    def test_retorna_existente_sem_duplicar(self, app, db):
        db.session.add(Musculo(nome='gluteos', nome_exibicao='Glúteos'))
        db.session.commit()

        resultado = MusculoService.get_or_create('Glúteos')

        assert Musculo.query.filter_by(nome_exibicao='Glúteos').count() == 1
        assert resultado.nome == 'gluteos'
