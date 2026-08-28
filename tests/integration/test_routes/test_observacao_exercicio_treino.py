"""
Testes para a observação por exercício dentro de um treino
(VersaoExercicio.observacao, até 60 caracteres).

Cobre:
- Salvar a observação ao editar um treino via tela "Cadastrar Treinos".
- Truncamento em 60 caracteres mesmo se o form mandar mais.
- Exibição da observação na tela de registrar treino.
"""
from datetime import date

from models import (
    db, User, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, Musculo,
)


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _montar_versao_com_treino_e_exercicio(user, com_observacao=False):
    """Cria: 1 exercício custom, 1 treino 'A', 1 versão ativa com esse
    treino, e o exercício associado (com ou sem observação)."""
    musculo = Musculo.query.filter_by(nome_exibicao='Peito').first()
    if not musculo:
        musculo = Musculo(nome='peito', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.flush()

    exercicio = ExercicioUsuario(usuario_id=user.id, nome='Supino Reto', musculo_id=musculo.id)
    db.session.add(exercicio)

    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date(2026, 1, 1), user_id=user.id)
    db.session.add(versao)
    db.session.flush()

    treino_versao = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A')
    db.session.add(treino_versao)
    db.session.flush()

    ve = VersaoExercicio(
        treino_versao_id=treino_versao.id,
        exercicio_usuario_id=exercicio.id,
        ordem=0,
        observacao='Pegada aberta' if com_observacao else None,
    )
    db.session.add(ve)
    db.session.commit()

    return exercicio, versao, treino_versao


class TestSalvarObservacaoAluno:
    def test_cadastrar_treinos_salvar_treino_salva_observacao(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_aluno_1')
            exercicio, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_1')

        resp = client.post(
            f'/aluno/cadastrar-treinos/{versao_id}/treino/{treino_versao_id}',
            data={
                'nome_treino': 'Treino A',
                'descricao_treino': '',
                'exercicios[]': [chave],
                f'observacao_{chave}': 'Cadência lenta na descida',
            }
        )

        assert resp.status_code == 302
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao_id).first()
            assert ve.observacao == 'Cadência lenta na descida'

    def test_observacao_e_truncada_em_60_caracteres(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_aluno_2')
            exercicio, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_2')

        texto_longo = 'X' * 90
        client.post(
            f'/aluno/cadastrar-treinos/{versao_id}/treino/{treino_versao_id}',
            data={
                'nome_treino': 'Treino A',
                'descricao_treino': '',
                'exercicios[]': [chave],
                f'observacao_{chave}': texto_longo,
            }
        )

        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao_id).first()
            assert len(ve.observacao) == 60
            assert ve.observacao == 'X' * 60

    def test_editar_sem_observacao_grava_none(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_aluno_3')
            exercicio, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_3')

        client.post(
            f'/aluno/cadastrar-treinos/{versao_id}/treino/{treino_versao_id}',
            data={
                'nome_treino': 'Treino A',
                'descricao_treino': '',
                'exercicios[]': [chave],
                f'observacao_{chave}': '',
            }
        )

        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=treino_versao_id).first()
            assert ve.observacao is None


class TestObservacaoNaTelaRegistrarTreino:
    def test_observacao_aparece_na_tela_de_registrar_treino(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_reg_1')
            exercicio, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            treino_versao_id = treino_versao.id
        _login(client, 'obs_reg_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_versao_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'Pegada aberta' in html

    def test_sem_observacao_nao_mostra_bloco_de_observacao(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_reg_2')
            exercicio, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=False)
            treino_versao_id = treino_versao.id

        _login(client, 'obs_reg_2')
        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_versao_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        # A classe 'dash-registro-obs' também existe na definição CSS da
        # página (sempre presente); o que indica se o bloco foi de fato
        # renderizado é o ícone, que só aparece dentro do {% if %}.
        assert 'bi-chat-left-text' not in html
