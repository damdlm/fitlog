"""Testes de integração: editar/excluir exercício não pode mexer em
exercícios do catálogo global (ExercicioSistema) -- só em exercícios
personalizados do próprio usuário (ExercicioUsuario/ExercicioCustomizado).

Antes da correção, tentar editar ou excluir um exercício do catálogo por
essas rotas acabava batendo na tabela errada (exercicios_usuario) com um
ID que na verdade pertencia a exercicios_sistema -- na pior hipótese,
se por coincidência o usuário tivesse um exercício personalizado com o
mesmo número de ID, a exclusão apagava o exercício errado.
"""
from models import db, User, Musculo, ExercicioUsuario, ExercicioSistema


def _criar_usuario_logado(client, email='aluno_ex@teste.com'):
    with client.application.app_context():
        user = User(username=email.split('@')[0], email=email)
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    client.post('/auth/login', data={'username': email.split('@')[0], 'password': '123456'})
    return user_id


def test_nao_permite_editar_exercicio_do_catalogo(client):
    user_id = _criar_usuario_logado(client)
    with client.application.app_context():
        ex_sistema = ExercicioSistema(id_original='0200', nome='Supino Reto', grupo_muscular='Peito')
        db.session.add(ex_sistema)
        db.session.commit()
        ex_id = ex_sistema.id

    resp = client.get(f'/aluno/exercicio/{ex_id}', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'catálogo geral' in html

    # O exercício do catálogo continua intacto
    with client.application.app_context():
        ex_sistema = ExercicioSistema.query.get(ex_id)
        assert ex_sistema is not None
        assert ex_sistema.nome == 'Supino Reto'


def test_nao_permite_excluir_exercicio_do_catalogo(client):
    user_id = _criar_usuario_logado(client)
    with client.application.app_context():
        ex_sistema = ExercicioSistema(id_original='0201', nome='Levantamento Terra', grupo_muscular='Costas')
        db.session.add(ex_sistema)
        db.session.commit()
        ex_id = ex_sistema.id

    resp = client.get(f'/aluno/exercicio/{ex_id}/excluir?confirmar=true', follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        assert ExercicioSistema.query.get(ex_id) is not None


def test_nao_apaga_exercicio_personalizado_com_id_coincidente_do_catalogo(client):
    """Cenário do bug real: um exercício personalizado do usuário tem,
    por coincidência, o mesmo ID numérico de um exercício do catálogo.
    Tentar excluir o exercício do catálogo NÃO pode apagar o personalizado."""
    user_id = _criar_usuario_logado(client)
    with client.application.app_context():
        musculo = Musculo(nome='costas', nome_exibicao='Costas')
        db.session.add(musculo)
        db.session.flush()

        ex_custom = ExercicioUsuario(usuario_id=user_id, nome='Remada Curvada (meu)', musculo_id=musculo.id)
        db.session.add(ex_custom)
        db.session.flush()
        custom_id = ex_custom.id

        # Cria exercícios de sistema "descartáveis" até um deles coincidir
        # em ID com o exercício personalizado acima.
        ex_sistema = None
        for i in range(custom_id + 3):
            ex = ExercicioSistema(id_original=f'sys{i}', nome=f'Sistema {i}', grupo_muscular='Pernas')
            db.session.add(ex)
            db.session.flush()
            if ex.id == custom_id:
                ex_sistema = ex
        db.session.commit()
        assert ex_sistema is not None, "não foi possível reproduzir a coincidência de ID no teste"
        sistema_id = ex_sistema.id

    resp = client.get(f'/aluno/exercicio/{sistema_id}/excluir?confirmar=true', follow_redirects=True)
    assert resp.status_code == 200

    # O exercício PERSONALIZADO do usuário, com o mesmo número de ID,
    # tem que continuar existindo.
    with client.application.app_context():
        assert ExercicioUsuario.query.get(custom_id) is not None


def test_ainda_permite_editar_exercicio_personalizado(client):
    user_id = _criar_usuario_logado(client)
    with client.application.app_context():
        musculo = Musculo(nome='peito', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.flush()
        ex_custom = ExercicioUsuario(usuario_id=user_id, nome='Supino (meu)', musculo_id=musculo.id)
        db.session.add(ex_custom)
        db.session.commit()
        custom_id = ex_custom.id

    resp = client.post(f'/aluno/exercicio/{custom_id}', data={
        'nome': 'Supino (editado)',
        'musculo': 'Peito',
        'descricao': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        ex_custom = ExercicioUsuario.query.get(custom_id)
        assert ex_custom.nome == 'Supino (editado)'