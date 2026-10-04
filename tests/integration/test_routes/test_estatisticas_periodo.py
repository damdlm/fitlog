"""Filtro global de período da página de Estatísticas (dias=N, inicio/fim, tudo=1).

Cada endpoint que alimenta a página tem que respeitar o mesmo período; sem
nenhum parâmetro, o comportamento antigo (30 dias / 60 dias) continua valendo.
"""
from datetime import datetime, timedelta, timezone

from models import db, User, TreinoVersao, VersaoGlobal, RegistroTreino, HistoricoTreino, Musculo, ExercicioUsuario
from services.billing_service import BillingService


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def _montar(app, username):
    with app.app_context():
        u = User(username=username, email=f'{username}@t.com', tipo_usuario='aluno')
        u.set_password('x' * 12)
        db.session.add(u)
        db.session.flush()
        BillingService.iniciar_trial(u)
        db.session.commit()
        m = Musculo(nome=f'm_{username}', nome_exibicao='M')
        db.session.add(m)
        db.session.commit()
        ex = ExercicioUsuario(usuario_id=u.id, nome='Supino', musculo_id=m.id)
        db.session.add(ex)
        db.session.commit()
        versao = VersaoGlobal(numero_versao=1, descricao='v1', divisao='AB',
                              data_inicio=datetime.now(timezone.utc).date(), user_id=u.id)
        db.session.add(versao)
        db.session.commit()
        treinos = {}
        for i, cod in enumerate('AB'):
            t = TreinoVersao(versao_id=versao.id, codigo=cod, nome_treino=cod, descricao_treino='d', ordem=i)
            db.session.add(t)
            db.session.commit()
            treinos[cod] = t.id
        return u.id, versao.id, ex.id, treinos


def _registrar(app, uid, vid, ex, tid, dias_atras, carga, reps, series=1):
    with app.app_context():
        r = RegistroTreino(
            treino_versao_id=tid, versao_id=vid, periodo='Julho/2026', semana=1,
            exercicio_usuario_id=ex,
            data_registro=datetime.now(timezone.utc) - timedelta(days=dias_atras), user_id=uid)
        db.session.add(r)
        db.session.commit()
        for i in range(series):
            db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=i))
        db.session.commit()


def _logar(client, app, uid):
    with app.app_context():
        user = db.session.get(User, uid)
    _login(client, user)


def test_kpis_respeitam_dias_e_tudo(client, app):
    uid, vid, ex, t = _montar(app, 'per_kpis')
    _registrar(app, uid, vid, ex, t['A'], 3, 10, 10)     # 100, dentro de 7 dias
    _registrar(app, uid, vid, ex, t['B'], 20, 20, 10)    # 200, só nos 30 dias
    _registrar(app, uid, vid, ex, t['A'], 80, 30, 10)    # 300, só no "tudo"
    _logar(client, app, uid)

    k7 = client.get('/api/kpis?dias=7').get_json()
    assert (k7['treinos_realizados'], k7['volume_total']) == (1, 100.0)

    k30 = client.get('/api/kpis?dias=30').get_json()
    assert (k30['treinos_realizados'], k30['volume_total']) == (2, 300.0)

    padrao = client.get('/api/kpis').get_json()   # sem parâmetro = 30 dias, como sempre
    assert padrao['volume_total'] == 300.0

    tudo = client.get('/api/kpis?tudo=1').get_json()
    assert (tudo['treinos_realizados'], tudo['volume_total']) == (3, 600.0)
    # sem período anterior pra comparar
    assert tudo['volume_variacao'] is None and tudo['treinos_variacao'] is None


def test_kpis_intervalo_personalizado_e_validacao(client, app):
    uid, vid, ex, t = _montar(app, 'per_kpis_custom')
    _registrar(app, uid, vid, ex, t['A'], 3, 10, 10)
    _registrar(app, uid, vid, ex, t['B'], 20, 20, 10)
    _logar(client, app, uid)

    hoje = datetime.now(timezone.utc).date()
    ini = (hoje - timedelta(days=22)).isoformat()
    fim = (hoje - timedelta(days=15)).isoformat()
    k = client.get(f'/api/kpis?inicio={ini}&fim={fim}').get_json()
    assert (k['treinos_realizados'], k['volume_total']) == (1, 200.0)

    # o último dia do intervalo entra inteiro
    d = (hoje - timedelta(days=3)).isoformat()
    assert client.get(f'/api/kpis?inicio={d}&fim={d}').get_json()['treinos_realizados'] == 1

    assert client.get('/api/kpis?inicio=2026-13-40&fim=2026-01-01').status_code == 400
    assert client.get(f'/api/kpis?inicio={fim}&fim={ini}').status_code == 400   # início depois do fim


def test_progresso_agregado_respeita_periodo(client, app):
    uid, vid, ex, t = _montar(app, 'per_prog')
    _registrar(app, uid, vid, ex, t['A'], 2, 10, 10)     # 100
    _registrar(app, uid, vid, ex, t['A'], 50, 20, 10)    # 200 (fora dos 30 dias)
    _logar(client, app, uid)

    assert sum(client.get('/api/progresso?modo=semana').get_json()['volumes']) == 100.0   # padrão: 30 dias
    assert sum(client.get('/api/progresso?modo=semana&dias=7').get_json()['volumes']) == 100.0
    assert sum(client.get('/api/progresso?modo=semana&dias=90').get_json()['volumes']) == 300.0
    assert sum(client.get('/api/progresso?modo=semana&tudo=1').get_json()['volumes']) == 300.0
    assert client.get('/api/progresso?modo=treino&tudo=1').get_json()['volumes'] == [200.0, 100.0]

    hoje = datetime.now(timezone.utc).date()
    ini = (hoje - timedelta(days=60)).isoformat()
    fim = (hoje - timedelta(days=40)).isoformat()
    d = client.get(f'/api/progresso?modo=semana&inicio={ini}&fim={fim}').get_json()
    assert sum(d['volumes']) == 200.0

    # período que termina no futuro não cria semanas vazias à frente de hoje
    futuro = (hoje + timedelta(days=60)).isoformat()
    d = client.get(f'/api/progresso?modo=semana&inicio={(hoje - timedelta(days=7)).isoformat()}&fim={futuro}').get_json()
    assert sum(d['volumes']) == 100.0 and len(d['semanas']) <= 2


def test_recordes_do_periodo_precisam_superar_o_que_veio_antes(client, app):
    uid, vid, ex, t = _montar(app, 'per_pr')
    _registrar(app, uid, vid, ex, t['A'], 40, 100, 10)   # PR antigo (1RM ~133)
    _registrar(app, uid, vid, ex, t['A'], 3, 80, 10)     # série recente MENOR: não é recorde
    _logar(client, app, uid)

    padrao = client.get('/api/recordes-pessoais').get_json()   # janela antiga de 60 dias
    assert [r['carga'] for r in padrao] == [100.0]
    assert client.get('/api/recordes-pessoais?dias=7').get_json() == []
    assert [r['carga'] for r in client.get('/api/recordes-pessoais?tudo=1').get_json()] == [100.0]

    _registrar(app, uid, vid, ex, t['A'], 2, 120, 10)    # agora sim, bateu o recorde
    assert [r['carga'] for r in client.get('/api/recordes-pessoais?dias=7').get_json()] == [120.0]
    assert [r['carga'] for r in client.get('/api/recordes-pessoais?dias=30').get_json()] == [120.0]


def test_atividade_geral_respeita_periodo(client, app):
    uid, vid, ex, t = _montar(app, 'per_atv')
    _registrar(app, uid, vid, ex, t['A'], 3, 10, 10, series=2)
    _registrar(app, uid, vid, ex, t['B'], 20, 10, 10, series=3)
    _registrar(app, uid, vid, ex, t['A'], 80, 10, 10, series=4)
    _logar(client, app, uid)

    assert client.get('/api/atividade-geral').get_json()['total_series'] == 5          # padrão: 30 dias
    assert client.get('/api/atividade-geral?dias=7').get_json()['total_series'] == 2
    assert client.get('/api/atividade-geral?tudo=1').get_json()['total_series'] == 9
    hoje = datetime.now(timezone.utc).date()
    ini = (hoje - timedelta(days=25)).isoformat()
    fim = (hoje - timedelta(days=15)).isoformat()
    assert client.get(f'/api/atividade-geral?inicio={ini}&fim={fim}').get_json()['total_series'] == 3


def test_progressao_forca_respeita_periodo(client, app):
    uid, vid, ex, t = _montar(app, 'per_rm')
    _registrar(app, uid, vid, ex, t['A'], 40, 100, 10)
    _registrar(app, uid, vid, ex, t['A'], 20, 105, 10)
    _registrar(app, uid, vid, ex, t['A'], 3, 110, 10)
    _logar(client, app, uid)

    chave = f'usuario_{ex}'
    assert len(client.get(f'/api/progressao-forca?exercicio={chave}').get_json()['valores']) == 3
    assert len(client.get(f'/api/progressao-forca?exercicio={chave}&dias=30').get_json()['valores']) == 2
    assert len(client.get(f'/api/progressao-forca?exercicio={chave}&dias=7').get_json()['valores']) == 1
    assert len(client.get(f'/api/progressao-forca?exercicio={chave}&tudo=1').get_json()['valores']) == 3