"""
Testes unitários para services/versao_service.py.

Foca nas funções ainda usadas pelo fluxo atual (versão sem divisão fixa,
"Cadastrar Treinos"): get_ativa/get_ativa_por_data, e
get_exercicios_agrupados_por_treino (criada para resolver N+1 em
professor/aluno/FitBot).

Os fluxos antigos de divisão fixa (ABC/ABCD/ABCDE) -- VersaoService.create/
clone/delete/finalizar/adicionar_treino/remover_treino, e o antigo
TreinoService de CRUD -- foram removidos junto com as telas que os usavam
("Nova Versão", "Meus Treinos"); versões e treinos agora só se criam via
VersaoService.create_livre/adicionar_treino_livre.
"""
from datetime import date

from models import (
    db, User, Musculo, VersaoGlobal, TreinoVersao,
    VersaoExercicio, ExercicioUsuario, ExercicioSistema,
)
from services.versao_service import VersaoService


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


def _criar_versao(user_id, descricao='Bloco', data_inicio=date(2026, 1, 1), data_fim=None):
    versao = VersaoGlobal(numero_versao=1, descricao=descricao, divisao='ABC',
                           data_inicio=data_inicio, data_fim=data_fim, user_id=user_id)
    db.session.add(versao)
    db.session.commit()
    return versao


def _criar_treino(versao_id, codigo='A', nome='Treino A', descricao='d'):
    treino = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=nome, descricao_treino=descricao)
    db.session.add(treino)
    db.session.commit()
    return treino


class TestGetAtiva:
    def test_sem_versao_retorna_none(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_1')
            assert VersaoService.get_ativa(user_id=u.id) is None

    def test_versao_sem_data_fim_e_ativa(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_2')
            _criar_versao(u.id, descricao='Bloco', data_inicio=date(2026, 1, 1))
            ativa = VersaoService.get_ativa_por_data(date(2026, 6, 1), user_id=u.id)
            assert ativa is not None
            assert ativa.descricao == 'Bloco'

    def test_versao_finalizada_nao_e_ativa_apos_data_fim(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_3')
            _criar_versao(u.id, descricao='Bloco', data_inicio=date(2026, 1, 1), data_fim=date(2026, 2, 1))

            ativa_depois = VersaoService.get_ativa_por_data(date(2026, 3, 1), user_id=u.id)
            assert ativa_depois is None

            ativa_durante = VersaoService.get_ativa_por_data(date(2026, 1, 15), user_id=u.id)
            assert ativa_durante is not None


class TestGetExerciciosAgrupadosPorTreino:
    """Funcao criada para resolver N+1 (rodada de otimizacao)."""

    def test_sem_versao_ativa_retorna_dict_vazio(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_1')
            assert VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id) == {}

    def test_agrupa_exercicios_de_usuario_e_de_sistema_por_treino(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_2')
            musc = _criar_musculo(u.id)
            versao = _criar_versao(u.id)

            treino_a = _criar_treino(versao.id, codigo='A', nome='Treino A')
            treino_b = _criar_treino(versao.id, codigo='B', nome='Treino B')

            ex_custom = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex_custom)
            db.session.commit()

            ex_sistema = ExercicioSistema(id_original='ag-001', nome='Agachamento', grupo_muscular='Pernas')
            db.session.add(ex_sistema)
            db.session.commit()

            db.session.add(VersaoExercicio(treino_versao_id=treino_a.id, exercicio_usuario_id=ex_custom.id, ordem=1))
            db.session.add(VersaoExercicio(treino_versao_id=treino_b.id, exercicio_base_id=ex_sistema.id, ordem=1))
            db.session.commit()

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
            versao = _criar_versao(u.id)
            treino_a = _criar_treino(versao.id, codigo='A', nome='Treino A')

            agrupado = VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id)
            assert agrupado[treino_a.id] == []

    def test_nao_mistura_exercicios_de_usuarios_diferentes(self, app):
        """Isolamento: exercicios de A nao devem aparecer no agrupamento de B."""
        with app.app_context():
            a = _criar_usuario('v_agrupado_iso_a')
            b = _criar_usuario('v_agrupado_iso_b')
            musc_a = _criar_musculo(a.id)
            musc_b = _criar_musculo(b.id)

            versao_a = _criar_versao(a.id, descricao='Bloco A')
            versao_b = _criar_versao(b.id, descricao='Bloco B')
            treino_a = _criar_treino(versao_a.id, codigo='A', nome='Treino A')
            treino_b = _criar_treino(versao_b.id, codigo='A', nome='Treino A')

            ex_a = ExercicioUsuario(usuario_id=a.id, nome='Exercicio de A', musculo_id=musc_a.id)
            ex_b = ExercicioUsuario(usuario_id=b.id, nome='Exercicio de B', musculo_id=musc_b.id)
            db.session.add_all([ex_a, ex_b])
            db.session.commit()

            db.session.add(VersaoExercicio(treino_versao_id=treino_a.id, exercicio_usuario_id=ex_a.id, ordem=1))
            db.session.add(VersaoExercicio(treino_versao_id=treino_b.id, exercicio_usuario_id=ex_b.id, ordem=1))
            db.session.commit()

            agrupado_a = VersaoService.get_exercicios_agrupados_por_treino(user_id=a.id)
            nomes_a = [ex.nome for lista in agrupado_a.values() for ex in lista]

            assert 'Exercicio de A' in nomes_a
            assert 'Exercicio de B' not in nomes_a
