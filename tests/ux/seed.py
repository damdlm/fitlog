"""Base realista para as simulações de tela (tests/ux).

Catálogo real (data/exercises.json), professor com 3 alunos e uma aluna
com 8 semanas de histórico. Usuários (senha de todos: "senha forte 1"):

    prof   professor "Carla Personal", com ana, bruno e dani
    ana    aluna com ficha "Hipertrofia" (ABC + esteira) e 8 semanas de treinos
    bruno  aluno com a mesma ficha e histórico
    dani   aluna com ficha, sem nenhum treino registrado
    novo   aluno sem professor, sem ficha e sem treinos
    adm    administrador

Não é coletado pelo pytest (nome sem "test_"). Usado por tests/ux/harness.py.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SENHA = 'senha forte 1'


def montar(caminho_db):
    """Cria a base do zero em `caminho_db` (SQLite)."""
    sys.path.insert(0, os.path.join(RAIZ, 'scripts'))
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        from app import create_app
    from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioSistema,
                        ExercicioUsuario, RegistroTreino, HistoricoTreino)
    from tests.conftest import _seed_telas_controladas, _seed_telas_controladas_professor
    from tests.ux.harness import config_para
    from services.billing_service import BillingService
    from services.estatistica_service import EstatisticaService
    from utils.date_utils import data_para_periodo, data_para_semana
    import seed_exercicios_sistema as sx

    if os.path.exists(caminho_db):
        os.remove(caminho_db)
    # Com o arquivo novo, o init_db() do create_app loga "Erro ao verificar
    # admin" (tabela users ainda inexistente para aquela checagem); é
    # inofensivo -- o create_all() logo abaixo monta tudo. Silenciado só aqui.
    import logging
    logging.disable(logging.CRITICAL)
    try:
        app = create_app(config_para(caminho_db))
    finally:
        logging.disable(logging.INFO)
    random.seed(7)
    with app.app_context():
        db.create_all()
        _seed_telas_controladas()
        _seed_telas_controladas_professor()
        with open(sx.JSON_PATH, encoding='utf-8') as f:
            db.session.bulk_insert_mappings(ExercicioSistema, [sx.parse_registro(r) for r in json.load(f)])
        db.session.commit()
        por_nome = {}
        for e in ExercicioSistema.query.all():
            por_nome.setdefault(e.nome.lower(), e)

        def acha(*termos):
            for t in termos:
                for n, e in por_nome.items():
                    if t in n and e.modo_registro == 'carga':
                        return e
            raise SystemExit('exercício não encontrado: ' + str(termos))

        def usuario(username, tipo, nome):
            u = User(username=username, email=f'{username}@exemplo.com', tipo_usuario=tipo, nome_completo=nome)
            u.set_password(SENHA)
            db.session.add(u)
            db.session.flush()
            BillingService.iniciar_trial(u, commit=False)
            return u

        prof = usuario('prof', 'professor', 'Carla Personal')
        ana = usuario('ana', 'aluno', 'Ana Souza')
        bruno = usuario('bruno', 'aluno', 'Bruno Lima')
        dani = usuario('dani', 'aluno', 'Daniela Reis')
        usuario('novo', 'aluno', 'Novo Aluno')
        adm = usuario('adm', 'aluno', 'Admin FitLog')
        adm.is_admin = True
        for a in (ana, bruno, dani):
            db.session.add(AlunoProfessor(aluno_id=a.id, professor_id=prof.id))
        db.session.flush()

        fichas = {
            'A': ('Peito e tríceps', [acha('supino reto com barra'), acha('crucifixo com halteres', 'crucifixo'),
                                      acha('supino inclinado'), acha('tríceps na polia', 'extensão de tríceps'),
                                      acha('mergulho no banco')]),
            'B': ('Costas e bíceps', [acha('puxada frontal', 'puxada'), acha('remada curvada', 'remada'),
                                      acha('remada baixa', 'remada sentada'), acha('rosca direta'), acha('rosca martelo')]),
            'C': ('Pernas', [acha('agachamento com barra', 'agachamento'), acha('leg press'),
                             acha('extensão de perna na máquina'),
                             acha('rosca de perna deitado', 'rosca de perna', 'flexão de perna', 'flexora'),
                             acha('elevação de panturrilha em pé', 'elevação de panturrilha')]),
        }
        esteira = ExercicioSistema.query.filter_by(id_original='9001').first()
        hoje = EstatisticaService.hoje_brasil()
        for u in (ana, bruno, dani):
            v1 = VersaoGlobal(numero_versao=1, descricao='Adaptação', divisao='ABC', user_id=u.id,
                              data_inicio=hoje - timedelta(days=120), data_fim=hoje - timedelta(days=57))
            v2 = VersaoGlobal(numero_versao=2, descricao='Hipertrofia', divisao='ABC', user_id=u.id,
                              data_inicio=hoje - timedelta(days=56))
            db.session.add_all([v1, v2])
            db.session.flush()
            for v in (v1, v2):
                for cod, (nome, exs) in fichas.items():
                    t = TreinoVersao(versao_id=v.id, codigo=cod, nome_treino=nome, descricao_treino=nome)
                    db.session.add(t)
                    db.session.flush()
                    for i, e in enumerate(exs):
                        db.session.add(VersaoExercicio(treino_versao_id=t.id, exercicio_base_id=e.id, ordem=i))
                    if cod == 'C' and esteira:
                        db.session.add(VersaoExercicio(treino_versao_id=t.id, exercicio_base_id=esteira.id, ordem=9))
            db.session.flush()
            if u is dani:
                continue
            treinos = TreinoVersao.query.filter_by(versao_id=v2.id).order_by(TreinoVersao.codigo).all()
            dia, k = hoje - timedelta(days=55), 0
            while dia < hoje:
                if dia.weekday() in (0, 2, 4) or (dia.weekday() == 5 and random.random() < .4):
                    t = treinos[k % 3]
                    k += 1
                    semana = (dia - v2.data_inicio).days // 7 + 1
                    for ve in VersaoExercicio.query.filter_by(treino_versao_id=t.id).all():
                        r = RegistroTreino(treino_versao_id=t.id, versao_id=v2.id, user_id=u.id,
                                           periodo=data_para_periodo(dia), semana=data_para_semana(dia),
                                           exercicio_base_id=ve.exercicio_base_id,
                                           data_registro=datetime.combine(dia, datetime.min.time()) + timedelta(hours=18))
                        db.session.add(r)
                        db.session.flush()
                        if esteira and ve.exercicio_base_id == esteira.id:
                            db.session.add(HistoricoTreino(registro_id=r.id, duracao_segundos=random.choice([900, 1200]),
                                                           distancia_km=random.choice([None, 2.5]), intensidade='moderada'))
                            continue
                        base = 20 + (ve.ordem * 7) + semana * 1.5
                        for _ in range(3):
                            db.session.add(HistoricoTreino(registro_id=r.id, carga=round(base / 2.5) * 2.5,
                                                           repeticoes=random.choice([8, 10, 10, 12])))
                dia += timedelta(days=1)
        db.session.add(ExercicioUsuario(usuario_id=ana.id, nome='Abdominal na bola'))
        db.session.commit()
    return caminho_db
