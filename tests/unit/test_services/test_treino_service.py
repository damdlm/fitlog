"""
Testes unitários para services/treino_service.py cobrindo casos de
borda não exercitados pelas rotas (conflito de código na edição,
case-insensitivity, isolamento entre usuários).
"""
from models import db, User, Treino
from flask_login import login_user
from services.treino_service import TreinoService


def _criar_usuario(username):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario='aluno', nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


class TestGetByCodigo:
    def test_busca_case_insensitive(self, app):
        with app.app_context():
            u = _criar_usuario('ts_codigo_1')
            TreinoService.create('a', 'Treino A', 'd', user_id=u.id)

            encontrado = TreinoService.get_by_codigo('a', user_id=u.id)
            assert encontrado is not None
            assert encontrado.codigo == 'A'

    def test_nao_encontra_treino_de_outro_usuario(self, app):
        with app.app_context():
            a = _criar_usuario('ts_codigo_a')
            b = _criar_usuario('ts_codigo_b')
            TreinoService.create('A', 'Treino do B', 'd', user_id=b.id)

            # 'a' está logado e tenta espiar o treino 'A' de 'b' passando
            # user_id=b.id -- get_target_user_id() ignora esse parâmetro
            # pra usuário não-admin/não-professor e usa sempre o próprio
            # current_user.id, então isso nunca deveria "vazar" dado de b.
            with app.test_request_context():
                login_user(a)
                resultado = TreinoService.get_by_codigo('A', user_id=b.id)
                assert resultado is None


class TestCreate:
    def test_nao_cria_sem_usuario(self, app):
        with app.app_context():
            resultado = TreinoService.create('A', 'Treino A', 'd', user_id=None)
            assert resultado is None

    def test_nao_cria_codigo_duplicado_mesmo_usuario(self, app):
        with app.app_context():
            u = _criar_usuario('ts_create_dup')
            t1 = TreinoService.create('A', 'Primeiro', 'd', user_id=u.id)
            t2 = TreinoService.create('A', 'Segundo', 'd', user_id=u.id)

            assert t1 is not None
            assert t2 is None

    def test_mesmo_codigo_em_usuarios_diferentes_e_permitido(self, app):
        # create() usa o user_id passado diretamente para GRAVAR, mas a
        # checagem de duplicidade (get_by_codigo) passa por filter_by_user,
        # que só filtra de verdade dentro de uma sessão logada (ver
        # BaseService.get_target_user_id). Por isso simulamos login aqui:
        # sem isso, a checagem de duplicidade "vaza" entre usuários porque
        # cai no fallback sem filtro nenhum.
        with app.app_context():
            a = _criar_usuario('ts_create_iso_a')
            b = _criar_usuario('ts_create_iso_b')
            a_id, b_id = a.id, b.id

        with app.test_request_context():
            login_user(db.session.get(User, a_id))
            t_a = TreinoService.create('A', 'Treino de A', 'd', user_id=a_id)

        with app.test_request_context():
            login_user(db.session.get(User, b_id))
            t_b = TreinoService.create('A', 'Treino de B', 'd', user_id=b_id)

        assert t_a is not None
        assert t_b is not None
        assert t_a.id != t_b.id


class TestUpdate:
    def test_atualiza_nome_e_descricao(self, app):
        with app.app_context():
            u = _criar_usuario('ts_update_1')
            t = TreinoService.create('A', 'Nome antigo', 'desc antiga', user_id=u.id)

            atualizado = TreinoService.update(t.id, nome='Nome novo', descricao='desc nova', user_id=u.id)
            assert atualizado.nome == 'Nome novo'
            assert atualizado.descricao == 'desc nova'

    def test_atualiza_codigo_para_um_livre(self, app):
        with app.app_context():
            u = _criar_usuario('ts_update_2')
            t = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)

            atualizado = TreinoService.update(t.id, codigo='B', user_id=u.id)
            assert atualizado.codigo == 'B'

    def test_nao_atualiza_para_codigo_ja_em_uso_por_outro_treino(self, app):
        with app.app_context():
            u = _criar_usuario('ts_update_3')
            TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            t_b = TreinoService.create('B', 'Treino B', 'd', user_id=u.id)

            resultado = TreinoService.update(t_b.id, codigo='A', user_id=u.id)
            assert resultado is None

            with app.app_context():
                t_b_recarregado = db.session.get(type(t_b), t_b.id)
                assert t_b_recarregado.codigo == 'B'  # não mudou

    def test_atualizar_para_o_proprio_codigo_atual_e_permitido(self, app):
        with app.app_context():
            u = _criar_usuario('ts_update_4')
            t = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)

            resultado = TreinoService.update(t.id, codigo='A', nome='Novo nome', user_id=u.id)
            assert resultado is not None
            assert resultado.nome == 'Novo nome'

    def test_treino_inexistente_retorna_none(self, app):
        with app.app_context():
            u = _criar_usuario('ts_update_5')
            resultado = TreinoService.update(999999, nome='X', user_id=u.id)
            assert resultado is None

    def test_nao_atualiza_treino_de_outro_usuario(self, app):
        with app.app_context():
            a = _criar_usuario('ts_update_iso_a')
            b = _criar_usuario('ts_update_iso_b')
            a_id, b_id = a.id, b.id
            t_b = TreinoService.create('A', 'Treino do B', 'd', user_id=b_id)
            t_b_id = t_b.id

        with app.test_request_context():
            login_user(db.session.get(User, a_id))
            resultado = TreinoService.update(t_b_id, nome='Hackeado', user_id=b_id)
            assert resultado is None

        with app.app_context():
            t_b_recarregado = db.session.get(Treino, t_b_id)
            assert t_b_recarregado.nome == 'Treino do B'


class TestDelete:
    def test_exclui_treino_existente(self, app):
        with app.app_context():
            u = _criar_usuario('ts_delete_1')
            t = TreinoService.create('A', 'Treino A', 'd', user_id=u.id)
            t_id = t.id

            ok = TreinoService.delete(t_id, user_id=u.id)
            assert ok is True
            assert TreinoService.get_by_id(t_id, user_id=u.id) is None

    def test_excluir_inexistente_retorna_false(self, app):
        with app.app_context():
            u = _criar_usuario('ts_delete_2')
            ok = TreinoService.delete(999999, user_id=u.id)
            assert ok is False

    def test_nao_exclui_treino_de_outro_usuario(self, app):
        with app.app_context():
            a = _criar_usuario('ts_delete_iso_a')
            b = _criar_usuario('ts_delete_iso_b')
            a_id, b_id = a.id, b.id
            t_b = TreinoService.create('A', 'Treino do B', 'd', user_id=b_id)
            t_b_id = t_b.id

        with app.test_request_context():
            login_user(db.session.get(User, a_id))
            ok = TreinoService.delete(t_b_id, user_id=b_id)
            assert ok is False

        with app.app_context():
            assert db.session.get(Treino, t_b_id) is not None
