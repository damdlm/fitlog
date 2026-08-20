"""Testes unitários para services/seed_service.py"""
from data.default_workouts import WORKOUTS_3X, WORKOUTS_4X, WORKOUTS_5X
from models import db, User, Treino, ExercicioCustomizado, Musculo
from services.seed_service import SeedService


def _criar_usuario(username):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario='aluno')
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


class TestGetOrCreateMusculo:
    def test_cria_musculo_novo(self, app):
        with app.app_context():
            musculo = SeedService.get_or_create_musculo('Peitoral')
            assert musculo is not None
            assert musculo.id is not None
            assert musculo.nome_exibicao == 'Peitoral'
            assert musculo.nome == 'peitoral'

    def test_retorna_musculo_existente_sem_duplicar(self, app):
        with app.app_context():
            primeiro = SeedService.get_or_create_musculo('Peitoral')
            segundo = SeedService.get_or_create_musculo('Peitoral')

            assert primeiro.id == segundo.id
            assert Musculo.query.filter_by(nome_exibicao='Peitoral').count() == 1


class TestCreateMinimalWorkouts:
    def test_cria_treinos_a_b_c_sem_exercicios(self, app):
        with app.app_context():
            u = _criar_usuario('seed_min_1')
            resultado = SeedService.create_minimal_workouts(u.id)

            assert set(resultado.keys()) == {'A', 'B', 'C'}
            assert Treino.query.filter_by(user_id=u.id).count() == 3
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id).count() == 0

    def test_treinos_tem_nomes_e_descricoes_esperados(self, app):
        with app.app_context():
            u = _criar_usuario('seed_min_2')
            resultado = SeedService.create_minimal_workouts(u.id)

            assert resultado['A'].nome == 'Treino A'
            assert resultado['B'].nome == 'Treino B'
            assert resultado['C'].nome == 'Treino C'

    def test_nao_duplica_treino_ja_existente(self, app):
        with app.app_context():
            u = _criar_usuario('seed_min_3')
            treino_existente = Treino(codigo='A', nome='Meu treino customizado',
                                       descricao='d', user_id=u.id)
            db.session.add(treino_existente)
            db.session.commit()

            resultado = SeedService.create_minimal_workouts(u.id)

            assert resultado['A'].nome == 'Meu treino customizado'
            assert Treino.query.filter_by(user_id=u.id, codigo='A').count() == 1

    def test_isolado_por_usuario(self, app):
        with app.app_context():
            u1 = _criar_usuario('seed_min_iso1')
            u2 = _criar_usuario('seed_min_iso2')
            SeedService.create_minimal_workouts(u1.id)
            SeedService.create_minimal_workouts(u2.id)

            assert Treino.query.filter_by(user_id=u1.id).count() == 3
            assert Treino.query.filter_by(user_id=u2.id).count() == 3


class TestCreateDefaultWorkouts:
    def test_frequencia_3x_cria_treinos_a_b_c(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_3x')
            resultado = SeedService.create_default_workouts(u.id, frequency='3x')

            assert set(resultado.keys()) == set(WORKOUTS_3X.keys())
            assert Treino.query.filter_by(user_id=u.id).count() == 3

    def test_frequencia_4x_cria_treinos_a_b_c_d(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_4x')
            resultado = SeedService.create_default_workouts(u.id, frequency='4x')

            assert set(resultado.keys()) == set(WORKOUTS_4X.keys())
            assert Treino.query.filter_by(user_id=u.id).count() == 4

    def test_frequencia_5x_cria_treinos_a_b_c_d_e(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_5x')
            resultado = SeedService.create_default_workouts(u.id, frequency='5x')

            assert set(resultado.keys()) == set(WORKOUTS_5X.keys())
            assert Treino.query.filter_by(user_id=u.id).count() == 5

    def test_frequencia_invalida_usa_3x_como_padrao(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_invalida')
            resultado = SeedService.create_default_workouts(u.id, frequency='invalida')

            assert set(resultado.keys()) == set(WORKOUTS_3X.keys())

    def test_cria_exercicios_customizados_para_cada_treino(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_exs')
            SeedService.create_default_workouts(u.id, frequency='3x')

            total_exercicios_esperado = sum(
                len(w['exercicios']) for w in WORKOUTS_3X.values()
            )
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id).count() == \
                total_exercicios_esperado

    def test_exercicio_vinculado_ao_musculo_correto(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_musc')
            SeedService.create_default_workouts(u.id, frequency='3x')

            supino = ExercicioCustomizado.query.filter_by(
                usuario_id=u.id, nome='Supino Reto com Barra').first()
            assert supino is not None
            musculo = db.session.get(Musculo, supino.musculo_id)
            assert musculo is not None
            assert musculo.nome_exibicao == 'Peitoral'

    def test_nao_duplica_treino_ja_existente_mas_mantem_exercicios(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_dup')
            treino_existente = Treino(codigo='A', nome='Treino customizado',
                                       descricao='d', user_id=u.id)
            db.session.add(treino_existente)
            db.session.commit()

            resultado = SeedService.create_default_workouts(u.id, frequency='3x')

            assert resultado['A'].nome == 'Treino customizado'
            assert Treino.query.filter_by(user_id=u.id, codigo='A').count() == 1
            # Como o treino 'A' já existia, a rota de criação de
            # exercícios para ele é pulada (continue) -- só B e C geram
            # exercícios.
            exercicios_esperados = sum(
                len(w['exercicios']) for codigo, w in WORKOUTS_3X.items() if codigo != 'A'
            )
            assert ExercicioCustomizado.query.filter_by(usuario_id=u.id).count() == \
                exercicios_esperados

    def test_nao_duplica_exercicio_ja_existente_para_o_usuario(self, app):
        with app.app_context():
            u = _criar_usuario('seed_def_exdup')
            SeedService.create_default_workouts(u.id, frequency='3x')
            total_antes = ExercicioCustomizado.query.filter_by(usuario_id=u.id).count()

            # Remove os treinos para poder rodar de novo sem cair no
            # "continue" acima, mas os exercícios do usuário continuam.
            Treino.query.filter_by(user_id=u.id).delete()
            db.session.commit()

            SeedService.create_default_workouts(u.id, frequency='3x')
            total_depois = ExercicioCustomizado.query.filter_by(usuario_id=u.id).count()

            assert total_depois == total_antes

    def test_isolado_por_usuario(self, app):
        with app.app_context():
            u1 = _criar_usuario('seed_def_iso1')
            u2 = _criar_usuario('seed_def_iso2')
            SeedService.create_default_workouts(u1.id, frequency='3x')
            SeedService.create_default_workouts(u2.id, frequency='3x')

            total_esperado = sum(len(w['exercicios']) for w in WORKOUTS_3X.values())
            assert ExercicioCustomizado.query.filter_by(usuario_id=u1.id).count() == \
                total_esperado
            assert ExercicioCustomizado.query.filter_by(usuario_id=u2.id).count() == \
                total_esperado


class TestCreateAllFrequencies:
    def test_cria_treinos_das_tres_frequencias(self, app):
        with app.app_context():
            u = _criar_usuario('seed_all_1')
            resultado = SeedService.create_all_frequencies(u.id)

            assert set(resultado.keys()) == {'3x', '4x', '5x'}
            # Códigos A/B/C se repetem entre as frequências (mesmo user_id
            # + código) -- 3x roda primeiro e cria A/B/C; 4x e 5x reaproveitam
            # os mesmos treinos A/B/C já existentes e só criam D (e E na 5x).
            assert Treino.query.filter_by(user_id=u.id).count() == 5

    def test_resultado_de_cada_frequencia_tem_os_codigos_certos(self, app):
        with app.app_context():
            u = _criar_usuario('seed_all_2')
            resultado = SeedService.create_all_frequencies(u.id)

            assert set(resultado['3x'].keys()) == set(WORKOUTS_3X.keys())
            assert set(resultado['4x'].keys()) == set(WORKOUTS_4X.keys())
            assert set(resultado['5x'].keys()) == set(WORKOUTS_5X.keys())
