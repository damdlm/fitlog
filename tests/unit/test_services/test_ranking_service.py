"""Testes para RankingService (tela "Melhores Alunos").

Cobrem as regras de negócio combinadas: janela de 30 dias, critério de
desempate (dias treinados > tempo total > nome), descarte de sessões
> 2h30 (só o tempo, não o dia), maior sessão do dia (não soma), exclusão
de professores/inativos/opt-out, e ignorar datas futuras.
"""
from datetime import date, datetime, timedelta, timezone

from models import db, User, Musculo, ExercicioUsuario, Treino, VersaoGlobal, RegistroTreino, HistoricoTreino
from services.ranking_service import RankingService, DURACAO_MAXIMA_VALIDA_SEGUNDOS
from services.base_service import CacheService


def _criar_aluno(email, tipo_usuario='aluno', ativo=True, aparecer_no_ranking=True, nome_completo=None):
    user = User(username=email.split('@')[0], email=email, tipo_usuario=tipo_usuario,
                ativo=ativo, aparecer_no_ranking=aparecer_no_ranking, nome_completo=nome_completo)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _criar_treino_e_versao(user):
    treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='')
    db.session.add(treino)
    versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='ABC',
                           data_inicio=date.today(), user_id=user.id)
    db.session.add(versao)
    db.session.flush()
    return treino, versao


def _criar_sessao(user, treino, versao, dia, tempo_treino_segundos, num_exercicios=1):
    """Cria uma 'sessão' de treino nesse dia: N registros (exercícios),
    cada um com uma série cujo tempo_treino é o mesmo (é assim que o
    cronômetro do topo é gravado de verdade, ver HistoricoTreino)."""
    musculo = Musculo.query.filter_by(nome='geral').first()
    if not musculo:
        musculo = Musculo(nome='geral', nome_exibicao='Geral')
        db.session.add(musculo)
        db.session.flush()

    for i in range(num_exercicios):
        ex = ExercicioUsuario(usuario_id=user.id, nome=f'Exercicio {dia}-{i}', musculo_id=musculo.id)
        db.session.add(ex)
        db.session.flush()

        registro = RegistroTreino(
            treino_id=treino.id, versao_id=versao.id, periodo='manha', semana=1,
            user_id=user.id, exercicio_usuario_id=ex.id,
            data_registro=datetime.combine(dia, datetime.min.time()).replace(hour=10),
        )
        db.session.add(registro)
        db.session.flush()
        db.session.add(HistoricoTreino(registro_id=registro.id, carga=50, repeticoes=10,
                                        tempo_treino=tempo_treino_segundos))
    db.session.commit()


def _limpar_cache():
    CacheService.invalidate("ranking:geral:30d")


def test_dias_treinados_e_desempate_por_tempo(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()

        aluno_a = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino_a, versao_a = _criar_treino_e_versao(aluno_a)
        _criar_sessao(aluno_a, treino_a, versao_a, hoje, 3600)
        _criar_sessao(aluno_a, treino_a, versao_a, hoje - timedelta(days=1), 3600)

        aluno_b = _criar_aluno('b@t.com', nome_completo='Aluno B')
        treino_b, versao_b = _criar_treino_e_versao(aluno_b)
        _criar_sessao(aluno_b, treino_b, versao_b, hoje, 3600)
        _criar_sessao(aluno_b, treino_b, versao_b, hoje - timedelta(days=1), 3600)
        _criar_sessao(aluno_b, treino_b, versao_b, hoje - timedelta(days=2), 3600)

        ranking = RankingService.calcular_ranking_geral()
        nomes_em_ordem = [r['nome'] for r in ranking]

        assert nomes_em_ordem[0] == 'Aluno B'  # 3 dias > 2 dias
        assert nomes_em_ordem[1] == 'Aluno A'
        assert ranking[0]['posicao'] == 1
        assert ranking[1]['posicao'] == 2


def test_empate_em_dias_desempata_por_tempo_total(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()

        aluno_a = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino_a, versao_a = _criar_treino_e_versao(aluno_a)
        _criar_sessao(aluno_a, treino_a, versao_a, hoje, 1800)  # 30 min

        aluno_b = _criar_aluno('b@t.com', nome_completo='Aluno B')
        treino_b, versao_b = _criar_treino_e_versao(aluno_b)
        _criar_sessao(aluno_b, treino_b, versao_b, hoje, 3600)  # 1h -- mesmo 1 dia, mas mais tempo

        ranking = RankingService.calcular_ranking_geral()
        assert ranking[0]['nome'] == 'Aluno B'
        assert ranking[0]['dias_treinados'] == ranking[1]['dias_treinados'] == 1
        assert ranking[0]['tempo_total_segundos'] > ranking[1]['tempo_total_segundos']


def test_sessao_acima_de_2h30_descarta_tempo_mas_conta_o_dia(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()

        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)
        # Sessão claramente esquecida ligada: 5 horas
        _criar_sessao(aluno, treino, versao, hoje, 5 * 3600)

        ranking = RankingService.calcular_ranking_geral()
        assert len(ranking) == 1
        assert ranking[0]['dias_treinados'] == 1  # o dia CONTA
        assert ranking[0]['tempo_total_segundos'] == 0  # mas o tempo é descartado


def test_sessao_exatamente_no_limite_e_valida(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, hoje, DURACAO_MAXIMA_VALIDA_SEGUNDOS)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking[0]['tempo_total_segundos'] == DURACAO_MAXIMA_VALIDA_SEGUNDOS


def test_multiplas_sessoes_no_mesmo_dia_usa_a_maior_nao_soma(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)

        # Duas "sessões" no mesmo dia (tempo_treino diferentes) -- só a
        # maior deve contar, não a soma das duas.
        musculo = Musculo(nome='geral2', nome_exibicao='Geral2')
        db.session.add(musculo)
        db.session.flush()

        for tempo in (1200, 3000):  # 20min, 50min
            ex = ExercicioUsuario(usuario_id=aluno.id, nome=f'Ex {tempo}', musculo_id=musculo.id)
            db.session.add(ex)
            db.session.flush()
            registro = RegistroTreino(
                treino_id=treino.id, versao_id=versao.id, periodo='manha', semana=1,
                user_id=aluno.id, exercicio_usuario_id=ex.id,
                data_registro=datetime.combine(hoje, datetime.min.time()).replace(hour=10),
            )
            db.session.add(registro)
            db.session.flush()
            db.session.add(HistoricoTreino(registro_id=registro.id, carga=50, repeticoes=10, tempo_treino=tempo))
        db.session.commit()

        ranking = RankingService.calcular_ranking_geral()
        assert ranking[0]['dias_treinados'] == 1
        assert ranking[0]['tempo_total_segundos'] == 3000  # a maior, não 1200+3000


def test_data_no_futuro_e_ignorada(app, db):
    with app.app_context():
        _limpar_cache()
        amanha = date.today() + timedelta(days=1)
        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, amanha, 1800)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking == []


def test_registro_de_hoje_com_horario_conta_normalmente(app, db):
    """Regressão: o limite superior da janela precisa ser exclusivo
    (amanhã), não 'data <= hoje' comparado direto -- senão registros de
    HOJE com qualquer horário depois da meia-noite ficariam de fora."""
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, hoje, 1800)  # criado às 10h

        ranking = RankingService.calcular_ranking_geral()
        assert len(ranking) == 1
        assert ranking[0]['dias_treinados'] == 1


def test_fora_da_janela_de_30_dias_nao_conta(app, db):
    with app.app_context():
        _limpar_cache()
        muito_antigo = date.today() - timedelta(days=45)
        aluno = _criar_aluno('a@t.com', nome_completo='Aluno A')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, muito_antigo, 1800)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking == []


def test_professor_nao_aparece_no_ranking(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        professor = _criar_aluno('p@t.com', tipo_usuario='professor', nome_completo='Professor X')
        treino, versao = _criar_treino_e_versao(professor)
        _criar_sessao(professor, treino, versao, hoje, 1800)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking == []


def test_aluno_inativo_nao_aparece_no_ranking(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        aluno = _criar_aluno('a@t.com', ativo=False, nome_completo='Aluno Inativo')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, hoje, 1800)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking == []


def test_opt_out_nao_aparece_no_ranking(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        aluno = _criar_aluno('a@t.com', aparecer_no_ranking=False, nome_completo='Aluno Discreto')
        treino, versao = _criar_treino_e_versao(aluno)
        _criar_sessao(aluno, treino, versao, hoje, 1800)

        ranking = RankingService.calcular_ranking_geral()
        assert ranking == []


def test_top_n_limita_resultado(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        for i in range(7):
            aluno = _criar_aluno(f'a{i}@t.com', nome_completo=f'Aluno {i}')
            treino, versao = _criar_treino_e_versao(aluno)
            _criar_sessao(aluno, treino, versao, hoje - timedelta(days=i), 1800)

        top5 = RankingService.top_n(5)
        assert len(top5) == 5


def test_posicao_do_usuario_fora_do_top(app, db):
    with app.app_context():
        _limpar_cache()
        hoje = date.today()
        alunos = []
        for i in range(7):
            aluno = _criar_aluno(f'a{i}@t.com', nome_completo=f'Aluno {i}')
            treino, versao = _criar_treino_e_versao(aluno)
            # Aluno 0 treina mais dias (fica em 1o), os demais decrescem
            for d in range(7 - i):
                _criar_sessao(aluno, treino, versao, hoje - timedelta(days=d), 1800)
            alunos.append(aluno)

        top5 = RankingService.top_n(5)
        assert len(top5) == 5

        ultimo_aluno = alunos[-1]  # o que treinou menos dias -- deve estar em 7o
        posicao = RankingService.posicao_do_usuario(ultimo_aluno.id)
        assert posicao is not None
        assert posicao['posicao'] == 7


def test_usuario_sem_nenhum_registro_nao_tem_posicao(app, db):
    with app.app_context():
        _limpar_cache()
        aluno = _criar_aluno('semtreino@t.com', nome_completo='Sem Treino')
        posicao = RankingService.posicao_do_usuario(aluno.id)
        assert posicao is None


def test_ranking_vazio_quando_nao_ha_alunos(app, db):
    with app.app_context():
        _limpar_cache()
        assert RankingService.calcular_ranking_geral() == []
