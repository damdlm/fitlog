"""Testes unitários para services/catalogo_service.py"""
from models import db, ExercicioSistema
from services.catalogo_service import CatalogoService


def _criar_exercicio_sistema(nome, grupo_muscular='Peitoral', equipamento='Barra',
                              passos_pt=None, id_original=None):
    ex = ExercicioSistema(nome=nome, grupo_muscular=grupo_muscular, equipamento=equipamento,
                           passos_pt=passos_pt or [], id_original=id_original or nome)
    db.session.add(ex)
    db.session.commit()
    return ex


class TestGetTodosExercicios:
    def test_vazio_sem_exercicios(self, app):
        with app.app_context():
            assert CatalogoService.get_todos_exercicios() == []

    def test_retorna_exercicios_ordenados_por_nome(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')
            _criar_exercicio_sistema('Agachamento')

            resultado = CatalogoService.get_todos_exercicios()
            assert len(resultado) == 2
            assert resultado[0]['nome'] == 'Agachamento'
            assert resultado[1]['nome'] == 'Supino Reto'

    def test_formato_do_dicionario_retornado(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral',
                                      equipamento='Barra', passos_pt=['Deite no banco'])

            resultado = CatalogoService.get_todos_exercicios()
            ex = resultado[0]
            assert ex['nome'] == 'Supino Reto'
            assert ex['musculo'] == 'Peitoral'
            assert ex['musculo_original'] == 'Peitoral'
            assert ex['equipment'] == 'Barra'
            assert ex['level'] == ''
            assert ex['force'] == ''
            assert ex['instructions'] == ['Deite no banco']

    def test_musculo_ausente_vira_nao_especificado(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Exercicio X', grupo_muscular=None)

            resultado = CatalogoService.get_todos_exercicios()
            assert resultado[0]['musculo'] == 'Não especificado'
            assert resultado[0]['musculo_original'] == ''

    def test_respeita_limite(self, app):
        with app.app_context():
            for i in range(5):
                _criar_exercicio_sistema(f'Exercicio {i}')

            resultado = CatalogoService.get_todos_exercicios(limite=2)
            assert len(resultado) == 2


class TestGetCatalogo:
    def test_e_alias_de_get_todos_exercicios(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')

            assert CatalogoService.get_catalogo() == CatalogoService.get_todos_exercicios()


class TestBuscarExercicios:
    def test_busca_por_termo(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')
            _criar_exercicio_sistema('Agachamento Livre')

            resultado = CatalogoService.buscar_exercicios(termo='supino')
            assert len(resultado) == 1
            assert resultado[0]['nome'] == 'Supino Reto'

    def test_busca_por_termo_case_insensitive(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')

            resultado = CatalogoService.buscar_exercicios(termo='SUPINO')
            assert len(resultado) == 1

    def test_busca_por_musculo(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Agachamento', grupo_muscular='Quadríceps')

            resultado = CatalogoService.buscar_exercicios(musculo='Quadríceps')
            assert len(resultado) == 1
            assert resultado[0]['nome'] == 'Agachamento'

    def test_busca_por_termo_e_musculo_combinados(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Supino Inclinado', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Rosca Direta', grupo_muscular='Bíceps')

            resultado = CatalogoService.buscar_exercicios(termo='supino', musculo='Peitoral')
            assert len(resultado) == 2

    def test_sem_filtros_retorna_todos(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')
            _criar_exercicio_sistema('Agachamento')

            resultado = CatalogoService.buscar_exercicios()
            assert len(resultado) == 2

    def test_vazio_para_termo_sem_correspondencia(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')

            resultado = CatalogoService.buscar_exercicios(termo='inexistente')
            assert resultado == []

    def test_respeita_limite(self, app):
        with app.app_context():
            for i in range(5):
                _criar_exercicio_sistema(f'Exercicio {i}')

            resultado = CatalogoService.buscar_exercicios(limite=3)
            assert len(resultado) == 3


class TestGetMusculosDisponiveis:
    def test_retorna_musculos_unicos_ordenados(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Supino Inclinado', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Agachamento', grupo_muscular='Quadríceps')

            resultado = CatalogoService.get_musculos_disponiveis()
            assert resultado == ['Peitoral', 'Quadríceps']

    def test_vazio_sem_exercicios(self, app):
        with app.app_context():
            assert CatalogoService.get_musculos_disponiveis() == []

    def test_ignora_musculo_nulo(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral')
            _criar_exercicio_sistema('Sem musculo', grupo_muscular=None)

            resultado = CatalogoService.get_musculos_disponiveis()
            assert resultado == ['Peitoral']


class TestGetExercicioPorNome:
    def test_encontra_exercicio(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto', grupo_muscular='Peitoral',
                                      equipamento='Barra', passos_pt=['Passo 1'])

            resultado = CatalogoService.get_exercicio_por_nome('Supino Reto')
            assert resultado is not None
            assert resultado['nome'] == 'Supino Reto'
            assert resultado['musculo'] == 'Peitoral'
            assert resultado['equipment'] == 'Barra'
            assert resultado['instructions'] == ['Passo 1']

    def test_busca_case_insensitive(self, app):
        with app.app_context():
            _criar_exercicio_sistema('Supino Reto')

            resultado = CatalogoService.get_exercicio_por_nome('supino reto')
            assert resultado is not None

    def test_none_para_nome_inexistente(self, app):
        with app.app_context():
            resultado = CatalogoService.get_exercicio_por_nome('Nao Existe')
            assert resultado is None
