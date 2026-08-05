"""
Testes de segurança/IDOR — Fase 4.

Cobre os cenários pedidos nas Seções 17 e 18 da missão:
- usuário A não acessa treino/histórico/estatística de B;
- professor A acessa aluno vinculado, não acessa aluno alheio;
- aluno não acessa recurso administrativo (rota exclusiva do professor);
- usuário não autenticado é redirecionado para login;
- manipulação de IDs (treino_id, versao_id, exercicio_id) próprios,
  de terceiros e inexistentes não deve vazar dado nem quebrar.

Inclui também o teste de regressão para o IDOR real encontrado e
corrigido nesta fase: GET /api/versao-exercicios/<versao_id> não
validava que a versão pertencia ao usuário autenticado.
"""
from datetime import date, datetime, timezone

from models import (
    db, User, AlunoProfessor, Musculo, ExercicioUsuario, ExercicioSistema,
    Treino, VersaoGlobal, TreinoVersao, VersaoExercicio, RegistroTreino, HistoricoTreino,
)


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, is_admin=is_admin, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _criar_treino_completo(user, codigo='A'):
    """Cria treino + versão + exercício + registro + histórico para um usuário."""
    musculo = Musculo.query.filter_by(nome=f'm_{user.id}').first()
    if not musculo:
        musculo = Musculo(nome=f'm_{user.id}', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.commit()

    ex = ExercicioUsuario(usuario_id=user.id, nome=f'Exercicio privado de {user.username}', musculo_id=musculo.id)
    db.session.add(ex)
    db.session.commit()

    treino = Treino(user_id=user.id, codigo=codigo, nome=f'Treino {codigo}', descricao='desc')
    db.session.add(treino)
    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date.today(), user_id=user.id)
    db.session.add(versao)
    db.session.commit()

    tv = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino=treino.nome, descricao_treino='')
    db.session.add(tv)
    db.session.commit()
    db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=1))
    db.session.commit()

    registro = RegistroTreino(
        treino_id=treino.id, versao_id=versao.id, periodo='manha', semana=1,
        exercicio_usuario_id=ex.id, data_registro=datetime.now(timezone.utc), user_id=user.id,
    )
    db.session.add(registro)
    db.session.commit()
    db.session.add(HistoricoTreino(registro_id=registro.id, carga=100, repeticoes=10))
    db.session.commit()

    return {'treino': treino, 'versao': versao, 'exercicio': ex, 'registro': registro}


class TestAcessoEntreUsuariosComuns:
    """Teste 1, 2, 3: usuário A não acessa treino/histórico/estatística de B."""

    def test_usuario_nao_acessa_treino_de_outro(self, client, app):
        with app.app_context():
            a = _criar_usuario('user_a_treino')
            b = _criar_usuario('user_b_treino')
            dados_b = _criar_treino_completo(b)
            treino_b_id = dados_b['treino'].id

        _login(client, 'user_a_treino')
        # tentativa de excluir o treino de B via rota de auto-gerenciamento
        resp = client.post(f'/admin/excluir/treino/{treino_b_id}', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Treino, treino_b_id) is not None  # não foi excluído

    def test_usuario_nao_acessa_historico_de_outro_via_evento_calendario(self, client, app):
        with app.app_context():
            a = _criar_usuario('user_a_hist')
            b = _criar_usuario('user_b_hist')
            dados_b = _criar_treino_completo(b)
            registro_b_id = dados_b['registro'].id

        _login(client, 'user_a_hist')
        resp = client.get(f'/calendar/api/evento/{registro_b_id}')
        assert resp.status_code == 404

    def test_usuario_nao_acessa_estatistica_de_outro(self, client, app):
        with app.app_context():
            a = _criar_usuario('user_a_stats')
            b = _criar_usuario('user_b_stats')
            _criar_treino_completo(b)

        _login(client, 'user_a_stats')
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code == 200
        # estatísticas são sempre calculadas com base no usuário autenticado
        # (current_user via BaseService) -- A não deve ver volume de B
        assert b'Exercicio privado de user_b_stats' not in resp.data


class TestProfessorAluno:
    """Teste 4, 5: professor acessa vinculado, não acessa não-vinculado."""

    def test_professor_acessa_aluno_vinculado(self, client, app):
        with app.app_context():
            professor = _criar_usuario('prof_seg', 'professor')
            aluno = _criar_usuario('aluno_seg', 'aluno')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=True))
            db.session.commit()
            _criar_treino_completo(aluno)
            aluno_id = aluno.id

        _login(client, 'prof_seg')
        resp = client.get(f'/professor/aluno/{aluno_id}/treinos')
        assert resp.status_code == 200

    def test_professor_nao_acessa_aluno_nao_vinculado(self, client, app):
        with app.app_context():
            professor = _criar_usuario('prof_seg2', 'professor')
            aluno_alheio = _criar_usuario('aluno_alheio', 'aluno')
            _criar_treino_completo(aluno_alheio)
            aluno_id = aluno_alheio.id

        _login(client, 'prof_seg2')
        resp = client.get(f'/professor/aluno/{aluno_id}/treinos', follow_redirects=True)
        assert resp.status_code == 200
        assert b'permiss\xc3\xa3o' in resp.data.lower() or b'permissao' in resp.data.lower()

    def test_professor_nao_acessa_estatisticas_de_aluno_nao_vinculado(self, client, app):
        with app.app_context():
            professor = _criar_usuario('prof_seg3', 'professor')
            aluno_alheio = _criar_usuario('aluno_alheio3', 'aluno')
            _criar_treino_completo(aluno_alheio)
            aluno_id = aluno_alheio.id

        _login(client, 'prof_seg3')
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas', follow_redirects=True)
        assert resp.status_code == 200
        assert b'permiss\xc3\xa3o' in resp.data.lower() or b'permissao' in resp.data.lower()
        assert b'Exercicio privado de aluno_alheio3' not in resp.data


class TestAlunoNaoAcessaAdmin:
    """Teste 6: aluno tenta acessar recurso administrativo."""

    def test_aluno_nao_desativa_outro_usuario(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('aluno_comum_seg')
            outro = _criar_usuario('outro_usuario_seg')
            outro_id = outro.id

        _login(client, 'aluno_comum_seg')
        resp = client.post(f'/professor/aluno/desativar/{outro_id}', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(User, outro_id).ativo is True

    def test_aluno_nao_edita_outro_usuario(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('aluno_comum_seg2')
            outro = _criar_usuario('outro_usuario_seg2')
            outro_id = outro.id

        _login(client, 'aluno_comum_seg2')
        resp = client.post(
            f'/professor/aluno/editar/{outro_id}',
            data={'nome_completo': 'Hackeado', 'email': 'outro_usuario_seg2@teste.com', 'telefone': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(User, outro_id).nome_completo != 'Hackeado'


class TestUsuarioNaoAutenticado:
    """Teste 7: usuário não autenticado é redirecionado para login."""

    def test_rota_protegida_redireciona_para_login(self, client):
        resp = client.get('/estatisticas/estatisticas')
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert '/auth/login' in resp.headers['Location']

    def test_calendario_protegido_redireciona_para_login(self, client):
        resp = client.get('/calendar/calendario')
        assert resp.status_code in (302, 401)


class TestIDOR:
    """Seção 18: manipulação de IDs (próprio, de outro usuário, inexistente)."""

    def test_versao_exercicios_id_proprio_funciona(self, client, app):
        with app.app_context():
            user = _criar_usuario('idor_proprio')
            dados = _criar_treino_completo(user)
            versao_id = dados['versao'].id

        _login(client, 'idor_proprio')
        resp = client.get(f'/api/versao-exercicios/{versao_id}')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_versao_exercicios_id_de_outro_usuario_nao_vaza_dados(self, client, app):
        """Regressão do IDOR corrigido: VersaoService.get_exercicios não
        validava que a versão pertencia ao usuário autenticado."""
        with app.app_context():
            atacante = _criar_usuario('idor_atacante')
            vitima = _criar_usuario('idor_vitima')
            dados_vitima = _criar_treino_completo(vitima)
            versao_vitima_id = dados_vitima['versao'].id

        _login(client, 'idor_atacante')
        resp = client.get(f'/api/versao-exercicios/{versao_vitima_id}')
        assert resp.status_code == 200
        assert resp.get_json() == []  # nenhum dado da vítima deve vazar

    def test_versao_exercicios_id_inexistente(self, client, app):
        with app.app_context():
            _criar_usuario('idor_inexistente')

        _login(client, 'idor_inexistente')
        resp = client.get('/api/versao-exercicios/999999')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_treino_id_de_outro_usuario_nao_e_editavel(self, client, app):
        with app.app_context():
            atacante = _criar_usuario('idor_treino_atacante')
            vitima = _criar_usuario('idor_treino_vitima')
            dados_vitima = _criar_treino_completo(vitima)
            treino_vitima_id = dados_vitima['treino'].id

        _login(client, 'idor_treino_atacante')
        resp = client.post(
            f'/admin/excluir/treino/{treino_vitima_id}',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Treino, treino_vitima_id) is not None

    def test_treino_id_excluido_nao_e_reeditavel(self, client, app):
        with app.app_context():
            user = _criar_usuario('idor_excluido')
            dados = _criar_treino_completo(user, codigo='B')
            treino_id = dados['treino'].id
            registro = dados['registro']
            # remove o registro/histórico antes, já que o treino tem FK
            db.session.delete(registro)
            db.session.commit()
            db.session.delete(dados['treino'])
            db.session.commit()

        _login(client, 'idor_excluido')
        resp = client.post(f'/admin/excluir/treino/{treino_id}', follow_redirects=True)
        assert resp.status_code == 200  # não deve quebrar (500) num ID já excluído

    def test_evento_calendario_id_sem_relacionamento(self, client, app):
        """Usuário sem nenhum vínculo com o dono do registro."""
        with app.app_context():
            atacante = _criar_usuario('idor_evento_atacante')
            vitima = _criar_usuario('idor_evento_vitima')
            dados = _criar_treino_completo(vitima)
            registro_id = dados['registro'].id

        _login(client, 'idor_evento_atacante')
        resp = client.get(f'/calendar/api/evento/{registro_id}')
        assert resp.status_code == 404
