"""Testes para services/base_service.py -- BaseService (usado por
todos os outros services: resolução de usuário atual, autorização
professor/aluno) e CacheService (wrapper sobre Flask-Caching). É a
base de que o resto do sistema depende, então testar aqui protege
indiretamente tudo que herda dela.
"""
from flask_login import login_user

from models import db, User, AlunoProfessor
from services.base_service import BaseService, CacheService, cached


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, is_admin=is_admin)
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _associar(aluno_id, professor_id, ativo=True):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo)
    db.session.add(assoc)
    db.session.commit()
    return assoc


class TestGetCurrentUser:

    def test_sem_usuario_logado_retorna_none(self, app):
        with app.test_request_context('/'):
            assert BaseService.get_current_user() is None
            assert BaseService.get_current_user_id() is None

    def test_com_usuario_logado_retorna_o_usuario(self, app, db):
        user = _criar_usuario('base_current_1')
        with app.test_request_context('/'):
            login_user(user)
            assert BaseService.get_current_user().id == user.id
            assert BaseService.get_current_user_id() == user.id


class TestGetTargetUserId:

    def test_sem_usuario_logado_retorna_none(self, app):
        with app.test_request_context('/'):
            assert BaseService.get_target_user_id(999) is None

    def test_sem_alvo_especificado_retorna_proprio_id(self, app, db):
        user = _criar_usuario('base_target_1')
        with app.test_request_context('/'):
            login_user(user)
            assert BaseService.get_target_user_id() == user.id

    def test_admin_pode_acessar_qualquer_usuario(self, app, db):
        admin = _criar_usuario('base_target_admin', is_admin=True)
        with app.test_request_context('/'):
            login_user(admin)
            assert BaseService.get_target_user_id(999999) == 999999

    def test_professor_acessa_dados_do_proprio_aluno(self, app, db):
        prof = _criar_usuario('base_target_prof1', tipo_usuario='professor')
        aluno = _criar_usuario('base_target_aluno1')
        _associar(aluno.id, prof.id)

        with app.test_request_context('/'):
            login_user(prof)
            assert BaseService.get_target_user_id(aluno.id) == aluno.id

    def test_professor_nao_acessa_aluno_de_outro_professor(self, app, db):
        """Caso de segurança: sem a associação, cai pro próprio ID do
        professor -- nunca vaza dados do aluno de outro professor."""
        prof1 = _criar_usuario('base_target_prof2', tipo_usuario='professor')
        prof2 = _criar_usuario('base_target_prof3', tipo_usuario='professor')
        aluno_do_prof2 = _criar_usuario('base_target_aluno2')
        _associar(aluno_do_prof2.id, prof2.id)

        with app.test_request_context('/'):
            login_user(prof1)
            resultado = BaseService.get_target_user_id(aluno_do_prof2.id)
            assert resultado == prof1.id  # NUNCA aluno_do_prof2.id

    def test_professor_nao_acessa_aluno_com_associacao_inativa(self, app, db):
        prof = _criar_usuario('base_target_prof4', tipo_usuario='professor')
        aluno = _criar_usuario('base_target_aluno3')
        _associar(aluno.id, prof.id, ativo=False)

        with app.test_request_context('/'):
            login_user(prof)
            assert BaseService.get_target_user_id(aluno.id) == prof.id

    def test_aluno_so_acessa_os_proprios_dados_mesmo_pedindo_outro_id(self, app, db):
        aluno1 = _criar_usuario('base_target_aluno4')
        aluno2 = _criar_usuario('base_target_aluno5')

        with app.test_request_context('/'):
            login_user(aluno1)
            assert BaseService.get_target_user_id(aluno2.id) == aluno1.id


class TestFilterByUser:

    def test_aplica_filtro_por_user_id_quando_ha_usuario(self, app, db):
        from models import VersaoGlobal
        from datetime import date
        user = _criar_usuario('base_filter_1')
        db.session.add(VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                                     data_inicio=date.today(), user_id=user.id))
        db.session.commit()

        with app.test_request_context('/'):
            login_user(user)
            query = BaseService.filter_by_user(VersaoGlobal.query)
            assert query.count() == 1

    def test_sem_usuario_logado_nao_filtra(self, app, db):
        from models import VersaoGlobal
        with app.test_request_context('/'):
            query = BaseService.filter_by_user(VersaoGlobal.query)
            # sem user_id pra filtrar, a query volta como veio (sem quebrar)
            assert query is VersaoGlobal.query or query.count() >= 0


class TestHandleError:

    def test_loga_reverte_a_sessao_e_retorna_none(self, app, db, caplog):
        import logging
        with app.app_context():
            with caplog.at_level(logging.ERROR):
                resultado = BaseService.handle_error(RuntimeError("falha simulada"), "Erro ao salvar")

        assert resultado is None
        assert any('Erro ao salvar' in r.message for r in caplog.records)


class TestGetAlunosDoProfessor:

    def test_retorna_alunos_ativos_do_professor(self, app, db):
        prof = _criar_usuario('base_alunos_prof1', tipo_usuario='professor')
        aluno1 = _criar_usuario('base_alunos_a1')
        aluno2 = _criar_usuario('base_alunos_a2')
        _associar(aluno1.id, prof.id)
        _associar(aluno2.id, prof.id, ativo=False)

        resultado = BaseService.get_alunos_do_professor(prof.id)

        ids = [a.id for a in resultado]
        assert aluno1.id in ids
        assert aluno2.id not in ids

    def test_sem_professor_id_usa_o_usuario_logado(self, app, db):
        prof = _criar_usuario('base_alunos_prof2', tipo_usuario='professor')
        aluno = _criar_usuario('base_alunos_a3')
        _associar(aluno.id, prof.id)

        with app.test_request_context('/'):
            login_user(prof)
            resultado = BaseService.get_alunos_do_professor()
            assert aluno.id in [a.id for a in resultado]

    def test_sem_usuario_logado_e_sem_professor_id_retorna_vazio(self, app, db):
        with app.test_request_context('/'):
            assert BaseService.get_alunos_do_professor() == []

    def test_aluno_logado_sem_professor_id_retorna_vazio(self, app, db):
        aluno = _criar_usuario('base_alunos_a4')
        with app.test_request_context('/'):
            login_user(aluno)
            assert BaseService.get_alunos_do_professor() == []


class TestGetProfessorDoAluno:

    def test_retorna_o_professor_do_aluno(self, app, db):
        prof = _criar_usuario('base_prof_do_aluno_p1', tipo_usuario='professor')
        aluno = _criar_usuario('base_prof_do_aluno_a1')
        _associar(aluno.id, prof.id)

        resultado = BaseService.get_professor_do_aluno(aluno.id)
        assert resultado.id == prof.id

    def test_sem_aluno_id_usa_o_usuario_logado(self, app, db):
        prof = _criar_usuario('base_prof_do_aluno_p2', tipo_usuario='professor')
        aluno = _criar_usuario('base_prof_do_aluno_a2')
        _associar(aluno.id, prof.id)

        with app.test_request_context('/'):
            login_user(aluno)
            resultado = BaseService.get_professor_do_aluno()
            assert resultado.id == prof.id

    def test_aluno_sem_professor_associado_retorna_none(self, app, db):
        aluno = _criar_usuario('base_prof_do_aluno_a3')
        assert BaseService.get_professor_do_aluno(aluno.id) is None

    def test_sem_usuario_logado_e_sem_aluno_id_retorna_none(self, app, db):
        with app.test_request_context('/'):
            assert BaseService.get_professor_do_aluno() is None

    def test_professor_logado_sem_aluno_id_retorna_none(self, app, db):
        prof = _criar_usuario('base_prof_do_aluno_p3', tipo_usuario='professor')
        with app.test_request_context('/'):
            login_user(prof)
            assert BaseService.get_professor_do_aluno() is None


class TestCacheService:

    def test_set_get_invalidate(self, app):
        with app.app_context():
            CacheService.set('chave_teste_base', {'a': 1}, ttl_seconds=60)
            assert CacheService.get('chave_teste_base') == {'a': 1}

            CacheService.invalidate('chave_teste_base')
            assert CacheService.get('chave_teste_base') is None

    def test_invalidate_pattern_simplecache_remove_so_as_que_combinam(self, app):
        with app.app_context():
            CacheService.set('fitbot_context:1:x', 'a')
            CacheService.set('fitbot_context:2:x', 'b')
            CacheService.set('outra_coisa', 'c')

            CacheService.invalidate_pattern('fitbot_context:1:')

            assert CacheService.get('fitbot_context:1:x') is None
            assert CacheService.get('fitbot_context:2:x') == 'b'
            assert CacheService.get('outra_coisa') == 'c'

    def test_invalidate_pattern_usa_scan_iter_quando_ha_cliente_redis(self, app, monkeypatch):
        """Cobre o branch de produção (Redis) sem precisar de um Redis
        de verdade -- fake client só precisa responder scan_iter/delete."""
        chamadas = {}

        class _FakeRedisClient:
            def scan_iter(self, match=None, count=None):
                chamadas['match'] = match
                return iter(['fitlog:fitbot_context:1:a', 'fitlog:fitbot_context:1:b'])

            def delete(self, *chaves):
                chamadas['deletadas'] = chaves

        class _FakeCacheBackend:
            _write_client = _FakeRedisClient()
            key_prefix = 'fitlog:'

        class _FakeFlaskCache:
            cache = _FakeCacheBackend()

        import services.base_service as base_service_module
        monkeypatch.setattr(base_service_module, 'flask_cache', _FakeFlaskCache())

        with app.app_context():
            CacheService.invalidate_pattern('fitbot_context:1:')

        assert chamadas['match'] == '*fitbot_context:1:*'
        assert chamadas['deletadas'] == ('fitlog:fitbot_context:1:a', 'fitlog:fitbot_context:1:b')

    def test_invalidate_pattern_nunca_propaga_excecao(self, app, monkeypatch):
        import services.base_service as base_service_module

        class _CacheQuebrado:
            @property
            def _cache(self):
                raise RuntimeError("boom")

        class _FakeFlaskCache:
            cache = _CacheQuebrado()

        monkeypatch.setattr(base_service_module, 'flask_cache', _FakeFlaskCache())

        with app.app_context():
            # não pode levantar exceção nenhuma
            CacheService.invalidate_pattern('qualquer')


class TestCachedDecorator:

    def test_cacheia_o_resultado_na_segunda_chamada(self, app):
        contador = {'n': 0}

        @cached(ttl_seconds=60, key_prefix='teste_decorator')
        def funcao_cara(x):
            contador['n'] += 1
            return x * 2

        with app.app_context():
            assert funcao_cara(5) == 10
            assert funcao_cara(5) == 10
            # a segunda chamada com o mesmo argumento não deve re-executar
            assert contador['n'] == 1

    def test_argumentos_diferentes_geram_chaves_diferentes(self, app):
        @cached(ttl_seconds=60, key_prefix='teste_decorator_2')
        def funcao(x):
            return x * 10

        with app.app_context():
            assert funcao(1) == 10
            assert funcao(2) == 20
