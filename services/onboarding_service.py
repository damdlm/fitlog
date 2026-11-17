"""Cartão "Comece por aqui" (lote 4, E1) para conta nova de aluno.

Três passos: 1) montar a ficha, 2) registrar o primeiro treino, 3) ver o
progresso. Os dois primeiros saem do banco; o terceiro é marcado no
navegador quando a pessoa abre a tela Progresso (localStorage, ver
templates/_comece_por_aqui.html) -- não há o que guardar no servidor só
por ter aberto uma página. O cartão some quando os três estão feitos ou
quando a pessoa toca em "Ocultar".
"""
from datetime import datetime, timedelta, timezone

from models import RegistroTreino, TreinoVersao, VersaoExercicio, VersaoGlobal, db

# Conta com mais tempo que isso, e que já tem ficha e treino registrado,
# não é "conta nova": não vê o cartão só por nunca ter aberto o Progresso.
DIAS_CONTA_NOVA = 30


def passos_comece_por_aqui(user):
    """Dict com o estado dos passos, ou None quando o cartão não se aplica
    (não é aluno, ou conta antiga que já fez os passos do servidor)."""
    if not user or not user.is_authenticated or not user.is_aluno():
        return None

    tem_ficha = db.session.query(VersaoExercicio.id).join(
        TreinoVersao, VersaoExercicio.treino_versao_id == TreinoVersao.id
    ).join(
        VersaoGlobal, TreinoVersao.versao_id == VersaoGlobal.id
    ).filter(
        VersaoGlobal.user_id == user.id,
        VersaoGlobal.data_fim.is_(None),
    ).first() is not None

    registrou = db.session.query(RegistroTreino.id).filter(
        RegistroTreino.user_id == user.id
    ).first() is not None

    criado = user.created_at
    if criado is not None and criado.tzinfo is None:
        criado = criado.replace(tzinfo=timezone.utc)
    conta_nova = criado is None or criado >= datetime.now(timezone.utc) - timedelta(days=DIAS_CONTA_NOVA)

    if tem_ficha and registrou and not conta_nova:
        return None

    tem_professor = bool(user.get_professor()) if hasattr(user, 'get_professor') else False
    return {
        'ficha': tem_ficha,
        'registro': registrou,
        'tem_professor': tem_professor,
        'feitos_servidor': int(tem_ficha) + int(registrou),
    }
