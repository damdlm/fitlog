"""Regressão: colisão de ID entre ExercicioUsuario e ExercicioSistema
em EstatisticaService.preparar_dados_tabela() / stats/visualizar_tabela.html.

Os dois modelos têm sequências de ID independentes, então um
ExercicioUsuario e um ExercicioSistema podem ter o mesmo número de id.
Antes da correção, a função usava só `ex.id` como chave (e
`r.exercicio_id`, que faz coalesce entre exercicio_usuario_id e
exercicio_base_id) -- se os dois tivessem o mesmo id, o registro do
exercício errado aparecia na célula do outro na Tabela de Progresso.
"""
from datetime import date, datetime, timezone

from models import (
    db, User, Musculo, ExercicioUsuario, ExercicioSistema,
    Treino, VersaoGlobal, TreinoVersao, VersaoExercicio,
    RegistroTreino, HistoricoTreino,
)
from services.estatistica_service import EstatisticaService
from services.exercicio_service import ExercicioService


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def test_ids_colidentes_nao_se_misturam_na_tabela(app, db):
    with app.app_context():
        user = User(username='colisao_id', email='colisao_id@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()

        musculo = Musculo(nome='m_colisao', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.commit()

        # Força os dois exercícios a terem o MESMO id numérico, em
        # tabelas diferentes (exercicios_usuario x exercicios_sistema).
        ex_usuario = ExercicioUsuario(usuario_id=user.id, nome='Supino personalizado', musculo_id=musculo.id)
        db.session.add(ex_usuario)
        db.session.commit()

        ex_sistema = ExercicioSistema(id_original='colide-1', nome='Supino do catálogo', grupo_muscular='Peito')
        db.session.add(ex_sistema)
        db.session.commit()

        # Ajusta o id do exercicio_sistema para bater com o do exercicio_usuario
        # (garante a colisão independentemente da ordem de criação nas tabelas).
        db.session.execute(
            db.text("UPDATE exercicios_sistema SET id = :novo_id WHERE id = :id_atual"),
            {"novo_id": ex_usuario.id, "id_atual": ex_sistema.id},
        )
        db.session.commit()
        ex_sistema_id = ex_usuario.id  # agora colidem de propósito

        treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='')
        db.session.add(treino)
        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                               data_inicio=date.today(), user_id=user.id)
        db.session.add(versao)
        db.session.commit()

        tv = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino=treino.nome, descricao_treino='')
        db.session.add(tv)
        db.session.commit()
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex_usuario.id, ordem=1))
        db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_base_id=ex_sistema_id, ordem=2))
        db.session.commit()

        # Um registro para cada um dos dois exercícios com o mesmo id numérico
        reg_usuario = RegistroTreino(
            treino_id=treino.id, versao_id=versao.id, periodo='periodo', semana=1,
            exercicio_usuario_id=ex_usuario.id, data_registro=datetime.now(timezone.utc), user_id=user.id,
        )
        db.session.add(reg_usuario)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=reg_usuario.id, carga=100, repeticoes=10))

        reg_sistema = RegistroTreino(
            treino_id=treino.id, versao_id=versao.id, periodo='periodo', semana=1,
            exercicio_base_id=ex_sistema_id, data_registro=datetime.now(timezone.utc), user_id=user.id,
        )
        db.session.add(reg_sistema)
        db.session.commit()
        db.session.add(HistoricoTreino(registro_id=reg_sistema.id, carga=40, repeticoes=15))
        db.session.commit()

        exercicios = ExercicioService.get_exercicios_completos(user_id=user.id)
        exercicios = [e for e in exercicios if e.id == ex_usuario.id]
        assert len(exercicios) == 2  # um 'usuario' e um 'base', mesmo id numérico

        registros = RegistroTreino.query.filter_by(user_id=user.id).all()
        dados = EstatisticaService.preparar_dados_tabela(exercicios, registros, "todas", {})

        key = f"periodo_1"
        chave_usuario = next(e for e in exercicios if e.tipo == 'usuario')
        chave_base = next(e for e in exercicios if e.tipo == 'base')

        entrada_usuario = dados['registros_por_exercicio'][f"usuario_{chave_usuario.id}"].get(key)
        entrada_base = dados['registros_por_exercicio'][f"base_{chave_base.id}"].get(key)

        assert entrada_usuario is not None and entrada_base is not None
        # Cada entrada deve ter as séries do SEU registro, não do outro
        assert entrada_usuario['series'][0]['carga'] == 100.0
        assert entrada_base['series'][0]['carga'] == 40.0
