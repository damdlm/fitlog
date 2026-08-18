"""
Testes para a observação por exercício dentro de um treino
(VersaoExercicio.observacao, até 60 caracteres).

Cobre:
- Salvar a observação ao editar um treino da versão (aluno e professor).
- Truncamento em 60 caracteres mesmo se o form mandar mais.
- Exibição da observação na tela de registrar treino.
- Preservação da observação ao clonar uma versão.
"""
from datetime import date

from models import (
    db, User, Treino, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, ExercicioSistema, Musculo, AlunoProfessor,
)
from services.versao_service import VersaoService


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

    treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='Treino A')
    db.session.add(treino)

    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date(2026, 1, 1), user_id=user.id)
    db.session.add(versao)
    db.session.flush()

    treino_versao = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino='Treino A')
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

    return exercicio, treino, versao, treino_versao


class TestSalvarObservacaoAluno:
    def test_editar_treino_versao_salva_observacao(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_aluno_1')
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_1')

        resp = client.post(
            f'/aluno/versao/{versao_id}/treino/A/editar',
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
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_2')

        texto_longo = 'X' * 90
        client.post(
            f'/aluno/versao/{versao_id}/treino/A/editar',
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
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            chave = f'u_{exercicio.id}'
            versao_id, treino_versao_id = versao.id, treino_versao.id
        _login(client, 'obs_aluno_3')

        client.post(
            f'/aluno/versao/{versao_id}/treino/A/editar',
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

    def test_formulario_de_edicao_preenche_observacao_existente(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_aluno_4')
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            versao_id = versao.id
        _login(client, 'obs_aluno_4')

        resp = client.get(f'/aluno/versao/{versao_id}/treino/A/editar')
        html = resp.get_data(as_text=True)

        assert 'Pegada aberta' in html


class TestSalvarObservacaoProfessor:
    def test_professor_edita_treino_do_aluno_e_salva_observacao(self, client, app):
        with app.app_context():
            professor = _criar_usuario('obs_prof_1', 'professor')
            aluno = _criar_usuario('obs_prof_aluno_1', 'aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
            db.session.commit()
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(aluno)
            chave = f'u_{exercicio.id}'
            aluno_id, versao_id, tv_id = aluno.id, versao.id, treino_versao.id
        _login(client, 'obs_prof_1')

        resp = client.post(
            f'/professor/aluno/{aluno_id}/versao/{versao_id}/treino/A/editar',
            data={
                'nome_treino': 'Treino A',
                'descricao_treino': '',
                'exercicios[]': [chave],
                f'observacao_{chave}': 'Foco na fase excêntrica',
            }
        )

        assert resp.status_code == 302
        with app.app_context():
            ve = VersaoExercicio.query.filter_by(treino_versao_id=tv_id).first()
            assert ve.observacao == 'Foco na fase excêntrica'


class TestObservacaoNaTelaRegistrarTreino:
    def test_observacao_aparece_na_tela_de_registrar_treino(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_reg_1')
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            treino_id = treino.id
        _login(client, 'obs_reg_1')

        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'Pegada aberta' in html

    def test_sem_observacao_nao_mostra_bloco_de_observacao(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_reg_2')
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=False)
            treino_id = treino.id

        _login(client, 'obs_reg_2')
        resp = client.get(f'/registrar/registrar-treino?data=2026-01-05&treino={treino_id}')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        # A classe 'dash-registro-obs' também existe na definição CSS da
        # página (sempre presente); o que indica se o bloco foi de fato
        # renderizado é o ícone, que só aparece dentro do {% if %}.
        assert 'bi-chat-left-text' not in html


class TestObservacaoPreservadaAoClonar:
    def test_clonar_versao_preserva_observacao(self, client, app):
        with app.app_context():
            user = _criar_usuario('obs_clone_1')
            exercicio, treino, versao, treino_versao = _montar_versao_com_treino_e_exercicio(user, com_observacao=True)
            # get_ativa exige que a versão não tenha data_fim e a versão de
            # origem precisa ser finalizada antes de clonar (clone() recusa
            # se já existe uma versão ativa).
            versao.data_fim = date(2026, 1, 10)
            db.session.commit()
            versao_id, user_id = versao.id, user.id

        with app.app_context():
            ok = VersaoService.clone(versao_id, user_id=user_id)
            assert ok is True

            nova_versao = VersaoGlobal.query.filter(
                VersaoGlobal.user_id == user_id,
                VersaoGlobal.id != versao_id
            ).first()
            assert nova_versao is not None

            tv_nova = TreinoVersao.query.filter_by(versao_id=nova_versao.id).first()
            ve_nova = VersaoExercicio.query.filter_by(treino_versao_id=tv_nova.id).first()
            assert ve_nova.observacao == 'Pegada aberta'