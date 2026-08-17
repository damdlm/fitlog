"""
Testes para a rota professor.listar_alunos ("Meus Alunos").

Cobre a mudança que restringiu a listagem a alunos vinculados e ativos,
removendo o filtro de status e os quadros de resumo (Vinculados/Ativos/
Inativos) da tela.
"""
import pytest
from models import db, User, AlunoProfessor


def _criar_usuario(username, tipo_usuario, ativo=True, is_admin=False):
    user = User(
        username=username,
        email=f'{username}@teste.com',
        tipo_usuario=tipo_usuario,
        is_admin=is_admin,
        nome_completo=username.title(),
        ativo=ativo,
    )
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={
        'username': username,
        'password': '123456'
    })


@pytest.fixture
def cenario_alunos(app):
    """
    Professor com:
    - aluno_ativo_vinculado: vínculo ativo + aluno ativo -> deve aparecer
    - aluno_inativo_vinculado: vínculo ativo + aluno inativo -> não deve aparecer
    - aluno_vinculo_inativo: aluno ativo mas vínculo (AlunoProfessor) inativo -> não deve aparecer
    - aluno_de_outro_professor: vinculado a outro professor -> não deve aparecer
    """
    with app.app_context():
        professor = _criar_usuario('prof1', 'professor')
        outro_professor = _criar_usuario('prof2', 'professor')

        aluno_ativo = _criar_usuario('joaosilva', 'aluno', ativo=True)
        aluno_inativo = _criar_usuario('mariainativa', 'aluno', ativo=False)
        aluno_vinculo_inativo = _criar_usuario('carlosdesvinculado', 'aluno', ativo=True)
        aluno_de_outro = _criar_usuario('anadeoutro', 'aluno', ativo=True)

        db.session.add(AlunoProfessor(aluno_id=aluno_ativo.id, professor_id=professor.id, ativo=True))
        db.session.add(AlunoProfessor(aluno_id=aluno_inativo.id, professor_id=professor.id, ativo=True))
        db.session.add(AlunoProfessor(aluno_id=aluno_vinculo_inativo.id, professor_id=professor.id, ativo=False))
        db.session.add(AlunoProfessor(aluno_id=aluno_de_outro.id, professor_id=outro_professor.id, ativo=True))
        db.session.commit()

        return {
            'professor_id': professor.id,
            'aluno_ativo_id': aluno_ativo.id,
            'aluno_inativo_id': aluno_inativo.id,
            'aluno_vinculo_inativo_id': aluno_vinculo_inativo.id,
            'aluno_de_outro_id': aluno_de_outro.id,
        }


class TestListarAlunosFiltraVinculadosEAtivos:
    def test_mostra_apenas_aluno_vinculado_e_ativo(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'joaosilva' in html

    def test_nao_mostra_aluno_com_vinculo_ativo_mas_aluno_inativo(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'mariainativa' not in html

    def test_nao_mostra_aluno_com_vinculo_inativo(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'carlosdesvinculado' not in html

    def test_nao_mostra_aluno_de_outro_professor(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'anadeoutro' not in html

    def test_parametro_status_legado_e_ignorado_sem_quebrar_a_rota(self, client, cenario_alunos):
        """A rota não deve mais depender de ?status=... -- se alguém (link
        salvo, bookmark) ainda mandar o parâmetro, a página deve carregar
        normalmente e continuar mostrando só vinculados+ativos."""
        _login(client, 'prof1')
        resp = client.get('/professor/alunos?status=todos')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'joaosilva' in html
        assert 'mariainativa' not in html


class TestListarAlunosBusca:
    def test_busca_por_nome_encontra_aluno(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos?busca=joaosilva')
        html = resp.data.decode('utf-8')
        assert 'joaosilva' in html

    def test_busca_sem_correspondencia_nao_encontra_aluno(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos?busca=naoexiste')
        html = resp.data.decode('utf-8')
        assert 'joaosilva' not in html


class TestListarAlunosLayout:
    def test_nao_mostra_quadros_de_resumo(self, client, cenario_alunos):
        """Os quadros Vinculados/Ativos/Inativos foram removidos da tela."""
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'Vinculados</h6>' not in html
        assert 'Inativos</h6>' not in html

    def test_nao_mostra_select_de_status(self, client, cenario_alunos):
        """O filtro dropdown de status foi removido -- só busca + botão Filtrar."""
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'name="status"' not in html

    def test_nao_mostra_badge_de_status_ativo(self, client, cenario_alunos):
        """O badge 'Ativo'/'Inativo' por aluno foi removido da listagem."""
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'bg-success">Ativo<' not in html

    def test_mostra_campo_busca_e_botao_filtrar(self, client, cenario_alunos):
        _login(client, 'prof1')
        resp = client.get('/professor/alunos')
        html = resp.data.decode('utf-8')
        assert 'name="busca"' in html
        assert 'Filtrar' in html