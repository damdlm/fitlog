"""Testes unitários para services/registro_service.py"""
from datetime import date, datetime, timedelta

from flask_login import login_user

from models import db, User, Treino, VersaoGlobal, ExercicioUsuario
from services.registro_service import RegistroService


def _criar_usuario(username):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario='aluno', nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _criar_cenario_base(username):
    """Cria usuário + treino + versão + exercício de usuário, sem registros."""
    u = _criar_usuario(username)
    t = Treino(codigo='A', nome='Treino A', descricao='d', user_id=u.id)
    db.session.add(t)
    db.session.commit()

    v = VersaoGlobal(numero_versao=1, descricao='v1', divisao='ABC',
                      data_inicio=date(2024, 1, 1), user_id=u.id)
    db.session.add(v)
    db.session.commit()

    ex = ExercicioUsuario(usuario_id=u.id, nome='Supino')
    db.session.add(ex)
    db.session.commit()

    return u, t, v, ex


def _salvar_sessao(t, v, ex, user_id, periodo='Janeiro/2024', semana=1, carga=50,
                    repeticoes=10, num_series=3):
    dados = {
        ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': carga,
                'repeticoes': repeticoes, 'num_series': num_series}
    }
    return RegistroService.salvar_registros(t.id, v.id, periodo, semana, dados, user_id=user_id)


class TestSalvarRegistros:
    def test_salva_com_sucesso(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_salvar_1')
            resultado = _salvar_sessao(t, v, ex, u.id)
            assert resultado is True

            registros = RegistroService.get_all(user_id=u.id, load_series=True)
            assert len(registros) == 1
            assert len(registros[0].series) == 3

    def test_sem_user_id_retorna_false(self, app):
        with app.app_context():
            resultado = RegistroService.salvar_registros(1, 1, 'Janeiro/2024', 1, {}, user_id=None)
            assert resultado is False

    def test_ignora_exercicio_sem_carga(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_salvar_2')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': None,
                              'repeticoes': 10, 'num_series': 3}}
            resultado = RegistroService.salvar_registros(t.id, v.id, 'Janeiro/2024', 1, dados,
                                                           user_id=u.id)
            assert resultado is True
            assert RegistroService.get_all(user_id=u.id) == []

    def test_substitui_sessao_existente(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_salvar_3')
            _salvar_sessao(t, v, ex, u.id, carga=50)
            _salvar_sessao(t, v, ex, u.id, carga=60)

            registros = RegistroService.get_all(user_id=u.id, load_series=True)
            assert len(registros) == 1
            assert float(registros[0].series[0].carga) == 60

    def test_grava_tempo_treino_nas_series(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_salvar_4')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1}}
            RegistroService.salvar_registros(t.id, v.id, 'Janeiro/2024', 1, dados,
                                              user_id=u.id, tempo_treino=1800)

            registros = RegistroService.get_all(user_id=u.id, load_series=True)
            assert registros[0].series[0].tempo_treino == 1800


class TestGetAll:
    def test_vazio_sem_registros(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_1')
            assert RegistroService.get_all(user_id=u.id) == []

    def test_filtra_por_treino_id(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_2')
            _salvar_sessao(t, v, ex, u.id)

            resultado = RegistroService.get_all(filtros={'treino_id': t.id}, user_id=u.id)
            assert len(resultado) == 1

            resultado_vazio = RegistroService.get_all(filtros={'treino_id': 99999}, user_id=u.id)
            assert resultado_vazio == []

    def test_filtra_por_periodo_semana_versao(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_3')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=1)

            assert len(RegistroService.get_all(
                filtros={'periodo': 'Janeiro/2024', 'semana': 1, 'versao_id': v.id},
                user_id=u.id)) == 1
            assert RegistroService.get_all(filtros={'periodo': 'Fevereiro/2024'}, user_id=u.id) == []

    def test_filtra_por_exercicio_id(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_4')
            _salvar_sessao(t, v, ex, u.id)

            resultado = RegistroService.get_all(filtros={'exercicio_id': ex.id}, user_id=u.id)
            assert len(resultado) == 1

    def test_filtra_por_intervalo_de_datas(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_5')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1,
                              'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            dentro = RegistroService.get_all(
                user_id=u.id, data_inicio=datetime(2024, 6, 1), data_fim=datetime(2024, 7, 1))
            assert len(dentro) == 1

            fora = RegistroService.get_all(
                user_id=u.id, data_inicio=datetime(2024, 7, 1), data_fim=datetime(2024, 8, 1))
            assert fora == []

    def test_isolamento_entre_usuarios(self, app):
        with app.app_context():
            u1, t1, v1, ex1 = _criar_cenario_base('rs_getall_iso1')
            u2, t2, v2, ex2 = _criar_cenario_base('rs_getall_iso2')
            _salvar_sessao(t1, v1, ex1, u1.id)
            _salvar_sessao(t2, v2, ex2, u2.id)

            assert len(RegistroService.get_all(user_id=u1.id)) == 1
            assert len(RegistroService.get_all(user_id=u2.id)) == 1

    def test_usa_current_user_quando_sem_user_id(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getall_current')
            _salvar_sessao(t, v, ex, u.id)
            u_id = u.id

        with app.test_request_context():
            login_user(db.session.get(User, u_id))
            resultado = RegistroService.get_all()
            assert len(resultado) == 1

    def test_vazio_sem_usuario_autenticado(self, app):
        with app.app_context():
            assert RegistroService.get_all() == []


class TestGetTreinoPorData:
    def test_encontra_registro_do_dia(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_treinodata_1')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1,
                              'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            resultado = RegistroService.get_treino_por_data('2024-06-15', user_id=u.id)
            assert resultado is not None
            assert resultado.treino_id == t.id

    def test_none_para_dia_sem_registro(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_treinodata_2')
            resultado = RegistroService.get_treino_por_data('2024-06-15', user_id=u.id)
            assert resultado is None

    def test_none_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_treino_por_data('2024-06-15') is None

    def test_aceita_objeto_date(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_treinodata_3')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1,
                              'data_registro': datetime(2024, 6, 20)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            resultado = RegistroService.get_treino_por_data(date(2024, 6, 20), user_id=u.id)
            assert resultado is not None


class TestExcluirPorTreinoData:
    def test_exclui_registros_e_series(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_excluir_1')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 2,
                              'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            resultado = RegistroService.excluir_por_treino_data(t.id, v.id, '2024-06-15', user_id=u.id)
            assert resultado is True
            assert RegistroService.get_all(user_id=u.id) == []

    def test_false_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.excluir_por_treino_data(1, 1, '2024-06-15') is False

    def test_nao_afeta_outras_datas(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_excluir_2')
            dados1 = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                               'repeticoes': 10, 'num_series': 1,
                               'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados1, user_id=u.id)
            dados2 = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                               'repeticoes': 10, 'num_series': 1,
                               'data_registro': datetime(2024, 6, 22)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 2, dados2, user_id=u.id)

            RegistroService.excluir_por_treino_data(t.id, v.id, '2024-06-15', user_id=u.id)
            assert len(RegistroService.get_all(user_id=u.id)) == 1


class TestGetByData:
    def test_encontra_registros_do_dia(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getbydata_1')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1,
                              'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            resultado = RegistroService.get_by_data(t.id, v.id, '2024-06-15', user_id=u.id)
            assert len(resultado) == 1

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_by_data(1, 1, '2024-06-15') == []

    def test_vazio_para_dia_diferente(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_getbydata_2')
            dados = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                              'repeticoes': 10, 'num_series': 1,
                              'data_registro': datetime(2024, 6, 15)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados, user_id=u.id)

            resultado = RegistroService.get_by_data(t.id, v.id, '2024-06-16', user_id=u.id)
            assert resultado == []


class TestSalvarRegistroUnico:
    def test_salva_com_sucesso(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_unico_1')
            resultado = RegistroService.salvar_registro_unico(
                t.id, v.id, 'Janeiro/2024', 1, ex.id, 50, 10, num_series=3, user_id=u.id)

            assert resultado is not None
            assert resultado.exercicio_usuario_id == ex.id
            assert len(resultado.series) == 3

    def test_none_sem_usuario(self, app):
        with app.app_context():
            resultado = RegistroService.salvar_registro_unico(
                1, 1, 'Janeiro/2024', 1, 1, 50, 10)
            assert resultado is None

    def test_none_se_exercicio_nao_existe(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_unico_2')
            resultado = RegistroService.salvar_registro_unico(
                t.id, v.id, 'Janeiro/2024', 1, 99999, 50, 10, user_id=u.id)
            assert resultado is None

    def test_substitui_registro_existente_do_mesmo_exercicio(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_unico_3')
            RegistroService.salvar_registro_unico(
                t.id, v.id, 'Janeiro/2024', 1, ex.id, 50, 10, user_id=u.id)
            RegistroService.salvar_registro_unico(
                t.id, v.id, 'Janeiro/2024', 1, ex.id, 70, 8, user_id=u.id)

            registros = RegistroService.get_all(user_id=u.id, load_series=True)
            assert len(registros) == 1
            assert float(registros[0].series[0].carga) == 70


class TestGetPeriodosExistentes:
    def test_retorna_periodos_ordenados_desc(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_periodos_1')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024')
            _salvar_sessao(t, v, ex, u.id, periodo='Marco/2024', semana=2)

            resultado = RegistroService.get_periodos_existentes(user_id=u.id)
            assert resultado == ['Marco/2024', 'Janeiro/2024']

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_periodos_existentes() == []


class TestGetSemanasPorPeriodo:
    def test_agrupa_semanas_por_periodo(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_semanas_1')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=1)
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=2)

            resultado = RegistroService.get_semanas_por_periodo(user_id=u.id)
            assert 'Janeiro/2024' in resultado
            semanas = {item['semana'] for item in resultado['Janeiro/2024']}
            assert semanas == {1, 2}

    def test_vazio_sem_registros(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_semanas_2')
            assert RegistroService.get_semanas_por_periodo(user_id=u.id) == {}


class TestGetVolumeTotalPorSemana:
    def test_calcula_volume_corretamente(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_volume_1')
            _salvar_sessao(t, v, ex, u.id, carga=50, repeticoes=10, num_series=3)

            registros = RegistroService.get_all(user_id=u.id, load_series=True)
            resultado = RegistroService.get_volume_total_por_semana(registros)

            key = f"{registros[0].periodo}_{registros[0].semana}"
            assert resultado[key] == 50 * 10 * 3

    def test_vazio_sem_registros(self, app):
        with app.app_context():
            assert RegistroService.get_volume_total_por_semana([]) == {}


class TestGetPorExercicio:
    def test_encontra_registros_do_exercicio(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_porex_1')
            _salvar_sessao(t, v, ex, u.id)

            resultado = RegistroService.get_por_exercicio(ex.id, user_id=u.id)
            assert len(resultado) == 1

    def test_respeita_limite(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_porex_2')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=1)
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=2)

            resultado = RegistroService.get_por_exercicio(ex.id, limite=1, user_id=u.id)
            assert len(resultado) == 1

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_por_exercicio(1) == []


class TestGetPorPeriodo:
    def test_encontra_registros_do_periodo(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_porperiodo_1')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024')

            resultado = RegistroService.get_por_periodo('Janeiro/2024', user_id=u.id)
            assert len(resultado) == 1

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_por_periodo('Janeiro/2024') == []


class TestGetPorSemana:
    def test_encontra_registros_da_semana(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_porsemana_1')
            _salvar_sessao(t, v, ex, u.id, periodo='Janeiro/2024', semana=2)

            resultado = RegistroService.get_por_semana('Janeiro/2024', 2, user_id=u.id)
            assert len(resultado) == 1

            assert RegistroService.get_por_semana('Janeiro/2024', 3, user_id=u.id) == []

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_por_semana('Janeiro/2024', 1) == []


class TestGetUltimoRegistroPorExercicio:
    def test_retorna_mais_recente(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_ultimo_1')
            dados1 = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 50,
                               'repeticoes': 10, 'num_series': 1,
                               'data_registro': datetime(2024, 6, 1)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 1, dados1, user_id=u.id)
            dados2 = {ex.id: {'exercicio_id': ex.id, 'tipo': 'usuario', 'carga': 60,
                               'repeticoes': 8, 'num_series': 1,
                               'data_registro': datetime(2024, 6, 10)}}
            RegistroService.salvar_registros(t.id, v.id, 'Junho/2024', 2, dados2, user_id=u.id)

            resultado = RegistroService.get_ultimo_registro_por_exercicio(ex.id, user_id=u.id)
            assert resultado is not None
            assert float(resultado.series[0].carga) == 60

    def test_none_sem_registros(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_ultimo_2')
            assert RegistroService.get_ultimo_registro_por_exercicio(ex.id, user_id=u.id) is None

    def test_none_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_ultimo_registro_por_exercicio(1) is None


class TestGetEstatisticasExercicio:
    def test_calcula_estatisticas_corretamente(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_estat_1')
            _salvar_sessao(t, v, ex, u.id, carga=50, repeticoes=10, num_series=2)

            resultado = RegistroService.get_estatisticas_exercicio(ex.id, user_id=u.id)
            assert resultado['total_registros'] == 1
            assert resultado['total_series'] == 2
            assert resultado['media_carga'] == 50
            assert resultado['media_repeticoes'] == 10
            assert resultado['maior_carga'] == 50
            assert resultado['maior_volume'] == 500

    def test_vazio_sem_registros(self, app):
        with app.app_context():
            u, t, v, ex = _criar_cenario_base('rs_estat_2')
            assert RegistroService.get_estatisticas_exercicio(ex.id, user_id=u.id) == {}

    def test_vazio_sem_usuario(self, app):
        with app.app_context():
            assert RegistroService.get_estatisticas_exercicio(1) == {}
