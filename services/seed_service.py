"""
Serviço para popular dados iniciais para novos usuários
Usa ExercicioCustomizado e Musculo (modelos unificados)
"""
from .base_service import BaseService
from models import db, Treino, ExercicioCustomizado, Musculo
from data.default_workouts import WORKOUTS_3X, WORKOUTS_4X, WORKOUTS_5X, MUSCLE_MAPPING
import logging

logger = logging.getLogger(__name__)

class SeedService:
    """Serviço para criar dados iniciais para novos usuários"""

    @staticmethod
    def get_or_create_musculo(nome_exibicao):
        """Retorna um músculo existente ou cria um novo"""
        musculo = Musculo.query.filter_by(nome_exibicao=nome_exibicao).first()
        if not musculo:
            musculo = Musculo(
                nome=nome_exibicao.lower(),
                nome_exibicao=nome_exibicao
            )
            db.session.add(musculo)
            db.session.flush()
            logger.info(f"Músculo criado: {nome_exibicao}")
        return musculo

    @staticmethod
    def create_minimal_workouts(user_id):
        """
        Cria apenas os treinos básicos (A, B, C) sem exercícios
        para que o usuário possa configurar depois
        """
        try:
            logger.info(f"Criando treinos mínimos para usuário {user_id}")

            treinos_base = {
                "A": {"nome": "Treino A", "descricao": "Peito/Ombro/Tríceps"},
                "B": {"nome": "Treino B", "descricao": "Costas/Bíceps"},
                "C": {"nome": "Treino C", "descricao": "Pernas"}
            }

            treinos_criados = {}
            for codigo, dados in treinos_base.items():
                treino = Treino.query.filter_by(user_id=user_id, codigo=codigo).first()
                if treino:
                    logger.warning(f"Treino {codigo} já existe para usuário {user_id}")
                else:
                    treino = Treino(
                        codigo=codigo,
                        nome=dados["nome"],
                        descricao=dados["descricao"],
                        user_id=user_id
                    )
                    db.session.add(treino)
                    db.session.flush()
                    logger.info(f"Treino {codigo} criado: {dados['nome']}")
                treinos_criados[codigo] = treino

            db.session.commit()
            logger.info(f"{len(treinos_criados)} treinos mínimos criados para usuário {user_id}")
            return treinos_criados

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar treinos mínimos: {str(e)}", exc_info=True)
            return {}

    @staticmethod
    def create_default_workouts(user_id, frequency="3x"):
        """
        Cria treinos completos com exercícios (ExercicioCustomizado) para um usuário
        """
        try:
            logger.info(f"Criando treinos completos para usuário {user_id} - Frequência {frequency}")

            if frequency == "4x":
                workouts = WORKOUTS_4X
            elif frequency == "5x":
                workouts = WORKOUTS_5X
            else:
                workouts = WORKOUTS_3X

            treinos_criados = {}

            for codigo, workout_data in workouts.items():
                treino = Treino.query.filter_by(user_id=user_id, codigo=codigo).first()
                if treino:
                    logger.warning(f"Treino {codigo} já existe para usuário {user_id}")
                    treinos_criados[codigo] = treino
                    continue

                treino = Treino(
                    codigo=codigo,
                    nome=workout_data["nome"],
                    descricao=workout_data["descricao"],
                    user_id=user_id
                )
                db.session.add(treino)
                db.session.flush()
                logger.info(f"Treino {codigo} criado: {workout_data['nome']}")

                for ex_data in workout_data["exercicios"]:
                    musculo_nome = MUSCLE_MAPPING.get(ex_data["musculo"], ex_data["musculo"])
                    musculo = SeedService.get_or_create_musculo(musculo_nome)

                    # Verificar se exercício customizado já existe para o usuário
                    exercicio = ExercicioCustomizado.query.filter_by(
                        usuario_id=user_id,
                        nome=ex_data["nome"]
                    ).first()

                    if not exercicio:
                        exercicio = ExercicioCustomizado(
                            usuario_id=user_id,
                            nome=ex_data["nome"],
                            descricao=f"Exercício para {workout_data['nome']}",
                            musculo_id=musculo.id
                        )
                        db.session.add(exercicio)
                        db.session.flush()
                        logger.debug(f"Exercício criado: {ex_data['nome']}")

                treinos_criados[codigo] = treino

            db.session.commit()
            logger.info(f"{len(treinos_criados)} treinos completos criados para usuário {user_id}")
            return treinos_criados

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar treinos completos: {str(e)}", exc_info=True)
            return {}

    @staticmethod
    def create_all_frequencies(user_id):
        """Cria todas as frequências de treino para um usuário (útil para testes)"""
        return {
            "3x": SeedService.create_default_workouts(user_id, "3x"),
            "4x": SeedService.create_default_workouts(user_id, "4x"),
            "5x": SeedService.create_default_workouts(user_id, "5x"),
        }