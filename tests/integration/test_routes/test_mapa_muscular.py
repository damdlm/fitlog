"""Mapa muscular: séries por semana, fadiga, força retida, níveis de força,
API (com a visão do professor), peso no perfil e o desenho do corpo
(MuscleMap, MIT). Relógio fixo (RELOGIO) onde o resultado depende da hora."""
import json
import re
from datetime import datetime, timedelta

from datetime import date, timezone
from zoneinfo import ZoneInfo

import services.mapa_muscular_service as mms
from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio, RegistroTreino,
                    HistoricoTreino, ExercicioSistema, ExercicioUsuario, Musculo)
from services.billing_service import BillingService
from services.mapa_muscular_service import MapaMuscularService, REGIOES, regiao_do_musculo, e1rm, forca_retida

BR = ZoneInfo('America/Sao_Paulo')


def _usuario(username, tipo='aluno', nome=None, genero=None):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo, ativo=True,
             nome_completo=nome or username.title(), genero=genero)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    BillingService.iniciar_trial(u)
    db.session.commit()
    return u


_N = [0]


def _ex(alvo, secundarios=(), nome=None):
    _N[0] += 1
    ex = ExercicioSistema(id_original=f'mm_{_N[0]}', nome=nome or f'Ex {_N[0]}', alvo=alvo,
                          grupo_muscular=(secundarios[0] if secundarios else alvo),
                          musculos_secundarios=list(secundarios))
    db.session.add(ex)
    db.session.commit()
    return ex


def _ficha(u):
    v = VersaoGlobal(numero_versao=1, descricao='V', divisao='LIVRE', user_id=u.id, data_inicio=mms._hoje())
    db.session.add(v)
    db.session.flush()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='A')
    db.session.add(t)
    db.session.commit()
    return v, t


def _treino(u, v, t, dias_atras, series, base=None, custom=None, carga=50, reps=10, cardio=False, salvo_em=None):
    dia = mms._hoje() - timedelta(days=dias_atras)  # respeita o relógio fixado no teste
    r = RegistroTreino(treino_versao_id=t.id, versao_id=v.id, periodo='Nov/2026', semana=1, user_id=u.id,
                       exercicio_base_id=base.id if base else None, exercicio_usuario_id=custom.id if custom else None,
                       data_registro=datetime(dia.year, dia.month, dia.day))
    if salvo_em is not None:
        r.created_at = salvo_em.astimezone(timezone.utc)
    db.session.add(r)
    db.session.flush()
    for i in range(series):
        if cardio:
            db.session.add(HistoricoTreino(registro_id=r.id, duracao_segundos=600, ordem=i))
        else:
            db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=i))
    db.session.commit()


HOJE = date(2026, 11, 24)  # terça
AGORA = datetime(2026, 11, 24, 21, 0, tzinfo=BR)


def _relogio(monkeypatch):
    monkeypatch.setattr(mms, '_hoje', lambda: HOJE)
    monkeypatch.setattr(mms, '_agora', lambda: AGORA)


def test_mapeamento_de_nomes():
    assert regiao_do_musculo('Peitorais') == 'peito'
    assert regiao_do_musculo('  TRÍCEPS ') == 'triceps'
    assert regiao_do_musculo('Isquiotibiais') == 'isquiotibiais'
    assert regiao_do_musculo('Sistema cardiovascular') is None


def test_todo_musculo_do_catalogo_tem_regiao():
    with open('data/exercises.json', encoding='utf-8') as f:
        catalogo = json.load(f)
    nomes = {e.get('target') for e in catalogo} | {m for e in catalogo for m in (e.get('secondary_muscles') or [])}
    sem = {n for n in nomes if n and regiao_do_musculo(n) is None}
    # pescoço é parte neutra do desenho (como no openGym); cardio não é músculo
    assert sem <= {'Sistema cardiovascular', 'Cardio', 'Esternocleidomastoideo'}


def test_forca_retida():
    assert forca_retida(0) == 1 and forca_retida(14) == 1
    assert round(forca_retida(20), 3) == 0.862
    assert forca_retida(42) == 0.5 and forca_retida(400) == 0.5


class TestCalculo:
    def test_semana_de_segunda_a_domingo(self, monkeypatch):
        _relogio(monkeypatch)
        assert MapaMuscularService.semana(0) == (date(2026, 11, 23), date(2026, 11, 29))
        assert MapaMuscularService.semana(-1) == (date(2026, 11, 16), date(2026, 11, 22))

    def test_series_da_semana_principal_inteira_secundario_meia(self, app, monkeypatch):
        _relogio(monkeypatch)
        with app.app_context():
            u = _usuario('mm_calc')
            v, t = _ficha(u)
            supino = _ex('Peitorais', ['Tríceps', 'Ombros'], nome='Supino reto')
            esteira = _ex('Sistema cardiovascular', [], nome='Esteira')
            m = Musculo.query.filter_by(nome_exibicao='Bíceps').first()
            if not m:
                m = Musculo(nome='biceps', nome_exibicao='Bíceps')
                db.session.add(m)
                db.session.flush()
            meu = ExercicioUsuario(usuario_id=u.id, nome='Rosca do Zé', musculo_id=m.id)
            db.session.add(meu)
            db.session.commit()
            _treino(u, v, t, 1, 3, base=supino, carga=50, reps=10)     # segunda 23: esta semana
            _treino(u, v, t, 1, 2, custom=meu, carga=10, reps=12)
            _treino(u, v, t, 0, 1, base=esteira, cardio=True)
            _treino(u, v, t, 3, 5, base=supino)                        # sábado 21: semana anterior
            r = MapaMuscularService.calcular(u.id, 0)['regioes']
            assert (r['peito']['series'], r['peito']['volume']) == (3, 1500)
            assert (r['triceps']['series'], r['triceps']['volume']) == (1.5, 0)
            assert (r['biceps']['series'], r['biceps']['volume']) == (2, 240)
            assert r['peito']['principais'] == ['Supino reto'] and r['peito']['faixa'] == (10, 20)
            assert sum(x['series'] for x in r.values()) == 8
            anterior = MapaMuscularService.calcular(u.id, -1)
            assert anterior['regioes']['peito']['series'] == 5
            assert anterior['semana'] == {'offset': -1, 'inicio': '2026-11-16', 'fim': '2026-11-22'}

    def test_fadiga_decai_pela_meia_vida(self, app, monkeypatch):
        _relogio(monkeypatch)
        with app.app_context():
            u = _usuario('mm_fad')
            v, t = _ficha(u)
            supino = _ex('Peitorais', ['Tríceps'])
            agach = _ex('Quadríceps', [])
            _treino(u, v, t, 0, 3, base=supino, salvo_em=datetime(2026, 11, 24, 16, 0, tzinfo=BR))
            # lançado hoje, treino de domingo: vale 18h daquele dia; 16 séries, limitado a 12
            _treino(u, v, t, 2, 16, base=agach, salvo_em=datetime(2026, 11, 24, 9, 0, tzinfo=BR))
            r = MapaMuscularService.calcular(u.id)['regioes']
            # peito: 3/8 = 0,375 × 0,5^(5/30) = 0,334 -> recuperando; volta a 0,25 em 30·log2(0,334/0,25)
            assert (r['peito']['estado'], r['peito']['fadiga'], r['peito']['horas_restantes']) == ('recuperando', 0.334, 12.5)
            assert r['peito']['pronto_em'] == '2026-11-25T09:32'  # 12,54 h depois das 21h
            # tríceps: 1,5/8 × 0,5^(5/24) = 0,162 -> pronto
            assert (r['triceps']['estado'], r['triceps']['horas_restantes']) == ('pronto', 0)
            # quadríceps: 12/8 × 0,5^(51/48) = 0,718 -> fatigado
            assert (r['quadriceps']['estado'], r['quadriceps']['fadiga']) == ('fatigado', 0.718)
            assert r['costas']['estado'] == 'sem_treino'

    def test_forca_retida_e_exercicios_por_regiao(self, app, monkeypatch):
        _relogio(monkeypatch)
        with app.app_context():
            u = _usuario('mm_ret')
            v, t = _ficha(u)
            agach = _ex('Glúteos', ['Quadríceps'], nome='Agachamento')
            extensora = _ex('Quadríceps', [], nome='Extensora')
            remada = _ex('Dorsais', [], nome='Remada')
            _treino(u, v, t, 3, 2, base=agach, carga=100, reps=5)
            _treino(u, v, t, 5, 3, base=extensora, carga=40, reps=12)
            _treino(u, v, t, 30, 3, base=remada, carga=60, reps=8)
            r = MapaMuscularService.calcular(u.id)['regioes']
            assert r['quadriceps']['retida'] == 1 and r['lombar']['retida'] == 0.5
            assert r['lombar']['ultimo_treino'] is None
            assert r['costas']['retida'] == round(0.5 ** ((30 - 14 + 3 / 24) / 28), 3)
            ex = r['quadriceps']['exercicios']
            assert [(e['nome'], e['papel']) for e in ex] == [('Extensora', 'principal'), ('Agachamento', 'secundario')]
            assert ex[1]['e1rm'] == 116.7 and ex[1]['retida'] == 1

    def test_planejado_pela_ficha(self, app):
        with app.app_context():
            u = _usuario('mm_plan')
            v, t = _ficha(u)
            t2 = TreinoVersao(versao_id=v.id, codigo='B', nome_treino='B')
            db.session.add(t2)
            db.session.flush()
            supino = _ex('Peitorais', ['Tríceps'])
            rosca = _ex('Bíceps', [])
            esteira = _ex('Sistema cardiovascular', [])
            esteira.modo_registro = 'tempo'
            db.session.add_all([VersaoExercicio(treino_versao_id=t.id, exercicio_base_id=supino.id, meta_series=4),
                                VersaoExercicio(treino_versao_id=t2.id, exercicio_base_id=rosca.id),
                                VersaoExercicio(treino_versao_id=t2.id, exercicio_base_id=esteira.id, meta_series=1)])
            db.session.commit()
            for dias in (1, 3, 8, 10):
                _treino(u, v, t, dias, 1, base=supino)
            d = MapaMuscularService.calcular(u.id)
            assert d['planejado'] == {'treinos': 2, 'sessoes_semana': 1.0, 'ficha': 'V'}
            r = d['regioes']
            assert (r['peito']['planejado_ciclo'], r['triceps']['planejado_ciclo'], r['biceps']['planejado_ciclo']) == (4, 2, 3)
            assert r['costas']['planejado_ciclo'] == 0

    def test_figura_pelo_genero(self, app):
        with app.app_context():
            assert MapaMuscularService.calcular(_usuario('mm_g1', nome='Mariana Alves').id)['genero'] == 'F'
            assert MapaMuscularService.calcular(_usuario('mm_g2', nome='Ana', genero='M').id)['genero'] == 'M'


class TestForca:
    def test_e1rm(self):
        assert e1rm(100, 1) == 100
        assert round(e1rm(100, 5), 2) == 116.67

    def test_nivel_pelo_peso(self, app):
        with app.app_context():
            u = _usuario('mm_forca', nome='Carlos', genero='M')
            v, t = _ficha(u)
            supino = ExercicioSistema(id_original='mmf1', nome='Supino reto com barra', alvo='Peitorais')
            agach = ExercicioSistema(id_original='mmf2', nome='Agachamento completo com barra', alvo='Quadríceps')
            outro = ExercicioSistema(id_original='mmf3', nome='Supino com halteres', alvo='Peitorais')
            db.session.add_all([supino, agach, outro])
            db.session.commit()
            _treino(u, v, t, 2, 1, base=supino, carga=100, reps=1)
            _treino(u, v, t, 3, 1, base=supino, carga=110, reps=15)  # acima de 12 reps: fora
            _treino(u, v, t, 4, 1, base=agach, carga=100, reps=5)
            _treino(u, v, t, 200, 1, base=agach, carga=200, reps=1)  # mais de 6 meses: fora
            _treino(u, v, t, 1, 1, base=outro, carga=60, reps=8)
            sem_peso = MapaMuscularService.niveis_forca(u.id)
            assert sem_peso['peso_kg'] is None and 'nivel' not in sem_peso['levantamentos'][0]
            u.peso_kg = 80
            db.session.commit()
            d = MapaMuscularService.niveis_forca(u.id)
            por = {x['chave']: x for x in d['levantamentos']}
            assert set(por) == {'supino', 'agachamento'}
            assert (por['supino']['e1rm'], por['supino']['razao'], por['supino']['nivel']) == (100, 1.25, 'Intermediário')
            assert (por['supino']['proximo'], por['supino']['faltam_kg']) == ('Avançado', 20)
            assert (por['agachamento']['nivel'], por['agachamento']['faltam_kg']) == ('Novato', 3.3)


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestApiETela:
    def test_api_do_proprio_aluno_e_do_professor(self, client, app):
        with app.app_context():
            prof = _usuario('mm_prof', 'professor')
            aluno = _usuario('mm_aluno')
            outro = _usuario('mm_outro')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            db.session.commit()
            v, t = _ficha(aluno)
            # dia 0 = hoje: sempre dentro da semana atual
            _treino(aluno, v, t, 0, 3, base=_ex('Dorsais', ['Bíceps']))
            ids = (aluno.id, outro.id)
        _login(client, 'mm_aluno')
        j = client.get('/api/mapa-muscular').get_json()
        assert j['regioes']['costas']['series'] == 3 and j['regioes']['biceps']['series'] == 1.5
        assert set(j['regioes']) == set(REGIOES) and j['semana']['offset'] == 0
        assert client.get('/api/mapa-muscular?semana=-1').get_json()['regioes']['costas']['series'] == 0
        assert client.get('/api/mapa-muscular?semana=3').get_json()['semana']['offset'] == 0
        assert client.get('/api/mapa-muscular?semana=-99').get_json()['semana']['offset'] == -52
        assert client.get('/api/mapa-muscular?semana=abc').get_json()['semana']['offset'] == 0
        client.get('/auth/logout')
        _login(client, 'mm_prof')
        assert client.get(f'/api/mapa-muscular?aluno_id={ids[0]}').get_json()['regioes']['costas']['series'] == 3
        assert client.get(f'/api/mapa-muscular?aluno_id={ids[1]}').status_code == 403

    def test_api_nivel_forca(self, client, app):
        with app.app_context():
            prof = _usuario('mmf_prof', 'professor')
            aluno = _usuario('mmf_aluno')
            outro = _usuario('mmf_outro')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
            db.session.commit()
            ids = (aluno.id, outro.id)
        _login(client, 'mmf_aluno')
        j = client.get('/api/nivel-forca').get_json()
        assert j['e_o_proprio'] is True and j['levantamentos'] == []
        client.get('/auth/logout')
        _login(client, 'mmf_prof')
        assert client.get(f'/api/nivel-forca?aluno_id={ids[0]}').get_json()['e_o_proprio'] is False
        assert client.get(f'/api/nivel-forca?aluno_id={ids[1]}').status_code == 403

    def test_peso_no_perfil(self, client, app):
        with app.app_context():
            _usuario('mm_peso')
        _login(client, 'mm_peso')
        assert 'name="peso_kg"' in client.get('/auth/profile').get_data(as_text=True)
        base = {'email': 'mm_peso@teste.com', 'nome_completo': 'Mm Peso'}
        client.post('/auth/profile/update', data={**base, 'peso_kg': '72,5'})
        with app.app_context():
            assert float(User.query.filter_by(username='mm_peso').one().peso_kg) == 72.5
        r = client.post('/auth/profile/update', data={**base, 'peso_kg': '20'}, follow_redirects=True)
        assert 'Peso corporal deve estar entre 30 e 300 kg.' in r.get_data(as_text=True)
        client.post('/auth/profile/update', data={**base, 'peso_kg': ''})
        with app.app_context():
            assert User.query.filter_by(username='mm_peso').one().peso_kg is None

    def test_secao_na_tela_de_progresso(self, client, app):
        with app.app_context():
            u = _usuario('mm_tela')
            v, t = _ficha(u)
            _treino(u, v, t, 1, 3, base=_ex('Peitorais'))
        _login(client, 'mm_tela')
        html = client.get('/aluno/estatisticas').get_data(as_text=True)
        assert 'id="mapaMuscular"' in html and 'href="#mapaMuscular"' in html
        assert 'vendor/musclemap/corpo-fitlog.js' in html and 'js/modules/mapa-muscular.js' in html
        assert 'MuscleMap' in html and 'licença MIT' in html
        assert "FitLogMapaMuscular.carregar(comAluno('/api/mapa-muscular'), comAluno('/api/nivel-forca'))" in html
        assert 'data-aba="fadiga"' in html and 'data-aba="forca"' in html and 'data-sub="planejado"' in html
        assert 'class="mm-semana-ant"' in html and 'class="mm-semana-prox"' in html


def test_desenho_do_corpo_e_licenca():
    with open('static/vendor/musclemap/corpo-fitlog.js', encoding='utf-8') as f:
        js = f.read()
    assert 'Copyright (c) 2026 Melih Colpan' in js and 'Permission is hereby granted' in js
    with open('static/vendor/musclemap/LICENSE', encoding='utf-8') as f:
        assert 'MIT License' in f.read()
    corpo = json.loads(re.search(r'window\.FitLogCorpo = (\{.*\});', js, re.S).group(1))
    assert set(corpo) == {'M', 'F'}
    for genero in corpo.values():
        assert set(genero) == {'frente', 'costas'}
        usadas = set()
        for vista in genero.values():
            assert len(vista['viewBox']) == 4
            for p in vista['partes']:
                assert p['r'] is None or p['r'] in REGIOES
                assert p['d'] and all(d[:1] in 'Mm' for d in p['d'])
                usadas.add(p['r'])
        assert set(REGIOES) <= usadas
    # cabelo e pescoço voltam como partes neutras (desenho original do MuscleMap)
    assert '"r":null' in js and 'pescoco' not in js


def test_migracao_peso(app):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    spec = importlib.util.spec_from_file_location('mig_peso', 'migrations/versions/e1f3a7b9c2d4_peso_corporal.py')
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == 'd9e2f6a3b8c5'
    with app.app_context():
        def rodar(f):
            with db.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    f()

        def colunas():
            return {c['name'] for c in inspect(db.engine).get_columns('users')}
        assert 'peso_kg' in colunas()
        rodar(mig.downgrade)
        assert 'peso_kg' not in colunas()
        rodar(mig.upgrade)
        assert 'peso_kg' in colunas()
