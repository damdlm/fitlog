"""Teste de integração: /registrar-treino deve mostrar o músculo correto
(ex: 'Peito') para um exercício vindo do catálogo (exercicios_sistema),
em vez de 'N/A'. Reproduz de ponta a ponta (requisição HTTP real) o bug
relatado, usando o mesmo caminho que o navegador percorre."""
from datetime import date

from models import db, User, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioSistema


def test_registrar_treino_mostra_musculo_do_catalogo(client):
    with client.application.app_context():
        user = User(username='aluno_reg', email='aluno_reg@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.flush()

        ex_sistema = ExercicioSistema(id_original='0099', nome='Supino Reto', grupo_muscular='Peito')
        db.session.add(ex_sistema)

        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                               data_inicio=date.today(), user_id=user.id)
        db.session.add(versao)
        db.session.flush()

        treino_versao = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A')
        db.session.add(treino_versao)
        db.session.flush()

        db.session.add(VersaoExercicio(treino_versao_id=treino_versao.id, exercicio_base_id=ex_sistema.id, ordem=1))
        db.session.commit()

        user_id = user.id
        treino_versao_id = treino_versao.id

    client.post('/auth/login', data={'username': 'aluno_reg', 'password': '123456'})

    hoje = date.today().strftime('%Y-%m-%d')
    resp = client.get(f'/registrar/registrar-treino?data={hoje}&treino={treino_versao_id}')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'Supino Reto' in html
    assert 'Peito' in html, "Grupo muscular 'Peito' não apareceu na página renderizada"
