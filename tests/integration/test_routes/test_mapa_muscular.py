"""Lote 5: mapa muscular -- séries e volume por região, recuperação
estimada, API (com a visão do professor) e o desenho do corpo (MuscleMap, MIT)."""
import json
import re
from datetime import datetime, timedelta

from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, RegistroTreino, HistoricoTreino,
                    ExercicioSistema, ExercicioUsuario, Musculo)
from services.billing_service import BillingService
from services.mapa_muscular_service import MapaMuscularService, REGIOES, regiao_do_musculo, _hoje


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
    v = VersaoGlobal(numero_versao=1, descricao='V', divisao='LIVRE', user_id=u.id, data_inicio=_hoje())
    db.session.add(v)
    db.session.flush()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='A')
    db.session.add(t)
    db.session.commit()
    return v, t


def _treino(u, v, t, dias_atras, series, base=None, custom=None, carga=50, reps=10, cardio=False):
    dia = _hoje() - timedelta(days=dias_atras)
    r = RegistroTreino(treino_versao_id=t.id, versao_id=v.id, periodo='Nov/2026', semana=1, user_id=u.id,
                       exercicio_base_id=base.id if base else None, exercicio_usuario_id=custom.id if custom else None,
                       data_registro=datetime(dia.year, dia.month, dia.day))
    db.session.add(r)
    db.session.flush()
    for i in range(series):
        if cardio:
            db.session.add(HistoricoTreino(registro_id=r.id, duracao_segundos=600, ordem=i))
        else:
            db.session.add(HistoricoTreino(registro_id=r.id, carga=carga, repeticoes=reps, ordem=i))
    db.session.commit()


def _periodo(dias):
    hoje = _hoje()
    return {'dia_inicio': hoje - timedelta(days=dias - 1), 'dia_fim': hoje}


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
    assert sem <= {'Sistema cardiovascular', 'Cardio'}


class TestCalculo:
    def test_principal_conta_inteira_secundario_meia_e_kg_so_no_principal(self, app):
        with app.app_context():
            u = _usuario('mm_calc')
            v, t = _ficha(u)
            supino = _ex('Peitorais', ['Tríceps', 'Ombros'], nome='Supino reto')
            esteira = _ex('Sistema cardiovascular', [], nome='Esteira')
            meu = ExercicioUsuario(usuario_id=u.id, nome='Rosca do Zé',
                                   musculo_id=Musculo.query.filter_by(nome_exibicao='Bíceps').first().id
                                   if Musculo.query.filter_by(nome_exibicao='Bíceps').first() else None)
            if meu.musculo_id is None:
                m = Musculo(nome='biceps', nome_exibicao='Bíceps')
                db.session.add(m)
                db.session.flush()
                meu.musculo_id = m.id
            db.session.add(meu)
            db.session.commit()
            _treino(u, v, t, 2, 3, base=supino, carga=50, reps=10)
            _treino(u, v, t, 2, 2, custom=meu, carga=10, reps=12)
            _treino(u, v, t, 1, 1, base=esteira, cardio=True)
            _treino(u, v, t, 40, 5, base=supino)  # fora dos 30 dias
            r = MapaMuscularService.calcular(u.id, _periodo(30))['regioes']
            assert (r['peito']['series'], r['peito']['volume']) == (3, 1500)
            assert (r['triceps']['series'], r['triceps']['volume']) == (1.5, 0)
            assert r['ombros']['series'] == 1.5
            assert (r['biceps']['series'], r['biceps']['volume']) == (2, 240)
            assert r['peito']['principais'] == ['Supino reto']
            assert sum(x['series'] for x in r.values()) == 8
            tudo = MapaMuscularService.calcular(u.id, None)['regioes']
            assert tudo['peito']['series'] == 8

    def test_recuperacao_estimada(self, app):
        with app.app_context():
            u = _usuario('mm_rec')
            v, t = _ficha(u)
            supino = _ex('Peitorais', ['Tríceps'])
            agach = _ex('Quadríceps', [])
            rosca = _ex('Bíceps', [])
            _treino(u, v, t, 0, 3, base=supino)
            _treino(u, v, t, 3, 4, base=agach)
            _treino(u, v, t, 1, 3, base=rosca)
            r = MapaMuscularService.calcular(u.id, _periodo(30))['regioes']
            assert (r['peito']['status'], r['peito']['faltam'], r['peito']['dias_desde']) == ('recuperando', 3, 0)
            assert r['triceps']['status'] == 'sem_treino'  # 1,5 série efetiva: abaixo do mínimo
            assert (r['quadriceps']['status'], r['quadriceps']['faltam']) == ('recuperado', 0)
            assert (r['biceps']['status'], r['biceps']['faltam']) == ('recuperando', 1)
            assert r['costas']['status'] == 'sem_treino'

    def test_figura_pelo_genero(self, app):
        with app.app_context():
            assert MapaMuscularService.calcular(_usuario('mm_g1', nome='Mariana Alves').id)['genero'] == 'F'
            assert MapaMuscularService.calcular(_usuario('mm_g2', nome='Ana', genero='M').id)['genero'] == 'M'


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
            _treino(aluno, v, t, 1, 3, base=_ex('Dorsais', ['Bíceps']))
            ids = (aluno.id, outro.id)
        _login(client, 'mm_aluno')
        j = client.get('/api/mapa-muscular?dias=7').get_json()
        assert j['regioes']['costas']['series'] == 3 and j['regioes']['biceps']['series'] == 1.5
        assert set(j['regioes']) == set(REGIOES) and j['max_series'] == 3
        assert client.get('/api/mapa-muscular?tudo=1').get_json()['regioes']['costas']['series'] == 3
        assert client.get('/api/mapa-muscular?inicio=2026-13-01&fim=2026-12-01').status_code == 400
        client.get('/auth/logout')
        _login(client, 'mm_prof')
        assert client.get(f'/api/mapa-muscular?dias=30&aluno_id={ids[0]}').get_json()['regioes']['costas']['series'] == 3
        assert client.get(f'/api/mapa-muscular?dias=30&aluno_id={ids[1]}').status_code == 403

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
        assert "comAluno('/api/mapa-muscular?' + periodoAtual.query)" in html


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
