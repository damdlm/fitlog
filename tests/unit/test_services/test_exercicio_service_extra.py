"""Testes para as funções de ExercicioService realmente usadas pela
aplicação (fora da propagação professor->aluno, já coberta em
test_exercicio_service.py original): resolução de exercício por ID
(base vs. usuário), listagens usadas nas telas de catálogo/progresso,
exclusão (com a checagem de "em uso"), reordenação dentro de um
treino e a busca em lote da última sessão de séries.
"""
from datetime import date, datetime, timezone

from models import (
    db, User, Musculo, ExercicioSistema, ExercicioUsuario, ExercicioCustomizado,
    VersaoGlobal, TreinoVersao, VersaoExercicio, RegistroTreino, HistoricoTreino,
)
from services.exercicio_service import ExercicioService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo_usuario)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.commit()
    return user


def _criar_exercicio_base(nome='Supino Reto', grupo_muscular='Peito'):
    ex = ExercicioSistema(id_original=f'sys-{nome}', nome=nome, grupo_muscular=grupo_muscular)
    db.session.add(ex)
    db.session.commit()
    return ex


def _criar_exercicio_usuario(usuario_id, nome='Rosca Direta', musculo_id=None):
    ex = ExercicioUsuario(usuario_id=usuario_id, nome=nome, musculo_id=musculo_id)
    db.session.add(ex)
    db.session.commit()
    return ex


def _criar_versao_com_treino(usuario_id, codigo='A'):
    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date.today(), user_id=usuario_id)
    db.session.add(versao)
    db.session.commit()
    tv = TreinoVersao(versao_id=versao.id, codigo=codigo, nome_treino=f'Treino {codigo}')
    db.session.add(tv)
    db.session.commit()
    return versao, tv


class TestGetById:

    def test_resolve_exercicio_base_pelo_id(self, app, db):
        ex_base = _criar_exercicio_base('Agachamento', 'Pernas')
        resultado = ExercicioService.get_by_id(ex_base.id, user_id=999)
        assert resultado is not None
        assert resultado.tipo == 'base'
        assert resultado.is_custom is False
        assert resultado.musculo == 'Pernas'

    def test_resolve_exercicio_do_usuario_pelo_id(self, app, db):
        user = _criar_usuario('ex_get_1')
        ex = _criar_exercicio_usuario(user.id, 'Puxada')
        resultado = ExercicioService.get_by_id(ex.id, user_id=user.id)
        assert resultado is not None
        assert resultado.tipo == 'usuario'
        assert resultado.is_custom is True

    def test_exercicio_de_outro_usuario_nao_e_retornado(self, app, db):
        """Isolamento: o ID de exercício de um usuário nunca deve
        resolver pra outro usuário que não é o dono."""
        dono = _criar_usuario('ex_get_dono')
        outro = _criar_usuario('ex_get_outro')
        ex = _criar_exercicio_usuario(dono.id, 'Privado do dono')
        resultado = ExercicioService.get_by_id(ex.id, user_id=outro.id)
        assert resultado is None

    def test_id_inexistente_retorna_none(self, app, db):
        assert ExercicioService.get_by_id(999999, user_id=1) is None


class TestGetExerciciosCompletos:

    def test_combina_catalogo_base_e_exercicios_do_usuario(self, app, db):
        user = _criar_usuario('ex_completos_1')
        _criar_exercicio_base('Supino')
        _criar_exercicio_usuario(user.id, 'Exercicio Proprio')

        resultado = ExercicioService.get_exercicios_completos(user_id=user.id)
        nomes = [ex.nome for ex in resultado]
        assert 'Supino' in nomes
        assert 'Exercicio Proprio' in nomes

    def test_nao_mistura_exercicios_de_outro_usuario(self, app, db):
        user_a = _criar_usuario('ex_completos_a')
        user_b = _criar_usuario('ex_completos_b')
        _criar_exercicio_usuario(user_a.id, 'Só do A')
        _criar_exercicio_usuario(user_b.id, 'Só do B')

        resultado_a = ExercicioService.get_exercicios_completos(user_id=user_a.id)
        nomes_a = [ex.nome for ex in resultado_a]
        assert 'Só do A' in nomes_a
        assert 'Só do B' not in nomes_a

    def test_sem_usuario_retorna_lista_vazia(self, app, db):
        assert ExercicioService.get_exercicios_completos(user_id=None) == []

    def test_nao_deixa_objetos_sujos_na_sessao(self, app, db):
        """Regressão do bug de WORKER TIMEOUT documentado no código:
        depois de montar a listagem, nada pode ficar pendente para
        escrita no próximo autoflush/commit."""
        user = _criar_usuario('ex_completos_sujeira')
        _criar_exercicio_base('Leg Press')
        ExercicioService.get_exercicios_completos(user_id=user.id)
        assert len(db.session.dirty) == 0


class TestGetExerciciosDosTreinos:

    def test_so_retorna_exercicios_associados_a_algum_treino(self, app, db):
        user = _criar_usuario('ex_treinos_1')
        ex_base = _criar_exercicio_base('Cadeira Extensora')
        _criar_exercicio_usuario(user.id, 'Nunca usado em treino')

        versao, tv = _criar_versao_com_treino(user.id)
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=ex_base.id, ordem=1))
        db.session.commit()

        resultado = ExercicioService.get_exercicios_dos_treinos(user_id=user.id)
        nomes = [ex.nome for ex in resultado]
        assert 'Cadeira Extensora' in nomes
        assert 'Nunca usado em treino' not in nomes

    def test_sem_usuario_retorna_vazio(self, app, db):
        assert ExercicioService.get_exercicios_dos_treinos(user_id=None) == []


class TestGetByTreino:

    def test_retorna_exercicios_do_treino_na_versao_ativa(self, app, db):
        user = _criar_usuario('ex_by_treino_1')
        ex_base = _criar_exercicio_base('Rosca Scott')
        versao, tv = _criar_versao_com_treino(user.id, codigo='A')
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=ex_base.id, ordem=1))
        db.session.commit()

        resultado = ExercicioService.get_by_treino(tv.id, user_id=user.id)
        assert len(resultado) == 1

    def test_treino_inexistente_retorna_vazio(self, app, db):
        user = _criar_usuario('ex_by_treino_2')
        assert ExercicioService.get_by_treino(999999, user_id=user.id) == []

    def test_sem_usuario_retorna_vazio(self, app, db):
        assert ExercicioService.get_by_treino(1, user_id=None) == []


class TestDeleteExercicioUsuario:
    """Cobre o bug real corrigido nesta sessão: a checagem de 'em uso'
    usava uma coluna (VersaoExercicio.exercicio_id) que não existe --
    isso fazia toda chamada cair no except e SEMPRE devolver False,
    mesmo pra exercícios que não estavam em uso em nenhum treino."""

    def test_exclui_exercicio_nao_usado_em_nenhuma_versao(self, app, db):
        user = _criar_usuario('ex_del_1')
        ex = _criar_exercicio_usuario(user.id, 'Pode excluir')

        sucesso = ExercicioService.delete_exercicio_usuario(ex.id, user_id=user.id)

        assert sucesso is True
        assert db.session.get(ExercicioUsuario, ex.id) is None

    def test_nao_exclui_exercicio_em_uso_em_versao(self, app, db):
        user = _criar_usuario('ex_del_2')
        ex = _criar_exercicio_usuario(user.id, 'Em uso')
        versao, tv = _criar_versao_com_treino(user.id)
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=1))
        db.session.commit()

        sucesso = ExercicioService.delete_exercicio_usuario(ex.id, user_id=user.id)

        assert sucesso is False
        assert db.session.get(ExercicioUsuario, ex.id) is not None

    def test_nao_exclui_exercicio_de_outro_usuario(self, app, db):
        dono = _criar_usuario('ex_del_dono')
        outro = _criar_usuario('ex_del_outro')
        ex = _criar_exercicio_usuario(dono.id, 'Não é do outro')

        sucesso = ExercicioService.delete_exercicio_usuario(ex.id, user_id=outro.id)

        assert sucesso is False
        assert db.session.get(ExercicioUsuario, ex.id) is not None

    def test_id_inexistente_retorna_false(self, app, db):
        user = _criar_usuario('ex_del_3')
        assert ExercicioService.delete_exercicio_usuario(999999, user_id=user.id) is False


class TestDeleteExercicioCustomizado:
    """ExercicioCustomizado é um alias de ExercicioUsuario (ver
    models.py) -- mesmo bug, mesma correção, tabela idêntica."""

    def test_exclui_exercicio_customizado_nao_usado(self, app, db):
        user = _criar_usuario('ex_delc_1')
        ex = ExercicioCustomizado(usuario_id=user.id, nome='Custom livre')
        db.session.add(ex)
        db.session.commit()

        sucesso = ExercicioService.delete_exercicio_customizado(ex.id, user_id=user.id)

        assert sucesso is True
        assert db.session.get(ExercicioCustomizado, ex.id) is None

    def test_nao_exclui_customizado_em_uso(self, app, db):
        user = _criar_usuario('ex_delc_2')
        ex = ExercicioCustomizado(usuario_id=user.id, nome='Custom em uso')
        db.session.add(ex)
        db.session.commit()
        versao, tv = _criar_versao_com_treino(user.id)
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=1))
        db.session.commit()

        sucesso = ExercicioService.delete_exercicio_customizado(ex.id, user_id=user.id)

        assert sucesso is False
        assert db.session.get(ExercicioCustomizado, ex.id) is not None


class TestReordenarExercicios:

    def test_reordena_exercicios_usuario_e_base_no_mesmo_treino(self, app, db):
        user = _criar_usuario('ex_reord_1')
        ex_usuario = _criar_exercicio_usuario(user.id, 'Do usuário')
        ex_base = _criar_exercicio_base('Do catálogo')
        versao, tv = _criar_versao_com_treino(user.id)
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex_usuario.id, ordem=0))
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=ex_base.id, ordem=1))
        db.session.commit()

        nova_ordem = [f'b_{ex_base.id}', f'u_{ex_usuario.id}']
        sucesso = ExercicioService.reordenar_exercicios(versao.id, 'A', nova_ordem, user_id=user.id)

        assert sucesso is True
        ve_base = VersaoExercicio.query.filter_by(treino_versao_id=tv.id, exercicio_base_id=ex_base.id).first()
        ve_usuario = VersaoExercicio.query.filter_by(treino_versao_id=tv.id, exercicio_usuario_id=ex_usuario.id).first()
        assert ve_base.ordem == 0
        assert ve_usuario.ordem == 1

    def test_versao_inexistente_retorna_false(self, app, db):
        user = _criar_usuario('ex_reord_2')
        assert ExercicioService.reordenar_exercicios(999999, 'A', [], user_id=user.id) is False

    def test_treino_codigo_inexistente_na_versao_retorna_false(self, app, db):
        user = _criar_usuario('ex_reord_3')
        versao, tv = _criar_versao_com_treino(user.id, codigo='A')
        assert ExercicioService.reordenar_exercicios(versao.id, 'Z', [], user_id=user.id) is False


class TestGetUltimaSessaoSeriesEmLote:

    def test_busca_ultima_sessao_de_varios_exercicios_de_uma_vez(self, app, db):
        user = _criar_usuario('ex_lote_1')
        ex_base = _criar_exercicio_base('Supino Lote')
        versao, tv = _criar_versao_com_treino(user.id)

        registro = RegistroTreino(
            treino_versao_id=tv.id, versao_id=versao.id, periodo='2026-09',
            semana=1, data_registro=datetime.now(timezone.utc),
            user_id=user.id, exercicio_base_id=ex_base.id,
        )
        db.session.add(registro)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=registro.id, carga=40, repeticoes=10, ordem=1))
        db.session.add(HistoricoTreino(registro_id=registro.id, carga=40, repeticoes=8, ordem=2))
        db.session.commit()

        # objeto "exercicio" simplificado no formato que a função espera
        class _ExFake:
            def __init__(self, id_, tipo, prefixo):
                self.id = id_
                self.tipo = tipo
                self.prefixo = prefixo

        exercicios = [_ExFake(ex_base.id, 'base', 'b_')]
        resultado = ExercicioService.get_ultima_sessao_series_em_lote(
            exercicios, versao.id, user_id=user.id
        )

        chave = f'b_{ex_base.id}'
        assert chave in resultado
        assert resultado[chave] == [
            {'carga': 40.0, 'repeticoes': 10},
            {'carga': 40.0, 'repeticoes': 8},
        ]

    def test_exercicio_sem_historico_nao_aparece_no_resultado(self, app, db):
        user = _criar_usuario('ex_lote_2')
        ex_base = _criar_exercicio_base('Nunca treinado')
        versao, tv = _criar_versao_com_treino(user.id)

        class _ExFake:
            def __init__(self, id_, tipo, prefixo):
                self.id = id_
                self.tipo = tipo
                self.prefixo = prefixo

        resultado = ExercicioService.get_ultima_sessao_series_em_lote(
            [_ExFake(ex_base.id, 'base', 'b_')], versao.id, user_id=user.id
        )
        assert resultado == {}

    def test_lista_vazia_de_exercicios_retorna_vazio(self, app, db):
        user = _criar_usuario('ex_lote_3')
        assert ExercicioService.get_ultima_sessao_series_em_lote([], 1, user_id=user.id) == {}
