"""Testes para EstatisticaService.calcular_por_musculo.

Cobrem as duas origens possíveis de exercício em RegistroTreino:
- exercicio_base_id -> catálogo do sistema (ExercicioSistema.grupo_muscular)
- exercicio_usuario_id -> exercício personalizado (via tabela Musculo)
"""
from datetime import date, datetime

from models import (
    db, User, Musculo, ExercicioUsuario, ExercicioSistema,
    TreinoVersao, VersaoGlobal, RegistroTreino, HistoricoTreino,
)
from services.estatistica_service import EstatisticaService


def _criar_usuario(email):
    user = User(username=email.split('@')[0], email=email)
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()
    return user


def _criar_treino_e_versao(user):
    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date.today(), user_id=user.id)
    db.session.add(versao)
    db.session.flush()
    treino = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A', descricao_treino='Treino A')
    db.session.add(treino)
    db.session.flush()
    return treino, versao


def _criar_registro(user, treino, versao, historico_carga_rep, **exercicio_kwargs):
    registro = RegistroTreino(
        treino_versao_id=treino.id,
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


def test_exercicio_do_catalogo_conta_pelo_grupo_muscular(app, db):
    with app.app_context():
        user = _criar_usuario('aluno1@teste.com')
        ex_sistema = ExercicioSistema(id_original='0001', nome='Supino Reto', grupo_muscular='Peito')
        db.session.add(ex_sistema)
        db.session.flush()
        treino, versao = _criar_treino_e_versao(user)
        _criar_registro(user, treino, versao, (100, 10), exercicio_base_id=ex_sistema.id)

        stats = EstatisticaService.calcular_por_musculo(user_id=user.id)

        assert stats['Peito'] == {
            'qtd_exercicios': 1, 'qtd_registros': 1,
            'total_series': 1, 'volume_total': 1000.0,
        }


def test_exercicio_personalizado_conta_pela_tabela_musculo(app, db):
    with app.app_context():
        user = _criar_usuario('aluno2@teste.com')
        musculo = Musculo(nome='costas', nome_exibicao='Costas')
        db.session.add(musculo)
        db.session.flush()
        ex_custom = ExercicioUsuario(usuario_id=user.id, nome='Remada Curvada', musculo_id=musculo.id)
        db.session.add(ex_custom)
        db.session.flush()
        treino, versao = _criar_treino_e_versao(user)
        _criar_registro(user, treino, versao, (80, 8), exercicio_usuario_id=ex_custom.id)

        stats = EstatisticaService.calcular_por_musculo(user_id=user.id)

        assert stats['Costas'] == {
            'qtd_exercicios': 1, 'qtd_registros': 1,
            'total_series': 1, 'volume_total': 640.0,
        }


def test_soma_catalogo_e_personalizado_no_mesmo_usuario(app, db):
    with app.app_context():
        user = _criar_usuario('aluno3@teste.com')

        ex_sistema = ExercicioSistema(id_original='0002', nome='Agachamento', grupo_muscular='Quadríceps')
        db.session.add(ex_sistema)

        musculo = Musculo(nome='quadriceps', nome_exibicao='Quadríceps')
        db.session.add(musculo)
        db.session.flush()
        ex_custom = ExercicioUsuario(usuario_id=user.id, nome='Leg Press', musculo_id=musculo.id)
        db.session.add(ex_custom)
        db.session.flush()

        treino, versao = _criar_treino_e_versao(user)
        _criar_registro(user, treino, versao, (150, 8), exercicio_base_id=ex_sistema.id)
        # nova versão/treino evita colidir com o UniqueConstraint (user_id, codigo)
        versao2 = VersaoGlobal(numero_versao=2, descricao='V2', divisao='ABC',
                                data_inicio=date.today(), user_id=user.id)
        db.session.add(versao2)
        db.session.flush()
        _criar_registro(user, treino, versao2, (100, 12), exercicio_usuario_id=ex_custom.id)

        stats = EstatisticaService.calcular_por_musculo(user_id=user.id)

        # Nomes iguais ("Quadríceps" nos dois lados) devem ser somados na mesma chave
        assert stats['Quadríceps']['qtd_registros'] == 2
        assert stats['Quadríceps']['total_series'] == 2
        assert stats['Quadríceps']['volume_total'] == 150 * 8 + 100 * 12
