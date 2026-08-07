"""
Testes unitários para services/versao_service.py.

Antes desta rodada, o arquivo tinha 36% de cobertura -- justamente o
serviço mais alterado nas últimas fases de otimização (N+1, IDOR).
Foca nas funções mais críticas para o fluxo de negócio: criar/clonar/
excluir/finalizar versão, gerenciar treinos dentro de uma versão, e
get_exercicios_agrupados_por_treino (função nova, criada para resolver
N+1 em professor/aluno/FitBot -- não tinha nenhum teste direto ainda,
só cobertura indireta via rotas).
"""
from datetime import date

from models import (
    db, User, Musculo, Treino, VersaoGlobal, TreinoVersao,
    VersaoExercicio, ExercicioUsuario, ExercicioSistema, RegistroTreino,
)
from services.versao_service import VersaoService
from services.treino_service import TreinoService


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _criar_musculo(user_id):
    musculo = Musculo(nome=f'm_{user_id}', nome_exibicao='Peito')
    db.session.add(musculo)
    db.session.commit()
    return musculo


class TestCreate:
    def test_cria_primeira_versao(self, app):
        with app.app_context():
            u = _criar_usuario('v_create_1')
            versao = VersaoService.create('Bloco 1', date(2026, 1, 1), divisao='ABC', user_id=u.id)

            assert versao is not None
            assert versao.numero_versao == 1
            assert versao.divisao == 'ABC'

    def test_criar_nova_versao_fecha_a_anterior(self, app):
        """Ao criar uma 2a versao sem data_fim explicita, a versao ativa anterior deve ser fechada."""
        with app.app_context():
            u = _criar_usuario('v_create_2')
            v1 = VersaoService.create('Bloco 1', date(2026, 1, 1), user_id=u.id)
            v2 = VersaoService.create('Bloco 2', date(2026, 3, 1), user_id=u.id)

            db.session.refresh(v1)
            assert v1.data_fim == date(2026, 3, 1)
            assert v2.numero_versao == 2

    def test_divisao_invalida_cai_para_abc(self, app):
        with app.app_context():
            u = _criar_usuario('v_create_3')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), divisao='XYZ', user_id=u.id)
            assert versao.divisao == 'ABC'


class TestGetAtiva:
    def test_sem_versao_retorna_none(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_1')
            assert VersaoService.get_ativa(user_id=u.id) is None

    def test_versao_sem_data_fim_e_ativa(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_2')
            VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            ativa = VersaoService.get_ativa_por_data(date(2026, 6, 1), user_id=u.id)
            assert ativa is not None
            assert ativa.descricao == 'Bloco'

    def test_versao_finalizada_nao_e_ativa_apos_data_fim(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_3')
            v = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            VersaoService.finalizar(v.id, date(2026, 2, 1), user_id=u.id)

            ativa_depois = VersaoService.get_ativa_por_data(date(2026, 3, 1), user_id=u.id)
            assert ativa_depois is None

            ativa_durante = VersaoService.get_ativa_por_data(date(2026, 1, 15), user_id=u.id)
            assert ativa_durante is not None


class TestAdicionarERemoverTreino:
    def test_adicionar_treino_a_versao(self, app):
        with app.app_context():
            u = _criar_usuario('v_treino_1')
            musc = _criar_musculo(u.id)
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'peito e triceps', user_id=u.id)
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()

            ok = VersaoService.adicionar_treino(
                versao.id, 'A', 'Treino A', 'peito e triceps', [ex.id], [], user_id=u.id
            )
            assert ok is True

            treinos = VersaoService.get_treinos(versao.id, user_id=u.id)
            assert 'A' in treinos
            assert treinos['A']['exercicios'] == [f'u_{ex.id}']

    def test_nao_adiciona_treino_duplicado_na_mesma_versao(self, app):
        with app.app_context():
            u = _criar_usuario('v_treino_2')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)

            ok1 = VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [], [], user_id=u.id)
            ok2 = VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [], [], user_id=u.id)

            assert ok1 is True
            assert ok2 is False

    def test_remover_treino_da_versao(self, app):
        with app.app_context():
            u = _criar_usuario('v_treino_3')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [], [], user_id=u.id)

            ok = VersaoService.remover_treino(versao.id, 'A', user_id=u.id)
            assert ok is True
            assert 'A' not in VersaoService.get_treinos(versao.id, user_id=u.id)

    def test_remover_treino_inexistente_retorna_false(self, app):
        with app.app_context():
            u = _criar_usuario('v_treino_4')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            ok = VersaoService.remover_treino(versao.id, 'Z', user_id=u.id)
            assert ok is False


class TestGetExerciciosAgrupadosPorTreino:
    """Funcao criada para resolver N+1 (rodada de otimizacao) -- sem teste unitario direto ate aqui."""

    def test_sem_versao_ativa_retorna_dict_vazio(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_1')
            assert VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id) == {}

    def test_agrupa_exercicios_de_usuario_e_de_sistema_por_treino(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_2')
            musc = _criar_musculo(u.id)
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)

            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            TreinoService.create('B', 'Treino B', 'd', user_id=u.id)

            ex_custom = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex_custom)
            db.session.commit()

            ex_sistema = ExercicioSistema(id_original='ag-001', nome='Agachamento', grupo_muscular='Pernas')
            db.session.add(ex_sistema)
            db.session.commit()

            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [ex_custom.id], [], user_id=u.id)
            VersaoService.adicionar_treino(versao.id, 'B', 'Treino B', 'd', [], [ex_sistema.id], user_id=u.id)

            treino_a = Treino.query.filter_by(codigo='A', user_id=u.id).first()
            treino_b = Treino.query.filter_by(codigo='B', user_id=u.id).first()

            agrupado = VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id)

            assert set(agrupado.keys()) == {treino_a.id, treino_b.id}
            assert len(agrupado[treino_a.id]) == 1
            assert agrupado[treino_a.id][0].nome == 'Supino'
            assert agrupado[treino_a.id][0].tipo == 'usuario'
            assert len(agrupado[treino_b.id]) == 1
            assert agrupado[treino_b.id][0].nome == 'Agachamento'
            assert agrupado[treino_b.id][0].tipo == 'base'

    def test_treino_sem_exercicios_aparece_com_lista_vazia(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_3')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            VersaoService.adicionar_treino(versao.id, 'A', 'Treino A', 'd', [], [], user_id=u.id)

            treino_a = Treino.query.filter_by(codigo='A', user_id=u.id).first()
            agrupado = VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id)
            assert agrupado[treino_a.id] == []

    def test_nao_mistura_exercicios_de_usuarios_diferentes(self, app):
        """Isolamento: exercicios de A nao devem aparecer no agrupamento de B."""
        with app.app_context():
            a = _criar_usuario('v_agrupado_iso_a')
            b = _criar_usuario('v_agrupado_iso_b')
            musc_a = _criar_musculo(a.id)
            musc_b = _criar_musculo(b.id)

            versao_a = VersaoService.create('Bloco A', date(2026, 1, 1), user_id=a.id)
            versao_b = VersaoService.create('Bloco B', date(2026, 1, 1), user_id=b.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=a.id)
            TreinoService.create('A', 'Treino A', 'd', user_id=b.id)

            ex_a = ExercicioUsuario(usuario_id=a.id, nome='Exercicio de A', musculo_id=musc_a.id)
            ex_b = ExercicioUsuario(usuario_id=b.id, nome='Exercicio de B', musculo_id=musc_b.id)
            db.session.add_all([ex_a, ex_b])
            db.session.commit()

            VersaoService.adicionar_treino(versao_a.id, 'A', 'Treino A', 'd', [ex_a.id], [], user_id=a.id)
            VersaoService.adicionar_treino(versao_b.id, 'A', 'Treino A', 'd', [ex_b.id], [], user_id=b.id)

            agrupado_a = VersaoService.get_exercicios_agrupados_por_treino(user_id=a.id)
            nomes_a = [ex.nome for lista in agrupado_a.values() for ex in lista]

            assert 'Exercicio de A' in nomes_a
            assert 'Exercicio de B' not in nomes_a


class TestDelete:
    def test_exclui_versao_sem_registros(self, app):
        with app.app_context():
            u = _criar_usuario('v_delete_1')
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            versao_id = versao.id
            ok = VersaoService.delete(versao_id, user_id=u.id)
            assert ok is True
            assert db.session.get(VersaoGlobal, versao_id) is None

    def test_nao_exclui_versao_com_registros(self, app):
        with app.app_context():
            u = _criar_usuario('v_delete_2')
            musc = _criar_musculo(u.id)
            versao = VersaoService.create('Bloco', date(2026, 1, 1), user_id=u.id)
            treino = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex)
            db.session.commit()
            registro = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='janeiro/2026', semana=1,
                exercicio_usuario_id=ex.id, data_registro=date(2026, 1, 5), user_id=u.id
            )
            db.session.add(registro)
            db.session.commit()
            versao_id = versao.id

            ok = VersaoService.delete(versao_id, user_id=u.id)
            assert ok is False
            assert db.session.get(VersaoGlobal, versao_id) is not None
