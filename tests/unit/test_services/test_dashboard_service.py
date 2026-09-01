"""Testes unitários para services/dashboard_service.py (painel
operacional do professor)."""
from datetime import date, datetime, timedelta, timezone

from models import db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, RegistroTreino
from services.dashboard_service import DashboardService, _hoje_br


def _criar_usuario(username, tipo_usuario='aluno', ativo=True, nome_completo=None):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo_usuario, ativo=ativo,
             nome_completo=nome_completo or username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _associar(aluno_id, professor_id, ativo=True, data_associacao=None):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo,
                            data_associacao=data_associacao or datetime.now(timezone.utc))
    db.session.add(assoc)
    db.session.commit()
    return assoc


def _criar_versao(user_id, numero_versao=1, data_inicio=None, data_fim=None):
    v = VersaoGlobal(numero_versao=numero_versao, descricao=f'V{numero_versao}', divisao='ABC',
                      data_inicio=data_inicio or date.today(), data_fim=data_fim, user_id=user_id)
    db.session.add(v)
    db.session.commit()
    return v


def _criar_treino(versao_id, codigo='A'):
    t = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=f'Treino {codigo}')
    db.session.add(t)
    db.session.commit()
    return t


def _criar_registro(user_id, treino_versao_id, versao_id, data_registro):
    r = RegistroTreino(treino_versao_id=treino_versao_id, versao_id=versao_id,
                        periodo='Agosto/2026', semana=1, exercicio_base_id=None,
                        exercicio_usuario_id=None, data_registro=data_registro, user_id=user_id)
    # exactly-one-exercicio constraint: usa exercicio_base_id fake não é
    # necessário para estas métricas (não olham HistoricoTreino), mas o
    # check constraint do banco exige uma das duas FKs preenchida.
    return r


def _criar_registro_valido(user_id, treino_versao_id, versao_id, data_registro, exercicio_base_id):
    r = RegistroTreino(treino_versao_id=treino_versao_id, versao_id=versao_id,
                        periodo='Agosto/2026', semana=1, exercicio_base_id=exercicio_base_id,
                        data_registro=data_registro, user_id=user_id)
    db.session.add(r)
    db.session.commit()
    return r


def _criar_exercicio_sistema():
    from models import ExercicioSistema
    ex = ExercicioSistema(id_original='999001', nome='Supino', grupo_muscular='Peito')
    db.session.add(ex)
    db.session.commit()
    return ex


class TestTotalAlunos:
    def test_zero_alunos(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ta_1', tipo_usuario='professor')
            dados = DashboardService.dados_professor(prof.id)
            assert dados['total_alunos'] == 0

    def test_um_aluno(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ta_2', tipo_usuario='professor')
            aluno = _criar_usuario('ds_ta_2_aluno')
            _associar(aluno.id, prof.id)
            dados = DashboardService.dados_professor(prof.id)
            assert dados['total_alunos'] == 1

    def test_varios_alunos(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ta_3', tipo_usuario='professor')
            for i in range(4):
                aluno = _criar_usuario(f'ds_ta_3_aluno{i}')
                _associar(aluno.id, prof.id)
            dados = DashboardService.dados_professor(prof.id)
            assert dados['total_alunos'] == 4

    def test_ignora_aluno_inativo(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ta_4', tipo_usuario='professor')
            aluno = _criar_usuario('ds_ta_4_aluno', ativo=False)
            _associar(aluno.id, prof.id)
            dados = DashboardService.dados_professor(prof.id)
            assert dados['total_alunos'] == 0

    def test_ignora_vinculo_inativo(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ta_5', tipo_usuario='professor')
            aluno = _criar_usuario('ds_ta_5_aluno')
            _associar(aluno.id, prof.id, ativo=False)
            dados = DashboardService.dados_professor(prof.id)
            assert dados['total_alunos'] == 0

    def test_nao_conta_aluno_de_outro_professor(self, app):
        with app.app_context():
            prof1 = _criar_usuario('ds_ta_6a', tipo_usuario='professor')
            prof2 = _criar_usuario('ds_ta_6b', tipo_usuario='professor')
            aluno = _criar_usuario('ds_ta_6_aluno')
            _associar(aluno.id, prof2.id)
            dados = DashboardService.dados_professor(prof1.id)
            assert dados['total_alunos'] == 0
            dados2 = DashboardService.dados_professor(prof2.id)
            assert dados2['total_alunos'] == 1


class TestTreinaramHoje:
    def test_ninguem_treinou(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_th_1', tipo_usuario='professor')
            aluno = _criar_usuario('ds_th_1_aluno')
            _associar(aluno.id, prof.id)
            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinaram_hoje'] == 0

    def test_um_aluno_treinou_hoje(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_th_2', tipo_usuario='professor')
            aluno = _criar_usuario('ds_th_2_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            _criar_registro_valido(aluno.id, treino.id, versao.id, _hoje_br(), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinaram_hoje'] == 1

    def test_mesmo_aluno_varios_registros_conta_uma_vez(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_th_3', tipo_usuario='professor')
            aluno = _criar_usuario('ds_th_3_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            _criar_registro_valido(aluno.id, treino.id, versao.id, _hoje_br(), ex.id)
            treino2 = _criar_treino(versao.id, codigo='B')
            _criar_registro_valido(aluno.id, treino2.id, versao.id, _hoje_br(), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinaram_hoje'] == 1

    def test_registro_de_ontem_nao_conta(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_th_4', tipo_usuario='professor')
            aluno = _criar_usuario('ds_th_4_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            ontem = _hoje_br() - timedelta(days=1)
            _criar_registro_valido(aluno.id, treino.id, versao.id, ontem, ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinaram_hoje'] == 0

    def test_varios_alunos_treinaram(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_th_5', tipo_usuario='professor')
            ex = _criar_exercicio_sistema()
            for i in range(3):
                aluno = _criar_usuario(f'ds_th_5_aluno{i}')
                _associar(aluno.id, prof.id)
                versao = _criar_versao(aluno.id)
                treino = _criar_treino(versao.id)
                _criar_registro_valido(aluno.id, treino.id, versao.id, _hoje_br(), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinaram_hoje'] == 3


class TestAlunosAtencao:
    def test_exatamente_7_dias_aparece(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_1', tipo_usuario='professor')
            aluno = _criar_usuario('ds_aa_1_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            _criar_registro_valido(aluno.id, treino.id, versao.id,
                                    _hoje_br() - timedelta(days=7), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['alunos_atencao']['total'] == 1
            assert dados['alunos_atencao']['itens'][0]['dias_parado'] == 7

    def test_6_dias_nao_aparece(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_2', tipo_usuario='professor')
            aluno = _criar_usuario('ds_aa_2_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            _criar_registro_valido(aluno.id, treino.id, versao.id,
                                    _hoje_br() - timedelta(days=6), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['alunos_atencao']['total'] == 0

    def test_30_dias_aparece_com_valor_correto(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_3', tipo_usuario='professor')
            aluno = _criar_usuario('ds_aa_3_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            _criar_registro_valido(aluno.id, treino.id, versao.id,
                                    _hoje_br() - timedelta(days=30), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            assert dados['alunos_atencao']['itens'][0]['dias_parado'] == 30

    def test_aluno_sem_nenhum_treino_aparece_como_nunca_treinou(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_4', tipo_usuario='professor')
            aluno = _criar_usuario('ds_aa_4_aluno')
            _associar(aluno.id, prof.id,
                      data_associacao=datetime.now(timezone.utc) - timedelta(days=10))

            dados = DashboardService.dados_professor(prof.id)
            assert dados['alunos_atencao']['total'] == 1
            assert dados['alunos_atencao']['itens'][0]['nunca_treinou'] is True

    def test_aluno_inativo_nao_aparece(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_5', tipo_usuario='professor')
            aluno = _criar_usuario('ds_aa_5_aluno', ativo=False)
            _associar(aluno.id, prof.id,
                      data_associacao=datetime.now(timezone.utc) - timedelta(days=30))

            dados = DashboardService.dados_professor(prof.id)
            assert dados['alunos_atencao']['total'] == 0

    def test_ordenado_pelo_maior_tempo_parado(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_aa_6', tipo_usuario='professor')
            ex = _criar_exercicio_sistema()

            aluno_a = _criar_usuario('ds_aa_6_a', nome_completo='Aluno Pouco Tempo')
            _associar(aluno_a.id, prof.id)
            versao_a = _criar_versao(aluno_a.id)
            treino_a = _criar_treino(versao_a.id)
            _criar_registro_valido(aluno_a.id, treino_a.id, versao_a.id,
                                    _hoje_br() - timedelta(days=8), ex.id)

            aluno_b = _criar_usuario('ds_aa_6_b', nome_completo='Aluno Muito Tempo')
            _associar(aluno_b.id, prof.id)
            versao_b = _criar_versao(aluno_b.id)
            treino_b = _criar_treino(versao_b.id)
            _criar_registro_valido(aluno_b.id, treino_b.id, versao_b.id,
                                    _hoje_br() - timedelta(days=20), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            nomes = [i['nome'] for i in dados['alunos_atencao']['itens']]
            assert nomes[0] == 'Aluno Muito Tempo'
            assert nomes[1] == 'Aluno Pouco Tempo'


class TestTreinosRevisao:
    def test_versao_recente_nao_aparece(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_tr_1', tipo_usuario='professor')
            aluno = _criar_usuario('ds_tr_1_aluno')
            _associar(aluno.id, prof.id)
            _criar_versao(aluno.id, data_inicio=date.today())

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinos_revisao']['total'] == 0

    def test_versao_com_60_dias_aparece(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_tr_2', tipo_usuario='professor')
            aluno = _criar_usuario('ds_tr_2_aluno')
            _associar(aluno.id, prof.id)
            _criar_versao(aluno.id, data_inicio=date.today() - timedelta(days=60))

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinos_revisao']['total'] == 1

    def test_versao_finalizada_nao_aparece_mesmo_antiga(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_tr_3', tipo_usuario='professor')
            aluno = _criar_usuario('ds_tr_3_aluno')
            _associar(aluno.id, prof.id)
            _criar_versao(aluno.id, data_inicio=date.today() - timedelta(days=90),
                          data_fim=date.today() - timedelta(days=61))

            dados = DashboardService.dados_professor(prof.id)
            assert dados['treinos_revisao']['total'] == 0


class TestAderencia:
    def test_sem_alunos_retorna_none(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ad_1', tipo_usuario='professor')
            dados = DashboardService.dados_professor(prof.id)
            assert dados['aderencia']['pct'] is None

    def test_aderencia_calculada_a_partir_de_dias_com_treino(self, app):
        with app.app_context():
            prof = _criar_usuario('ds_ad_2', tipo_usuario='professor')
            aluno = _criar_usuario('ds_ad_2_aluno')
            _associar(aluno.id, prof.id)
            versao = _criar_versao(aluno.id)
            treino = _criar_treino(versao.id)
            ex = _criar_exercicio_sistema()
            for dias_atras in range(10):
                _criar_registro_valido(aluno.id, treino.id, versao.id,
                                        _hoje_br() - timedelta(days=dias_atras), ex.id)

            dados = DashboardService.dados_professor(prof.id)
            # 10 dias distintos treinados / 30 dias do período, 1 aluno
            assert dados['aderencia']['pct'] == 33.0


class TestSeguranca:
    def test_alunos_atencao_nao_vaza_aluno_de_outro_professor(self, app):
        with app.app_context():
            prof1 = _criar_usuario('ds_sec_1a', tipo_usuario='professor')
            prof2 = _criar_usuario('ds_sec_1b', tipo_usuario='professor')
            aluno2 = _criar_usuario('ds_sec_1_aluno2', nome_completo='Aluno Do Outro')
            _associar(aluno2.id, prof2.id,
                      data_associacao=datetime.now(timezone.utc) - timedelta(days=30))

            dados = DashboardService.dados_professor(prof1.id)
            assert dados['alunos_atencao']['total'] == 0
            assert dados['atividade_recente'] == []
