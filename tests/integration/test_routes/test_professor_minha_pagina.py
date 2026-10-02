"""Tela "Minha Página" do professor: especialidades ampliadas (com
descrição para o tooltip), botões no padrão do app e salvamento."""
import pytest
from models import db, User
from services.professor_perfil_service import (
    ESPECIALIDADES_GRUPOS, ESPECIALIDADES_VALIDAS, ProfessorPerfilService,
)


@pytest.fixture
def professor(app):
    with app.app_context():
        user = User(
            username='profminhapagina',
            email='profminhapagina@teste.com',
            tipo_usuario='professor',
            nome_completo='Felipe Luis',
        )
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        ProfessorPerfilService.garantir_slug(user)
        db.session.commit()
        yield user.id


def _login(client):
    return client.post('/auth/login', data={'username': 'profminhapagina', 'password': '123456'})


def test_chaves_originais_continuam_validas():
    # Já estão gravadas no banco: não podem sumir nem mudar.
    for chave in ('emagrecimento', 'hipertrofia', 'reabilitacao', 'terceira_idade'):
        assert chave in ESPECIALIDADES_VALIDAS


def test_vocabulario_ampliado_com_descricao_curta():
    assert len(ESPECIALIDADES_VALIDAS) >= 15
    chaves = [c for _, itens in ESPECIALIDADES_GRUPOS for c, _, _ in itens]
    assert len(chaves) == len(set(chaves))
    for _, itens in ESPECIALIDADES_GRUPOS:
        for chave, rotulo, descricao in itens:
            assert rotulo.strip() and descricao.strip(), chave
            assert len(descricao) <= 80, chave


def test_tela_mostra_todas_com_descricao_para_tooltip(app, client, professor):
    _login(client)
    html = client.get('/professor/pagina/editar').data.decode()
    assert '<title>' in html and 'Minha Página' in html
    for _, itens in ESPECIALIDADES_GRUPOS:
        for chave, rotulo, descricao in itens:
            assert f'value="{chave}"' in html
            assert f'data-descricao="{descricao}"' in html


def test_botoes_usam_classes_padrao_do_app(app, client, professor):
    _login(client)
    html = client.get('/professor/pagina/editar').data.decode()
    assert 'btn btn-primary' in html
    # classes antigas, fora do padrão do restante da aplicação
    for antigo in ('epp-submit', 'epp-btn-escolher', 'epp-btn-ver'):
        assert antigo not in html


def test_salvar_nova_especialidade(app, client, professor):
    _login(client)
    resp = client.post(
        '/professor/pagina/editar',
        data={'especialidades': ['corrida', 'gestantes', 'pcd']},
        follow_redirects=True,
    )
    assert 'Página atualizada com sucesso!'.encode() in resp.data
    user = db.session.get(User, professor)
    assert set(user.professor_especialidades) == {'corrida', 'gestantes', 'pcd'}


def test_especialidade_desconhecida_e_ignorada(app, client, professor):
    _login(client)
    client.post(
        '/professor/pagina/editar',
        data={'especialidades': ['corrida', 'inventada']},
        follow_redirects=True,
    )
    user = db.session.get(User, professor)
    assert user.professor_especialidades == ['corrida']


def test_destaque_usa_descricao_da_nova_especialidade(app, professor):
    user = db.session.get(User, professor)
    user.professor_especialidades = ['corrida', 'gestantes']
    db.session.commit()
    destaque = ProfessorPerfilService.servicos_destaque(user)
    assert [d['chave'] for d in destaque[:2]] == ['corrida', 'gestantes']
    assert all(d['descricao'] for d in destaque)
