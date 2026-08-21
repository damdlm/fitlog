"""
Testes para a propagação automática de exercícios: quando um PROFESSOR
cadastra um exercício próprio (ExercicioService.criar_exercicio_customizado),
o mesmo exercício é copiado pra cada aluno ativo vinculado a ele, pra que
os alunos possam usar o mesmo exercício nos treinos deles.
"""
from models import db, User, AlunoProfessor, ExercicioCustomizado
from services.exercicio_service import ExercicioService


def _criar_usuario(username, tipo_usuario='aluno', ativo=True):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title(),
                ativo=ativo)
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _vincular(aluno, professor, ativo=True):
    vinculo = AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=ativo)
    db.session.add(vinculo)
    db.session.commit()
    return vinculo


class TestPropagacaoExercicioProfessorParaAlunos:
    def test_professor_cadastra_exercicio_e_alunos_recebem_copia(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_1', 'professor')
            aluno1 = _criar_usuario('aluno_ex_1a')
            aluno2 = _criar_usuario('aluno_ex_1b')
            _vincular(aluno1, professor)
            _vincular(aluno2, professor)

            ex = ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Supino Inclinado', musculo_nome='Peito',
                descricao='Banco a 30 graus'
            )
            assert ex is not None

            copia1 = ExercicioCustomizado.query.filter_by(usuario_id=aluno1.id, nome='Supino Inclinado').first()
            copia2 = ExercicioCustomizado.query.filter_by(usuario_id=aluno2.id, nome='Supino Inclinado').first()

            assert copia1 is not None
            assert copia2 is not None
            assert copia1.descricao == 'Banco a 30 graus'
            assert copia1.copiado_de_professor_id == professor.id
            assert copia2.copiado_de_professor_id == professor.id
            # Mesmo músculo do exercício original do professor
            assert copia1.musculo_id == ex.musculo_id

    def test_copias_sao_independentes_do_original(self, app):
        """Editar/excluir a cópia do aluno não deve mexer no exercício
        original do professor, e vice-versa -- são registros
        independentes, só relacionados pela informação de origem."""
        with app.app_context():
            professor = _criar_usuario('prof_ex_2', 'professor')
            aluno = _criar_usuario('aluno_ex_2')
            _vincular(aluno, professor)

            ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Agachamento Livre', musculo_nome='Pernas'
            )
            copia = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id, nome='Agachamento Livre').first()

            ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=copia.id, user_id=aluno.id, nome='Agachamento (ajustado por mim)'
            )

            original = ExercicioCustomizado.query.filter_by(usuario_id=professor.id, nome='Agachamento Livre').first()
            assert original is not None  # o do professor não foi alterado
            assert original.nome == 'Agachamento Livre'

    def test_aluno_criando_exercicio_proprio_nao_propaga(self, app):
        """Só propaga quando quem cadastra é professor -- um aluno
        criando um exercício próprio não deve gerar cópias em lugar
        nenhum (nem ele tem "alunos" pra propagar)."""
        with app.app_context():
            professor = _criar_usuario('prof_ex_3', 'professor')
            aluno = _criar_usuario('aluno_ex_3')
            _vincular(aluno, professor)

            ExercicioService.criar_exercicio_customizado(
                user_id=aluno.id, nome='Rosca Direta', musculo_nome='Bíceps'
            )

            # Não deve ter criado nada extra pro professor
            no_professor = ExercicioCustomizado.query.filter_by(usuario_id=professor.id, nome='Rosca Direta').first()
            assert no_professor is None

    def test_nao_propaga_para_aluno_com_vinculo_inativo(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_4', 'professor')
            aluno = _criar_usuario('aluno_ex_4')
            _vincular(aluno, professor, ativo=False)

            ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Leg Press', musculo_nome='Pernas'
            )

            copia = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id, nome='Leg Press').first()
            assert copia is None

    def test_nao_duplica_se_aluno_ja_tem_exercicio_com_mesmo_nome(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_5', 'professor')
            aluno = _criar_usuario('aluno_ex_5')
            _vincular(aluno, professor)

            # Aluno já tinha criado um exercício próprio com esse nome
            # antes do professor cadastrar o dele.
            ExercicioService.criar_exercicio_customizado(
                user_id=aluno.id, nome='Puxada Frontal', musculo_nome='Costas'
            )

            ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Puxada Frontal', musculo_nome='Costas'
            )

            total_do_aluno = ExercicioCustomizado.query.filter_by(
                usuario_id=aluno.id, nome='Puxada Frontal'
            ).count()
            assert total_do_aluno == 1


class TestPropagacaoDeEdicaoProfessorParaAlunos:
    def test_editar_exercicio_do_professor_atualiza_copias_dos_alunos(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_6', 'professor')
            aluno1 = _criar_usuario('aluno_ex_6a')
            aluno2 = _criar_usuario('aluno_ex_6b')
            _vincular(aluno1, professor)
            _vincular(aluno2, professor)

            original = ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Supino Reto', musculo_nome='Peito',
                descricao='Barra livre'
            )

            ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=original.id, user_id=professor.id,
                nome='Supino Reto (pegada média)', descricao='Barra livre, pegada na largura dos ombros'
            )

            copia1 = ExercicioCustomizado.query.filter_by(usuario_id=aluno1.id).filter(
                ExercicioCustomizado.copiado_de_exercicio_id == original.id
            ).first()
            copia2 = ExercicioCustomizado.query.filter_by(usuario_id=aluno2.id).filter(
                ExercicioCustomizado.copiado_de_exercicio_id == original.id
            ).first()

            assert copia1.nome == 'Supino Reto (pegada média)'
            assert copia1.descricao == 'Barra livre, pegada na largura dos ombros'
            assert copia2.nome == 'Supino Reto (pegada média)'
            assert copia2.descricao == 'Barra livre, pegada na largura dos ombros'

    def test_editar_musculo_do_professor_atualiza_copias(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_7', 'professor')
            aluno = _criar_usuario('aluno_ex_7')
            _vincular(aluno, professor)

            from services.musculo_service import MusculoService
            musculo_novo = MusculoService.get_or_create('Ombro')

            original = ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Elevação Lateral', musculo_nome='Ombro'
            )
            copia = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id).first()
            musculo_anterior_id = copia.musculo_id

            from services.musculo_service import MusculoService as MS
            outro_musculo = MS.get_or_create('Trapézio')

            ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=original.id, user_id=professor.id,
                musculo_id=outro_musculo.id
            )

            db.session.refresh(copia)
            assert copia.musculo_id == outro_musculo.id
            assert copia.musculo_id != musculo_anterior_id

    def test_editar_copia_do_aluno_nao_afeta_original_nem_outras_copias(self, app):
        """A propagação é só professor -> aluno. O aluno editar a
        própria cópia continua independente (não mexe no original do
        professor nem nas cópias de outros alunos)."""
        with app.app_context():
            professor = _criar_usuario('prof_ex_8', 'professor')
            aluno1 = _criar_usuario('aluno_ex_8a')
            aluno2 = _criar_usuario('aluno_ex_8b')
            _vincular(aluno1, professor)
            _vincular(aluno2, professor)

            original = ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Rosca Direta', musculo_nome='Bíceps'
            )
            copia1 = ExercicioCustomizado.query.filter_by(usuario_id=aluno1.id).first()
            copia2 = ExercicioCustomizado.query.filter_by(usuario_id=aluno2.id).first()

            ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=copia1.id, user_id=aluno1.id,
                nome='Rosca Direta (ajustada por mim)'
            )

            db.session.refresh(original)
            db.session.refresh(copia2)
            assert original.nome == 'Rosca Direta'
            assert copia2.nome == 'Rosca Direta'

    def test_nao_propaga_edicao_para_aluno_com_vinculo_desfeito(self, app):
        with app.app_context():
            professor = _criar_usuario('prof_ex_9', 'professor')
            aluno = _criar_usuario('aluno_ex_9')
            vinculo = _vincular(aluno, professor)

            original = ExercicioService.criar_exercicio_customizado(
                user_id=professor.id, nome='Cadeira Extensora', musculo_nome='Pernas'
            )
            copia = ExercicioCustomizado.query.filter_by(usuario_id=aluno.id).first()

            vinculo.ativo = False
            db.session.commit()

            ExercicioService.update_exercicio_customizado(
                exercicio_custom_id=original.id, user_id=professor.id,
                nome='Cadeira Extensora (unilateral)'
            )

            db.session.refresh(copia)
            assert copia.nome == 'Cadeira Extensora'