"""Testes de segurança de IDOR (Insecure Direct Object Reference).

CORREÇÃO seção 20/21 (prompt de hardening): a validação de IDs de
ExercicioUsuario ao salvar um treino da versão checava só se o ID
existia (ExercicioUsuario.query.get), não se pertencia ao usuário --
um usuário podia vincular à própria versão um exercício customizado de
OUTRO usuário só adivinhando/enumerando o ID (violação de integridade
referencial semântica, seção 21, e de autorização, seção 20).

A rota testada é a tela viva "Cadastrar Treinos"
(aluno.cadastrar_treinos_salvar_treino) -- o fluxo antigo de versão com
divisão fixa (blueprint 'version') foi removido.
"""
from datetime import date

from models import (
    db, User, VersaoGlobal, TreinoVersao, ExercicioUsuario,
)


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def _cria_usuario_com_versao_e_treino(username):
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('SenhaForte123')
    db.session.add(user)
    db.session.flush()

    versao = VersaoGlobal(
        numero_versao=1, descricao='V1', divisao='ABC',
        data_inicio=date.today(), data_fim=None, user_id=user.id,
    )
    db.session.add(versao)
    db.session.flush()

    tv = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A')
    db.session.add(tv)
    db.session.commit()
    return user, versao, tv


def test_nao_consegue_vincular_exercicio_customizado_de_outro_usuario(client, db):
    """Usuário A tenta, na própria versão, referenciar o ID de um
    ExercicioUsuario que pertence ao usuário B -- isso não pode ser
    aceito (IDOR)."""
    vitima, _, _ = _cria_usuario_com_versao_e_treino('idor_vitima')
    exercicio_da_vitima = ExercicioUsuario(nome='Exercício privado da vítima', usuario_id=vitima.id)
    db.session.add(exercicio_da_vitima)
    db.session.commit()
    exercicio_id = exercicio_da_vitima.id

    atacante, versao_atacante, treino_atacante = _cria_usuario_com_versao_e_treino('idor_atacante')
    _login(client, atacante)

    resp = client.post(
        f'/aluno/cadastrar-treinos/{versao_atacante.id}/treino/{treino_atacante.id}',
        data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{exercicio_id}'],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    # O exercício da vítima NÃO deve ter sido vinculado ao treino do atacante
    from models import VersaoExercicio
    vinculado = VersaoExercicio.query.filter_by(exercicio_usuario_id=exercicio_id).first()
    assert vinculado is None


def test_consegue_vincular_o_proprio_exercicio_customizado(client, db):
    """Controle positivo: o próprio exercício customizado do usuário
    continua funcionando normalmente."""
    user, versao, treino = _cria_usuario_com_versao_e_treino('idor_dono')
    exercicio_proprio = ExercicioUsuario(nome='Meu exercício', usuario_id=user.id)
    db.session.add(exercicio_proprio)
    db.session.commit()
    exercicio_id = exercicio_proprio.id

    _login(client, user)
    resp = client.post(
        f'/aluno/cadastrar-treinos/{versao.id}/treino/{treino.id}',
        data={
            'nome_treino': 'Treino A',
            'descricao_treino': '',
            'exercicios[]': [f'u_{exercicio_id}'],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    from models import VersaoExercicio
    vinculado = VersaoExercicio.query.filter_by(exercicio_usuario_id=exercicio_id).first()
    assert vinculado is not None
