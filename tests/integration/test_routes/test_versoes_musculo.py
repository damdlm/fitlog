"""Teste de integração: /aluno/versoes deve mostrar o músculo correto
para um exercício do catálogo dentro dos detalhes de uma versão.
Esse template usa o padrão de fallback (ve.exercicio cru, sem
enriquecimento prévio pelo serviço), diferente das outras telas."""
from datetime import date

from models import db, User, Treino, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioSistema


def test_versoes_aluno_mostra_musculo_do_catalogo(client):
    with client.application.app_context():
        user = User(username='aluno_ver', email='aluno_ver@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.flush()

        ex_sistema = ExercicioSistema(id_original='0100', nome='Agachamento Livre', grupo_muscular='Quadríceps')
        db.session.add(ex_sistema)

        treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='Treino A')
        db.session.add(treino)

        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                               data_inicio=date.today(), user_id=user.id)
        db.session.add(versao)
        db.session.flush()

        treino_versao = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino='Treino A')
        db.session.add(treino_versao)
        db.session.flush()

        db.session.add(VersaoExercicio(treino_versao_id=treino_versao.id, exercicio_base_id=ex_sistema.id, ordem=1))
        db.session.commit()

    client.post('/auth/login', data={'username': 'aluno_ver', 'password': '123456'})

    resp = client.get('/aluno/versoes')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'Agachamento Livre' in html
    assert 'Quadríceps' in html, "Grupo muscular 'Quadríceps' não apareceu na página renderizada"
