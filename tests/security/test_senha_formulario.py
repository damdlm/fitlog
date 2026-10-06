"""Formulários com senha: o que foi digitado NÃO some quando há erro, todos os
problemas da senha aparecem de uma vez, e os textos do formulário batem com as
regras reais do servidor."""
from datetime import datetime, timezone

from models import db, User, AlunoProfessor
from utils.validators import erros_senha, validar_senha

DADOS = {
    'username': 'maria_teste', 'email': 'maria.teste@exemplo.com', 'nome_completo': 'Maria da Silva',
    'telefone': '(47) 99999-1234', 'genero': 'F', 'tipo_usuario': 'professor', 'aceite_termos': 'on',
}


def _cadastrar(client, senha, confirmacao=None, **extra):
    dados = dict(DADOS, password=senha, confirm_password=senha if confirmacao is None else confirmacao)
    dados.update(extra)
    return client.post('/auth/register', data=dados)


class TestErrosDaSenha:
    def test_lista_todos_os_problemas_de_uma_vez(self):
        erros = erros_senha('abc')
        assert 'Senha deve ter pelo menos 8 caracteres' in erros
        assert 'Senha deve conter pelo menos um número' in erros
        assert len(erros) == 2

    def test_senha_valida_nao_tem_erros(self):
        assert erros_senha('Treino#Forte9', username='maria', email='m@x.com') == []

    def test_validar_senha_continua_devolvendo_o_primeiro_erro(self):
        assert validar_senha('abc') == (False, 'Senha deve ter pelo menos 8 caracteres')


class TestCadastroMantemOsCampos:
    def test_erro_de_senha_volta_com_campos_preenchidos_e_sem_a_senha(self, client):
        resp = _cadastrar(client, 'abc')
        assert resp.status_code == 302
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'value="maria_teste"' in html
        assert 'value="maria.teste@exemplo.com"' in html
        assert 'value="Maria da Silva"' in html
        assert 'value="(47) 99999-1234"' in html
        assert 'abc' not in html.split('name="password"')[1].split('>')[0]
        # todos os problemas, de uma vez, e as escolhas do formulário preservadas
        assert 'pelo menos 8 caracteres' in html and 'pelo menos um número' in html
        assert 'id="tipo_professor" value="professor" checked' in html
        assert 'value="F" selected' in html
        assert 'name="aceite_termos" required checked' in html

    def test_senhas_diferentes_somam_ao_erro_da_senha(self, client):
        _cadastrar(client, 'abc', confirmacao='outra')
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'As senhas não coincidem' in html and 'pelo menos 8 caracteres' in html

    def test_dados_voltam_so_uma_vez(self, client):
        _cadastrar(client, 'abc')
        client.get('/auth/register')
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'maria_teste' not in html

    def test_outros_erros_tambem_mantem_os_campos(self, client, app):
        with app.app_context():
            u = User(username='ocupado', email='ocupado@exemplo.com', tipo_usuario='aluno', ativo=True)
            u.set_password('Treino#Forte9')
            db.session.add(u)
            db.session.commit()
        _cadastrar(client, 'Treino#Forte9', username='ocupado')
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'Nome de usuário já existe' in html
        assert 'value="maria.teste@exemplo.com"' in html

    def test_formulario_mostra_as_regras_reais(self, client):
        html = client.get('/auth/register').get_data(as_text=True)
        assert 'Pelo menos 8 caracteres' in html
        assert 'Pelo menos uma letra' in html and 'Pelo menos um número' in html
        assert 'minlength="8"' in html
        assert '6 caracteres' not in html and 'minlength="6"' not in html

    def test_cadastro_valido_continua_funcionando(self, client, app):
        assert _cadastrar(client, 'Treino#Forte9').status_code == 302
        with app.app_context():
            assert User.query.filter_by(username='maria_teste').first() is not None


def _professor_e_aluno(app):
    with app.app_context():
        prof = User(username='prof_sf', email='prof_sf@teste.com', tipo_usuario='professor', ativo=True)
        prof.set_password('123456')
        alu = User(username='alu_sf', email='alu_sf@teste.com', tipo_usuario='aluno', ativo=True,
                   nome_completo='Aluno Sf')
        alu.set_password('123456')
        adm = User(username='adm_sf', email='adm_sf@teste.com', tipo_usuario='professor', ativo=True,
                   is_admin=True)
        adm.set_password('123456')
        db.session.add_all([prof, alu, adm])
        db.session.commit()
        db.session.add(AlunoProfessor(aluno_id=alu.id, professor_id=prof.id, ativo=True,
                                      data_associacao=datetime.now(timezone.utc)))
        db.session.commit()
        return alu.id


class TestFormulariosDoProfessor:
    def test_novo_aluno_mantem_campos_e_mostra_todos_os_erros(self, client, app):
        _professor_e_aluno(app)
        client.post('/auth/login', data={'username': 'prof_sf', 'password': '123456'})
        client.post('/professor/aluno/novo', data={
            'username': 'joao_novo', 'email': 'joao@exemplo.com', 'password': 'abc',
            'nome_completo': 'João Novo', 'telefone': '(47) 98888-0000'})
        html = client.get('/professor/aluno/novo').get_data(as_text=True)
        assert 'value="joao_novo"' in html and 'value="joao@exemplo.com"' in html
        assert 'value="João Novo"' in html and 'value="(47) 98888-0000"' in html
        assert 'pelo menos 8 caracteres' in html and 'pelo menos um número' in html
        assert '6 caracteres' not in html

    def test_editar_aluno_recusa_senha_fraca_mas_salva_o_resto(self, client, app):
        # Editar aluno é ação restrita ao admin (ver editar_aluno).
        aluno_id = _professor_e_aluno(app)
        client.post('/auth/login', data={'username': 'adm_sf', 'password': '123456'})
        resp = client.post(f'/professor/aluno/editar/{aluno_id}', data={
            'nome_completo': 'Nome Novo', 'email': 'alu_sf@teste.com', 'telefone': '1',
            'nova_senha': '1234567'}, follow_redirects=True)
        assert 'a senha NÃO foi alterada' in resp.get_data(as_text=True)
        with app.app_context():
            aluno = db.session.get(User, aluno_id)
            assert aluno.nome_completo == 'Nome Novo'
            assert aluno.check_password('123456')

    def test_editar_aluno_aceita_senha_forte(self, client, app):
        aluno_id = _professor_e_aluno(app)
        client.post('/auth/login', data={'username': 'adm_sf', 'password': '123456'})
        client.post(f'/professor/aluno/editar/{aluno_id}', data={
            'nome_completo': 'Aluno Sf', 'email': 'alu_sf@teste.com', 'telefone': '',
            'nova_senha': 'Treino#Forte9'})
        with app.app_context():
            assert db.session.get(User, aluno_id).check_password('Treino#Forte9')
