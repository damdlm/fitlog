"""Serviço de avaliação (1-5 estrelas) do aluno pro próprio professor.
Separado de ProfessorPerfilService porque quem escreve aqui é sempre o
aluno, nunca o professor (autorização diferente)."""
import logging

from sqlalchemy import func

from models import db, AvaliacaoProfessor, User
from .base_service import BaseService

logger = logging.getLogger(__name__)


class AvaliacaoProfessorService(BaseService):

    @staticmethod
    def avaliar(aluno: User, professor_id: int, nota) -> tuple[bool, str]:
        """Cria ou atualiza a nota do aluno pro professor. Só permite
        avaliar o PRÓPRIO professor vinculado (nunca um professor_id
        arbitrário vindo do request) -- mesma lógica de autorização de
        User.pode_acessar_dados_de."""
        if not aluno.is_aluno():
            return False, 'Apenas alunos podem avaliar professores.'

        professor_vinculado = aluno.get_professor()
        if not professor_vinculado or professor_vinculado.id != int(professor_id):
            return False, 'Você só pode avaliar o seu próprio professor.'

        try:
            nota_int = int(nota)
        except (TypeError, ValueError):
            return False, 'Nota inválida.'
        if nota_int < 1 or nota_int > 5:
            return False, 'A nota deve ser de 1 a 5.'

        try:
            avaliacao = AvaliacaoProfessor.query.filter_by(
                aluno_id=aluno.id, professor_id=professor_vinculado.id
            ).first()
            if avaliacao:
                avaliacao.nota = nota_int
            else:
                avaliacao = AvaliacaoProfessor(
                    aluno_id=aluno.id, professor_id=professor_vinculado.id, nota=nota_int
                )
                db.session.add(avaliacao)
            db.session.commit()
            return True, 'Avaliação registrada -- obrigado pelo feedback!'
        except Exception:
            db.session.rollback()
            logger.exception('Erro ao salvar avaliação de %s para professor %s', aluno.id, professor_id)
            return False, 'Erro ao salvar sua avaliação. Tente novamente.'

    @staticmethod
    def nota_do_aluno(aluno_id: int, professor_id: int):
        """Nota que ESTE aluno já deu (ou None), pra pré-marcar as
        estrelas no formulário."""
        avaliacao = AvaliacaoProfessor.query.filter_by(
            aluno_id=aluno_id, professor_id=professor_id
        ).first()
        return avaliacao.nota if avaliacao else None

    @staticmethod
    def resumo(professor_id: int) -> dict:
        """Média (arredondada em 1 casa) e total de avaliações do
        professor -- uma única query de agregação."""
        media, total = db.session.query(
            func.avg(AvaliacaoProfessor.nota), func.count(AvaliacaoProfessor.id)
        ).filter(AvaliacaoProfessor.professor_id == professor_id).first()

        return {
            'media': round(float(media), 1) if media is not None else 0.0,
            'total': total or 0,
        }
