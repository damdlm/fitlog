"""Cenários de borda do mapa muscular: aluno sem nada, só cardio, carga zero,
virada de semana, treino salvo de madrugada (UTC já no dia seguinte), relógio
adiantado, treino com data futura, nível de força nos extremos, planejado com
ficha finalizada, permissões (vínculo inativo, admin, aluno alheio),
parâmetros estranhos na API e valores inválidos de peso no perfil."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import services.mapa_muscular_service as mms
from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio, RegistroTreino,
                    HistoricoTreino, ExercicioSistema, ExercicioUsuario, Musculo)
from services.billing_service import BillingService
from services.mapa_muscular_service import MapaMuscularService as S

BR = ZoneInfo('America/Sao_Paulo')
_N = [0]


def _u(nome, tipo='aluno', genero=None, peso=None, nome_completo=None):
    u = User(username=nome, email=f'{nome}@t.com', tipo_usuario=tipo, ativo=True,
             nome_completo=nome_completo or nome.title(), genero=genero, peso_kg=peso)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    BillingService.iniciar_trial(u)
    db.session.commit()
    return u


def _ex(alvo=None, sec=(), nome=None, modo='carga'):
    _N[0] += 1
    e = ExercicioSistema(id_original=f'zz{_N[0]}', nome=nome or f'Zz {_N[0]}', alvo=alvo,
                         musculos_secundarios=list(sec), modo_registro=modo)
    db.session.add(e)
    db.session.commit()
    return e


def _ficha(u, dias_atras=40, fim=None):
    n = (db.session.query(db.func.max(VersaoGlobal.numero_versao)).filter_by(user_id=u.id).scalar() or 0) + 1
    v = VersaoGlobal(numero_versao=n, descricao=f'F{n}', divisao='LIVRE', user_id=u.id,
                     data_inicio=mms._hoje() - timedelta(days=dias_atras), data_fim=fim)
    db.session.add(v)
    db.session.flush()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='A')
    db.session.add(t)
    db.session.commit()
    return v, t


def _reg(u, v, t, dias, series, base=None, custom=None, salvo=None):
    d = mms._hoje() - timedelta(days=dias)
    r = RegistroTreino(treino_versao_id=t.id, versao_id=v.id, periodo='x', semana=1, user_id=u.id,
                       exercicio_base_id=base.id if base else None, exercicio_usuario_id=custom.id if custom else None,
                       data_registro=datetime(d.year, d.month, d.day))
    if salvo:
        r.created_at = salvo.astimezone(timezone.utc)
    db.session.add(r)
    db.session.flush()
    for i, s in enumerate(series):
        db.session.add(HistoricoTreino(registro_id=r.id, ordem=i, **s))
    db.session.commit()
    return r


def _relogio(monkeypatch, hoje, agora):
    monkeypatch.setattr(mms, '_hoje', lambda: hoje)
    monkeypatch.setattr(mms, '_agora', lambda: agora)


S10 = {'carga': 50, 'repeticoes': 10}
TER = date(2026, 11, 24)


class TestBordas:
    def test_usuario_sem_nada(self, app):
        with app.app_context():
            u = _u('zz_vazio')
            for semana in (0, -1, -52):
                d = S.calcular(u.id, semana)
                assert all(r['series'] == 0 and r['estado'] == 'sem_treino' and r['retida'] == 0.5
                           and r['exercicios'] == [] and r['ultimo_treino'] is None for r in d['regioes'].values())
                assert d['planejado'] == {'treinos': 0, 'sessoes_semana': None, 'ficha': None}
                assert d['max_series'] == 0
            assert S.niveis_forca(u.id) == {'peso_kg': None, 'genero': 'M', 'levantamentos': []}

    def test_so_cardio_exercicio_sem_musculo_e_alvo_sem_regiao(self, app):
        with app.app_context():
            u = _u('zz_cardio')
            v, t = _ficha(u)
            esteira = _ex('Sistema cardiovascular', modo='tempo')
            pular = _ex('Sistema cardiovascular')  # alvo sem região, modo carga
            sem = ExercicioUsuario(usuario_id=u.id, nome='Sem músculo')
            db.session.add(sem)
            db.session.commit()
            _reg(u, v, t, 0, [{'duracao_segundos': 900}], base=esteira)
            _reg(u, v, t, 0, [S10, S10], base=pular)
            _reg(u, v, t, 0, [S10, S10, S10], custom=sem)
            d = S.calcular(u.id)
            assert sum(r['series'] for r in d['regioes'].values()) == 0
            assert all(r['estado'] == 'sem_treino' and not r['exercicios'] for r in d['regioes'].values())

    def test_carga_zero_e_sem_carga(self, app):
        with app.app_context():
            u = _u('zz_corporal', peso=70)
            v, t = _ficha(u)
            flexao = _ex('Peitorais', nome='Flexão')
            supino = _ex('Peitorais', nome='Supino reto com barra')
            _reg(u, v, t, 0, [{'carga': 0, 'repeticoes': 15}, {'carga': None, 'repeticoes': 12}], base=flexao)
            _reg(u, v, t, 0, [{'carga': 0, 'repeticoes': 5}], base=supino)
            r = S.calcular(u.id)['regioes']['peito']
            assert (r['series'], r['volume']) == (3, 0)
            assert [(e['nome'], e['e1rm']) for e in r['exercicios']] == [('Flexão', None), ('Supino reto com barra', None)]
            assert S.niveis_forca(u.id)['levantamentos'] == []

    def test_virada_de_semana(self, app, monkeypatch):
        # domingo 23h59 ainda é a semana de segunda 16; segunda 00h01 já é a outra
        _relogio(monkeypatch, date(2026, 11, 22), datetime(2026, 11, 22, 23, 59, tzinfo=BR))
        assert S.semana(0) == (date(2026, 11, 16), date(2026, 11, 22))
        _relogio(monkeypatch, date(2026, 11, 23), datetime(2026, 11, 23, 0, 1, tzinfo=BR))
        assert S.semana(0) == (date(2026, 11, 23), date(2026, 11, 29))
        with app.app_context():
            u = _u('zz_virada')
            v, t = _ficha(u)
            e = _ex('Bíceps')
            _reg(u, v, t, 1, [S10] * 4, base=e)  # domingo 22
            assert S.calcular(u.id, 0)['regioes']['biceps']['series'] == 0
            assert S.calcular(u.id, -1)['regioes']['biceps']['series'] == 4

    def test_dois_treinos_no_dia_e_madrugada_utc(self, app, monkeypatch):
        _relogio(monkeypatch, TER, datetime(2026, 11, 24, 23, 50, tzinfo=BR))
        with app.app_context():
            u = _u('zz_madrugada')
            v, t = _ficha(u)
            e = _ex('Peitorais')
            _reg(u, v, t, 0, [S10] * 3, base=e, salvo=datetime(2026, 11, 24, 7, 0, tzinfo=BR))
            # 23h30 em Brasília = 02h30 UTC do dia 25: continua sendo o treino do dia 24
            _reg(u, v, t, 0, [S10] * 3, base=e, salvo=datetime(2026, 11, 24, 23, 30, tzinfo=BR))
            r = S.calcular(u.id)['regioes']['peito']
            # mesmo dia = uma sessão de 6 séries (6/8 = 0,75) na hora mais tarde, 20 min atrás
            assert r['series'] == 6 and r['estado'] == 'fatigado' and r['fadiga'] == 0.744
            assert r['ultimo_treino'] == '2026-11-24T23:30'

    def test_relogio_adiantado_nao_da_hora_negativa(self, app, monkeypatch):
        _relogio(monkeypatch, TER, datetime(2026, 11, 24, 10, 0, tzinfo=BR))
        with app.app_context():
            u = _u('zz_relogio')
            v, t = _ficha(u)
            e = _ex('Peitorais')
            _reg(u, v, t, 0, [S10] * 4, base=e, salvo=datetime(2026, 11, 24, 11, 0, tzinfo=BR))
            r = S.calcular(u.id)['regioes']['peito']
            assert r['fadiga'] == 0.5 and r['retida'] == 1  # sem decaimento negativo

    def test_treino_no_futuro_nao_conta(self, app, monkeypatch):
        _relogio(monkeypatch, TER, datetime(2026, 11, 24, 12, 0, tzinfo=BR))
        with app.app_context():
            u = _u('zz_futuro')
            v, t = _ficha(u)
            e = _ex('Peitorais')
            _reg(u, v, t, -2, [S10] * 3, base=e)  # quinta 26, ainda nesta semana
            r = S.calcular(u.id)['regioes']['peito']
            assert r['series'] == 0 and r['estado'] == 'sem_treino' and r['exercicios'] == []


class TestForcaBordas:
    def test_elite_sem_proximo_e_genero_pelo_nome(self, app):
        with app.app_context():
            u = _u('zz_elite', nome_completo='Maria Souza', peso=40)
            v, t = _ficha(u)
            e = _ex('Peitorais', nome='Supino reto com barra')
            _reg(u, v, t, 1, [{'carga': 60, 'repeticoes': 3}], base=e)
            d = S.niveis_forca(u.id)
            l = d['levantamentos'][0]
            assert d['genero'] == 'F' and l['nivel'] == 'Elite' and 'proximo' not in l and l['nivel_idx'] == 4

    def test_iniciante_e_faltam(self, app):
        with app.app_context():
            u = _u('zz_inic', genero='M', peso=100)
            v, t = _ficha(u)
            e = _ex('Dorsais', nome='Remada curvada com barra')
            _reg(u, v, t, 1, [{'carga': 40, 'repeticoes': 10}], base=e)
            l = S.niveis_forca(u.id)['levantamentos'][0]
            assert (l['nivel'], l['proximo'], l['faltam_kg']) == ('Iniciante', 'Novato', 6.7)

    def test_nome_com_maiuscula_diferente_e_exercicio_personalizado_fora(self, app):
        with app.app_context():
            u = _u('zz_nomes', genero='M', peso=80)
            v, t = _ficha(u)
            e = _ex('Peitorais', nome='SUPINO RETO COM BARRA')
            meu = ExercicioUsuario(usuario_id=u.id, nome='Supino reto com barra')
            db.session.add(meu)
            db.session.commit()
            _reg(u, v, t, 1, [{'carga': 80, 'repeticoes': 1}], base=e)
            _reg(u, v, t, 1, [{'carga': 200, 'repeticoes': 1}], custom=meu)
            ls = S.niveis_forca(u.id)['levantamentos']
            assert len(ls) == 1 and ls[0]['e1rm'] == 80


class TestPlanejadoBordas:
    def test_ficha_finalizada_nao_conta_e_exercicio_repetido_soma(self, app):
        with app.app_context():
            u = _u('zz_plan')
            _ficha(u, fim=mms._hoje() - timedelta(days=1))
            assert S.planejado(u.id)['treinos'] == 0
            v, t = _ficha(u, dias_atras=1)
            t2 = TreinoVersao(versao_id=v.id, codigo='B', nome_treino='B')
            db.session.add(t2)
            db.session.flush()
            m = Musculo.query.filter_by(nome_exibicao='Glúteos').first() or Musculo(nome='gluteos', nome_exibicao='Glúteos')
            db.session.add(m)
            db.session.flush()
            meu = ExercicioUsuario(usuario_id=u.id, nome='Ponte', musculo_id=m.id)
            e = _ex('Quadríceps', ['Glúteos'])
            db.session.add(meu)
            db.session.flush()
            db.session.add_all([VersaoExercicio(treino_versao_id=t.id, exercicio_base_id=e.id, meta_series=4),
                                VersaoExercicio(treino_versao_id=t2.id, exercicio_base_id=e.id),
                                VersaoExercicio(treino_versao_id=t2.id, exercicio_usuario_id=meu.id, meta_series=2)])
            db.session.commit()
            p = S.planejado(u.id)
            assert p['treinos'] == 2 and p['por_regiao'] == {'quadriceps': 7, 'gluteos': 5.5}


def _login(c, n):
    c.post('/auth/login', data={'username': n, 'password': '123456'})


class TestPermissoesEApi:
    def test_professor_desvinculado_admin_e_aluno_alheio(self, client, app):
        with app.app_context():
            prof = _u('zz_prof', 'professor')
            aluno = _u('zz_al')
            vinc = AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=False)
            adm = _u('zz_adm')
            adm.is_admin = True
            _u('zz_outro_al')
            db.session.add(vinc)
            db.session.commit()
            aid = aluno.id
        _login(client, 'zz_prof')
        for url in ('/api/mapa-muscular', '/api/nivel-forca'):
            assert client.get(f'{url}?aluno_id={aid}').status_code == 403
        client.get('/auth/logout')
        _login(client, 'zz_adm')
        assert client.get(f'/api/mapa-muscular?aluno_id={aid}').status_code == 200
        assert client.get(f'/api/nivel-forca?aluno_id={aid}').get_json()['e_o_proprio'] is False
        client.get('/auth/logout')
        _login(client, 'zz_outro_al')
        assert client.get(f'/api/mapa-muscular?aluno_id={aid}').status_code == 403

    def test_parametros_estranhos(self, client, app):
        with app.app_context():
            _u('zz_param')
        _login(client, 'zz_param')
        for q, esperado in (('semana=abc', 0), ('semana=-5', -5), ('semana=7', 0), ('semana=-1000', -52),
                            ('semana=', 0), ('semana=1.5', 0), ('dias=30', 0)):
            r = client.get('/api/mapa-muscular?' + q)
            assert r.status_code == 200 and r.get_json()['semana']['offset'] == esperado, q
        assert client.get('/api/mapa-muscular?aluno_id=999999').status_code == 403

    def test_sem_login(self, client):
        assert client.get('/api/mapa-muscular').status_code in (302, 401)
        assert client.get('/api/nivel-forca').status_code in (302, 401)


class TestTela:
    def test_planejado_sem_ficha_tem_frase_propria(self, client, app):
        with app.app_context():
            u = _u('zz_tela')
            v, t = _ficha(u, fim=mms._hoje())
            _reg(u, v, t, 1, [S10], base=_ex('Peitorais'))
        _login(client, 'zz_tela')
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        assert '<p class="mm-nota-planejado" hidden></p>' in html
        with open('static/js/modules/mapa-muscular.js', encoding='utf-8') as f:
            js = f.read()
        assert 'Não há ficha ativa, então não há séries previstas para mostrar.' in js
        assert "if (plan && !dados.planejado.treinos) return '';" in js


class TestPerfilPeso:
    def test_valores(self, client, app):
        with app.app_context():
            _u('zz_peso', 'professor')
        _login(client, 'zz_peso')
        base = {'email': 'zz_peso@t.com', 'nome_completo': 'Zz'}

        def peso():
            with app.app_context():
                v = User.query.filter_by(username='zz_peso').one().peso_kg
                return None if v is None else float(v)
        for txt, esperado in (('80', 80), (' 72.25 ', 72.2), ('300', 300), ('30', 30)):
            client.post('/auth/profile/update', data={**base, 'peso_kg': txt})
            assert peso() == esperado, txt
        for ruim in ('abc', 'nan', 'inf', '-70', '300.1', '29.9', '1e9'):
            r = client.post('/auth/profile/update', data={**base, 'peso_kg': ruim}, follow_redirects=True)
            assert 'Peso corporal deve estar entre 30 e 300 kg.' in r.get_data(as_text=True), ruim
            assert peso() == 30, ruim
        client.post('/auth/profile/update', data=base)  # form sem o campo: não mexe
        assert peso() == 30


class TestApiPeso:
    def test_salva_valida_e_apaga(self, client, app):
        """Aba Força: o peso corporal é informado ali mesmo e libera os níveis."""
        with app.app_context():
            _u('zz_api_peso')
        _login(client, 'zz_api_peso')

        def peso():
            with app.app_context():
                v = User.query.filter_by(username='zz_api_peso').one().peso_kg
                return None if v is None else float(v)

        r = client.post('/api/peso-corporal', json={'peso_kg': '62,35'})
        assert r.status_code == 200 and r.get_json() == {'peso_kg': 62.4} and peso() == 62.4
        for ruim in ('20', '301', 'abc', -5):
            r = client.post('/api/peso-corporal', json={'peso_kg': ruim})
            assert r.status_code == 400 and 'entre 30 e 300' in r.get_json()['erro'] and peso() == 62.4
        assert client.post('/api/peso-corporal', json={'peso_kg': 80}).get_json() == {'peso_kg': 80.0}
        assert client.post('/api/peso-corporal', json={'peso_kg': ''}).get_json() == {'peso_kg': None} and peso() is None
        client.post('/api/peso-corporal', json={'peso_kg': 70})
        assert client.get('/api/nivel-forca').get_json()['peso_kg'] == 70

    def test_sem_login(self, client):
        assert client.post('/api/peso-corporal', json={'peso_kg': 70}).status_code in (302, 401)


def test_textos_das_abas_no_js():
    """Cada número diz o que é: "9 de 6–14" com "✓ na meta"/"faltam N",
    Recuperação com "Já pode treinar" e "em ~8 h", Força com o 1RM do melhor
    exercício PRINCIPAL e "treinou há X dias"."""
    with open('static/js/modules/mapa-muscular.js', encoding='utf-8') as f:
        js = f.read()
    assert "(f ? ' de ' + f[0] + '–' + f[1] : '')" in js
    assert "'<small class=\"mm-ok\">✓ na meta</small>'" in js and "'faltam ' + Math.max(1, Math.round(f[0] - v))" in js
    assert "Séries ' + feitas + ' · meta" in js
    # treinos/semana: seletor inteiro (o campo numérico ficava vazio com "2,8")
    assert 'Math.round(j.planejado.sessoes_semana || j.planejado.treinos || 3)' in js
    assert 'treinosSemana = Math.max(1, Math.min(14, treinosSemana + passo));' in js
    assert '<b>Já pode treinar:</b>' in js and "em <b>' + duracao(r.horas_restantes) + '</b>" in js
    assert "if (e.papel === 'principal' && e.e1rm && (!ex || e.e1rm > ex.e1rm)) ex = e;" in js
    assert '<b>Sem carga registrada:</b>' in js and "fetch('/api/peso-corporal'" in js
