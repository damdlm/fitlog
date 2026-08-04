"""Testes para EstatisticaService.calcular_por_treino.

Cobrem o agrupamento de registros por treino antes/depois da correção
do O(T x R) (Fase 3): os registros passaram a ser agrupados uma única
vez num dict, em vez de percorrer a lista inteira para cada treino.
Os testes garantem que o resultado é equivalente ao comportamento
anterior.
"""
from datetime import date, datetime

from models import (
    db, User, Musculo, ExercicioUsuario, ExercicioSistema,
    Treino, VersaoGlobal, RegistroTreino, HistoricoTreino,
)
from services.estatistica_service import EstatisticaService


def _criar_usuario(email):
    user = User(username=email.split('@')[0], email=email)
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()
    return user


def _criar_treino_e_versao(user, codigo='A', numero_versao=1):
    treino = Treino(user_id=user.id, codigo=codigo, nome=f'Treino {codigo}', descricao=f'Treino {codigo}')
    db.session.add(treino)
    versao = VersaoGlobal(numero_versao=numero_versao, descricao=f'V{numero_versao}', divisao='ABC',
                           data_inicio=date.today(), user_id=user.id)
    db.session.add(versao)
    db.session.flush()
    return treino, versao


def _criar_registro(user, treino, versao, historico_carga_rep, **exercicio_kwargs):
    registro = RegistroTreino(
        treino_id=treino.id,
        versao_id=versao.id,
        periodo='manha',
        semana=1,
        user_id=user.id,
        data_registro=datetime.now(),
        **exercicio_kwargs,
    )
    db.session.add(registro)
    db.session.flush()
    carga, repeticoes = historico_carga_rep
    db.session.add(HistoricoTreino(registro_id=registro.id, carga=carga, repeticoes=repeticoes))
    db.session.commit()
    return registro


def test_nenhum_treino_retorna_dict_vazio(app, db):
    with app.app_context():
        user = _criar_usuario('sem_treino@teste.com')
        stats = EstatisticaService.calcular_por_treino(user_id=user.id)
        assert stats == {}


def test_um_treino_sem_registros(app, db):
    with app.app_context():
        user = _criar_usuario('treino_sem_registro@teste.com')
        treino, _versao = _criar_treino_e_versao(user)

        stats = EstatisticaService.calcular_por_treino(user_id=user.id)

        assert stats[treino.id]['qtd_registros'] == 0
        assert stats[treino.id]['total_series'] == 0
        assert stats[treino.id]['volume_total'] == 0
        assert stats[treino.id]['qtd_exercicios'] == 0


def test_um_treino_com_varios_registros(app, db):
    with app.app_context():
        user = _criar_usuario('treino_varios_registros@teste.com')
        musculo = Musculo(nome='peito', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.flush()
        ex1 = ExercicioUsuario(usuario_id=user.id, nome='Supino', musculo_id=musculo.id)
        ex2 = ExercicioUsuario(usuario_id=user.id, nome='Crucifixo', musculo_id=musculo.id)
        db.session.add_all([ex1, ex2])
        db.session.flush()

        treino, versao = _criar_treino_e_versao(user)
        _criar_registro(user, treino, versao, (100, 10), exercicio_usuario_id=ex1.id)
        _criar_registro(user, treino, versao, (50, 12), exercicio_usuario_id=ex2.id)

        stats = EstatisticaService.calcular_por_treino(user_id=user.id)

        assert stats[treino.id]['qtd_registros'] == 2
        assert stats[treino.id]['total_series'] == 2
        assert stats[treino.id]['volume_total'] == 100 * 10 + 50 * 12
        assert stats[treino.id]['qtd_exercicios'] == 2  # ex1 e ex2


def test_varios_treinos_registros_permanecem_associados_ao_treino_correto(app, db):
    with app.app_context():
        user = _criar_usuario('varios_treinos@teste.com')
        musculo = Musculo(nome='costas', nome_exibicao='Costas')
        db.session.add(musculo)
        db.session.flush()
        ex = ExercicioUsuario(usuario_id=user.id, nome='Remada', musculo_id=musculo.id)
        db.session.add(ex)
        db.session.flush()

        treino_a, versao_a = _criar_treino_e_versao(user, codigo='A', numero_versao=1)
        treino_b, versao_b = _criar_treino_e_versao(user, codigo='B', numero_versao=2)

        _criar_registro(user, treino_a, versao_a, (80, 8), exercicio_usuario_id=ex.id)
        _criar_registro(user, treino_a, versao_a, (80, 8), exercicio_usuario_id=ex.id)
        _criar_registro(user, treino_b, versao_b, (60, 10), exercicio_usuario_id=ex.id)

        stats = EstatisticaService.calcular_por_treino(user_id=user.id)

        assert stats[treino_a.id]['qtd_registros'] == 2
        assert stats[treino_a.id]['volume_total'] == 80 * 8 * 2

        assert stats[treino_b.id]['qtd_registros'] == 1
        assert stats[treino_b.id]['volume_total'] == 60 * 10


def test_exercicio_personalizado_e_do_catalogo_no_mesmo_treino(app, db):
    with app.app_context():
        user = _criar_usuario('misto@teste.com')

        musculo = Musculo(nome='pernas', nome_exibicao='Pernas')
        db.session.add(musculo)
        db.session.flush()
        ex_custom = ExercicioUsuario(usuario_id=user.id, nome='Leg Press', musculo_id=musculo.id)
        db.session.add(ex_custom)

        ex_sistema = ExercicioSistema(id_original='0010', nome='Agachamento', grupo_muscular='Pernas')
        db.session.add(ex_sistema)
        db.session.flush()

        treino, versao = _criar_treino_e_versao(user)
        _criar_registro(user, treino, versao, (100, 10), exercicio_usuario_id=ex_custom.id)
        _criar_registro(user, treino, versao, (120, 6), exercicio_base_id=ex_sistema.id)

        stats = EstatisticaService.calcular_por_treino(user_id=user.id)

        assert stats[treino.id]['qtd_registros'] == 2
        assert stats[treino.id]['qtd_exercicios'] == 2
        assert stats[treino.id]['volume_total'] == 100 * 10 + 120 * 6
