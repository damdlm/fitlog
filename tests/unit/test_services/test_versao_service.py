"""
Testes unitários para services/versao_service.py.

Foca nas funções ainda usadas pelo fluxo atual (versão sem divisão fixa,
"Cadastrar Treinos"): get_ativa/get_ativa_por_data, e
get_exercicios_agrupados_por_treino (criada para resolver N+1 em
professor/aluno/FitBot).

Os fluxos antigos de divisão fixa (ABC/ABCD/ABCDE) -- VersaoService.create/
clone/delete/finalizar/adicionar_treino/remover_treino, e o antigo
TreinoService de CRUD -- foram removidos junto com as telas que os usavam
("Nova Versão", "Meus Treinos"); versões e treinos agora só se criam via
VersaoService.create_livre/adicionar_treino_livre.
"""
from datetime import date, datetime, timedelta, timezone

from models import (
    db, User, Musculo, VersaoGlobal, TreinoVersao,
    VersaoExercicio, ExercicioUsuario, ExercicioSistema, AlunoProfessor,
    Notificacao,
)
from services.versao_service import VersaoService


def _criar_usuario(username, tipo_usuario='aluno'):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, nome_completo=username.title())
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _criar_musculo(user_id):
    musculo = Musculo(nome=f'm_{user_id}', nome_exibicao='Peito')
    db.session.add(musculo)
    db.session.commit()
    return musculo


def _criar_versao(user_id, descricao='Bloco', data_inicio=date(2026, 1, 1), data_fim=None,
                   validade_meses=None, alerta_expiracao_enviado_em=None):
    versao = VersaoGlobal(numero_versao=1, descricao=descricao, divisao='ABC',
                           data_inicio=data_inicio, data_fim=data_fim, user_id=user_id,
                           validade_meses=validade_meses,
                           alerta_expiracao_enviado_em=alerta_expiracao_enviado_em)
    db.session.add(versao)
    db.session.commit()
    return versao


def _vincular(aluno_id, professor_id):
    db.session.add(AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=True))
    db.session.commit()


def _criar_treino(versao_id, codigo='A', nome='Treino A', descricao='d'):
    treino = TreinoVersao(versao_id=versao_id, codigo=codigo, nome_treino=nome, descricao_treino=descricao)
    db.session.add(treino)
    db.session.commit()
    return treino


class TestGetAtiva:
    def test_sem_versao_retorna_none(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_1')
            assert VersaoService.get_ativa(user_id=u.id) is None

    def test_versao_sem_data_fim_e_ativa(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_2')
            _criar_versao(u.id, descricao='Bloco', data_inicio=date(2026, 1, 1))
            ativa = VersaoService.get_ativa_por_data(date(2026, 6, 1), user_id=u.id)
            assert ativa is not None
            assert ativa.descricao == 'Bloco'

    def test_versao_finalizada_nao_e_ativa_apos_data_fim(self, app):
        with app.app_context():
            u = _criar_usuario('v_ativa_3')
            _criar_versao(u.id, descricao='Bloco', data_inicio=date(2026, 1, 1), data_fim=date(2026, 2, 1))

            ativa_depois = VersaoService.get_ativa_por_data(date(2026, 3, 1), user_id=u.id)
            assert ativa_depois is None

            ativa_durante = VersaoService.get_ativa_por_data(date(2026, 1, 15), user_id=u.id)
            assert ativa_durante is not None


class TestGetExerciciosAgrupadosPorTreino:
    """Funcao criada para resolver N+1 (rodada de otimizacao)."""

    def test_sem_versao_ativa_retorna_dict_vazio(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_1')
            assert VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id) == {}

    def test_agrupa_exercicios_de_usuario_e_de_sistema_por_treino(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_2')
            musc = _criar_musculo(u.id)
            versao = _criar_versao(u.id)

            treino_a = _criar_treino(versao.id, codigo='A', nome='Treino A')
            treino_b = _criar_treino(versao.id, codigo='B', nome='Treino B')

            ex_custom = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=musc.id)
            db.session.add(ex_custom)
            db.session.commit()

            ex_sistema = ExercicioSistema(id_original='ag-001', nome='Agachamento', grupo_muscular='Pernas')
            db.session.add(ex_sistema)
            db.session.commit()

            db.session.add(VersaoExercicio(treino_versao_id=treino_a.id, exercicio_usuario_id=ex_custom.id, ordem=1))
            db.session.add(VersaoExercicio(treino_versao_id=treino_b.id, exercicio_base_id=ex_sistema.id, ordem=1))
            db.session.commit()

            agrupado = VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id)

            assert set(agrupado.keys()) == {treino_a.id, treino_b.id}
            assert len(agrupado[treino_a.id]) == 1
            assert agrupado[treino_a.id][0].nome == 'Supino'
            assert agrupado[treino_a.id][0].tipo == 'usuario'
            assert len(agrupado[treino_b.id]) == 1
            assert agrupado[treino_b.id][0].nome == 'Agachamento'
            assert agrupado[treino_b.id][0].tipo == 'base'

    def test_treino_sem_exercicios_aparece_com_lista_vazia(self, app):
        with app.app_context():
            u = _criar_usuario('v_agrupado_3')
            versao = _criar_versao(u.id)
            treino_a = _criar_treino(versao.id, codigo='A', nome='Treino A')

            agrupado = VersaoService.get_exercicios_agrupados_por_treino(user_id=u.id)
            assert agrupado[treino_a.id] == []

    def test_nao_mistura_exercicios_de_usuarios_diferentes(self, app):
        """Isolamento: exercicios de A nao devem aparecer no agrupamento de B."""
        with app.app_context():
            a = _criar_usuario('v_agrupado_iso_a')
            b = _criar_usuario('v_agrupado_iso_b')
            musc_a = _criar_musculo(a.id)
            musc_b = _criar_musculo(b.id)

            versao_a = _criar_versao(a.id, descricao='Bloco A')
            versao_b = _criar_versao(b.id, descricao='Bloco B')
            treino_a = _criar_treino(versao_a.id, codigo='A', nome='Treino A')
            treino_b = _criar_treino(versao_b.id, codigo='A', nome='Treino A')

            ex_a = ExercicioUsuario(usuario_id=a.id, nome='Exercicio de A', musculo_id=musc_a.id)
            ex_b = ExercicioUsuario(usuario_id=b.id, nome='Exercicio de B', musculo_id=musc_b.id)
            db.session.add_all([ex_a, ex_b])
            db.session.commit()

            db.session.add(VersaoExercicio(treino_versao_id=treino_a.id, exercicio_usuario_id=ex_a.id, ordem=1))
            db.session.add(VersaoExercicio(treino_versao_id=treino_b.id, exercicio_usuario_id=ex_b.id, ordem=1))
            db.session.commit()

            agrupado_a = VersaoService.get_exercicios_agrupados_por_treino(user_id=a.id)
            nomes_a = [ex.nome for lista in agrupado_a.values() for ex in lista]

            assert 'Exercicio de A' in nomes_a
            assert 'Exercicio de B' not in nomes_a


class TestValidadeMesesEExpiracao:
    """VersaoGlobal.data_expiracao/dias_para_expirar e
    VersaoService._validar_validade_meses (feature de validade em meses
    + alerta de expiração)."""

    def test_sem_validade_meses_nao_tem_data_expiracao(self, app):
        with app.app_context():
            u = _criar_usuario('val_1')
            versao = _criar_versao(u.id, data_inicio=date(2026, 1, 1))
            assert versao.data_expiracao is None
            assert versao.dias_para_expirar is None

    def test_data_expiracao_soma_meses_a_partir_de_data_inicio(self, app):
        with app.app_context():
            u = _criar_usuario('val_2')
            versao = _criar_versao(u.id, data_inicio=date(2026, 1, 15), validade_meses=3)
            assert versao.data_expiracao == date(2026, 4, 15)

    def test_dias_para_expirar_conta_a_partir_de_hoje(self, app):
        with app.app_context():
            hoje = date.today()
            u_futura = _criar_usuario('val_3_futura')
            u_vencida = _criar_usuario('val_3_vencida')

            versao_futura = _criar_versao(u_futura.id, data_inicio=hoje, validade_meses=1)
            assert versao_futura.dias_para_expirar > 0

            versao_vencida = _criar_versao(u_vencida.id, descricao='Vencida',
                                            data_inicio=hoje - timedelta(days=400), validade_meses=1)
            assert versao_vencida.dias_para_expirar < 0

    def test_validar_validade_meses_aceita_vazio_como_sem_prazo(self, app):
        with app.app_context():
            assert VersaoService._validar_validade_meses(None) is None
            assert VersaoService._validar_validade_meses('') is None

    def test_validar_validade_meses_converte_string_numerica(self, app):
        with app.app_context():
            assert VersaoService._validar_validade_meses('6') == 6

    def test_validar_validade_meses_rejeita_valor_fora_do_limite(self, app):
        with app.app_context():
            import pytest
            with pytest.raises(ValueError):
                VersaoService._validar_validade_meses(0)
            with pytest.raises(ValueError):
                VersaoService._validar_validade_meses(999)

    def test_validar_validade_meses_rejeita_nao_numerico(self, app):
        with app.app_context():
            import pytest
            with pytest.raises(ValueError):
                VersaoService._validar_validade_meses('abc')

    def test_create_livre_grava_validade_meses(self, app):
        with app.app_context():
            u = _criar_usuario('val_create')
            versao = VersaoService.create_livre('Bloco com prazo', user_id=u.id, validade_meses=2)
            assert versao.validade_meses == 2
            assert versao.data_expiracao is not None

    def test_clonar_versao_carrega_validade_da_origem(self, app):
        with app.app_context():
            u = _criar_usuario('val_clone')
            origem = _criar_versao(u.id, data_inicio=date(2026, 1, 1),
                                    data_fim=date(2026, 2, 1), validade_meses=4)
            clone = VersaoService.clonar_versao(origem.id, user_id=u.id)
            assert clone.validade_meses == 4

    def test_clonar_versao_de_professor_aceita_validade_explicita(self, app):
        with app.app_context():
            prof = _criar_usuario('val_prof', tipo_usuario='professor')
            aluno = _criar_usuario('val_aluno')
            origem = _criar_versao(prof.id, data_inicio=date(2026, 1, 1), validade_meses=6)
            nova = VersaoService.clonar_versao_de_professor(
                origem.id, professor_id=prof.id, aluno_id=aluno.id, validade_meses=1
            )
            assert nova.validade_meses == 1

    def test_clonar_versao_de_professor_mantem_validade_da_origem_por_padrao(self, app):
        with app.app_context():
            prof = _criar_usuario('val_prof2', tipo_usuario='professor')
            aluno = _criar_usuario('val_aluno2')
            origem = _criar_versao(prof.id, data_inicio=date(2026, 1, 1), validade_meses=6)
            nova = VersaoService.clonar_versao_de_professor(
                origem.id, professor_id=prof.id, aluno_id=aluno.id
            )
            assert nova.validade_meses == 6


class TestAlertarExpiracoes:
    """VersaoService.alertar_expiracoes -- comando CLI
    'versoes-alertar-expiracao'."""

    def test_sem_versoes_com_validade_nao_alerta_nada(self, app):
        with app.app_context():
            u = _criar_usuario('alerta_1')
            _criar_versao(u.id, data_inicio=date.today())
            assert VersaoService.alertar_expiracoes() == 0

    def test_versao_longe_do_vencimento_nao_alerta(self, app):
        with app.app_context():
            u = _criar_usuario('alerta_2')
            _criar_versao(u.id, data_inicio=date.today(), validade_meses=12)
            assert VersaoService.alertar_expiracoes() == 0
            assert Notificacao.query.count() == 0

    def test_versao_dentro_da_janela_notifica_dono_sem_professor(self, app):
        with app.app_context():
            u = _criar_usuario('alerta_3')
            # data_inicio há 355 dias + validade de 12 meses cai dentro
            # da janela de 15 dias antes de vencer, sem precisar
            # depender do calendário exato.
            versao = _criar_versao(u.id, data_inicio=date.today() - timedelta(days=355),
                                    validade_meses=12)
            total = VersaoService.alertar_expiracoes()
            assert total == 1

            db.session.refresh(versao)
            assert versao.alerta_expiracao_enviado_em is not None

            notifs = Notificacao.query.filter_by(destinatario_id=u.id).all()
            assert len(notifs) == 1
            assert notifs[0].tipo == 'versao_expirando'

    def test_versao_dentro_da_janela_notifica_tambem_o_professor_vinculado(self, app):
        with app.app_context():
            prof = _criar_usuario('alerta_prof', tipo_usuario='professor')
            aluno = _criar_usuario('alerta_aluno')
            _vincular(aluno.id, prof.id)
            _criar_versao(aluno.id, data_inicio=date.today() - timedelta(days=355), validade_meses=12)

            total = VersaoService.alertar_expiracoes()
            assert total == 1

            notif_aluno = Notificacao.query.filter_by(destinatario_id=aluno.id).first()
            notif_prof = Notificacao.query.filter_by(destinatario_id=prof.id).first()
            assert notif_aluno is not None
            assert notif_prof is not None
            assert notif_prof.tipo == 'versao_expirando'

    def test_versao_ja_alertada_nao_alerta_de_novo(self, app):
        with app.app_context():
            u = _criar_usuario('alerta_4')
            _criar_versao(
                u.id, data_inicio=date.today() - timedelta(days=355), validade_meses=12,
                alerta_expiracao_enviado_em=datetime.now(timezone.utc),
            )
            assert VersaoService.alertar_expiracoes() == 0
            assert Notificacao.query.count() == 0

    def test_versao_finalizada_nao_alerta(self, app):
        with app.app_context():
            u = _criar_usuario('alerta_5')
            _criar_versao(
                u.id, data_inicio=date.today() - timedelta(days=355), validade_meses=12,
                data_fim=date.today(),
            )
            assert VersaoService.alertar_expiracoes() == 0

    def test_versao_ja_vencida_ainda_alerta_uma_vez(self, app):
        """Cobre o caso do cron não ter rodado no dia certo: mesmo já
        tendo passado do prazo, ainda deve gerar UM alerta."""
        with app.app_context():
            u = _criar_usuario('alerta_6')
            _criar_versao(u.id, data_inicio=date.today() - timedelta(days=800), validade_meses=12)
            assert VersaoService.alertar_expiracoes() == 1
