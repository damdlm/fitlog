"""Testes mínimos para a evolução do FitBot: contexto do usuário logado
(nome + treino atual), sempre a partir de current_user (backend),
nunca de um user_id vindo do front-end.
"""
from datetime import date

from flask_login import login_user

from models import (
    db, User, Treino, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioSistema,
)
from services.fitbot_service import FitBotService


def _criar_usuario_com_treino(username, nome_exercicio, grupo_muscular='Peito'):
    """Cria um usuário com uma versão ativa (data_fim=None), 1 treino e
    1 exercício do catálogo — o suficiente para VersaoService.get_ativa()
    e VersaoService.get_treinos()/get_exercicios() resolverem tudo."""
    user = User(username=username, email=f'{username}@teste.com')
    user.set_password('123456')
    db.session.add(user)
    db.session.flush()

    ex_sistema = ExercicioSistema(
        id_original=f'ex-{username}', nome=nome_exercicio, grupo_muscular=grupo_muscular
    )
    db.session.add(ex_sistema)

    treino = Treino(user_id=user.id, codigo='A', nome='Treino A', descricao='Treino A')
    db.session.add(treino)

    versao = VersaoGlobal(
        numero_versao=1, descricao='V1', divisao='ABC',
        data_inicio=date.today(), data_fim=None, user_id=user.id,
    )
    db.session.add(versao)
    db.session.flush()

    treino_versao = TreinoVersao(versao_id=versao.id, treino_id=treino.id, nome_treino='Treino A')
    db.session.add(treino_versao)
    db.session.flush()

    db.session.add(VersaoExercicio(
        treino_versao_id=treino_versao.id, exercicio_base_id=ex_sistema.id, ordem=1
    ))
    db.session.commit()
    return user


def test_contexto_treino_usuario_autenticado(app):
    """O FitBot consegue montar o contexto (nome + treino atual real)
    do usuário logado, usando o mecanismo de login já existente."""
    with app.test_request_context():
        user = _criar_usuario_com_treino('joao_fitbot', 'Supino Reto')
        login_user(user)

        contexto = FitBotService._montar_contexto_treino()

        assert contexto is not None
        assert 'joao_fitbot' in contexto
        assert 'Supino Reto' in contexto
        assert 'Treino A' in contexto


def test_contexto_treino_sem_usuario_autenticado_retorna_none(app):
    """Sem usuário logado (fora de uma sessão autenticada), o FitBot
    não deve tentar acessar dados privados de ninguém."""
    with app.test_request_context():
        contexto = FitBotService._montar_contexto_treino()
        assert contexto is None


def test_contexto_treino_isolamento_entre_usuarios(app):
    """Usuário A só vê o próprio treino; usuário B só vê o próprio —
    nunca dados um do outro."""
    with app.test_request_context():
        user_a = _criar_usuario_com_treino('aluno_a', 'Supino Reto')
        user_b = _criar_usuario_com_treino('aluno_b', 'Leg Press')

        login_user(user_a)
        contexto_a = FitBotService._montar_contexto_treino()
        assert 'Supino Reto' in contexto_a
        assert 'Leg Press' not in contexto_a

    with app.test_request_context():
        login_user(user_b)
        contexto_b = FitBotService._montar_contexto_treino()
        assert 'Leg Press' in contexto_b
        assert 'Supino Reto' not in contexto_b


def test_contexto_treino_usuario_sem_versao_ativa_retorna_none(app):
    """Usuário autenticado mas sem nenhuma versão/treino cadastrado:
    não há dados reais para usar, então o FitBot não inventa nada."""
    with app.test_request_context():
        user = User(username='sem_treino', email='sem_treino@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()

        login_user(user)
        contexto = FitBotService._montar_contexto_treino()
        assert contexto is None


def test_pergunta_geral_nao_e_afetada_quando_nao_ha_contexto(app, monkeypatch):
    """Perguntas gerais (sem contexto de treino) devem continuar
    funcionando exatamente como antes: nenhuma mensagem system extra
    é adicionada quando não há contexto."""
    with app.test_request_context():
        user = User(username='pergunta_geral', email='pg@teste.com')
        user.set_password('123456')
        db.session.add(user)
        db.session.commit()
        login_user(user)

        capturado = {}

        class RespostaFake:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "Hipertrofia é..."}}]}

        def fake_post(url, json=None, headers=None, timeout=None):
            capturado['mensagens'] = json['messages']
            return RespostaFake()

        monkeypatch.setattr('services.fitbot_service.requests.post', fake_post)
        app.config['GROQ_API_KEY'] = 'fake-key-para-teste'

        resultado = FitBotService.get_resposta(mensagem='O que é hipertrofia?')

        assert resultado['ok'] is True
        # Sem treino cadastrado -> só a system instruction original, nada mais
        roles_system = [m for m in capturado['mensagens'] if m['role'] == 'system']
        assert len(roles_system) == 1


def test_endpoint_fitbot_exige_login(client):
    """Sem autenticação, o endpoint do FitBot não deve responder com
    dados privados — o acesso deve ser bloqueado (login_required)."""
    resp = client.post('/fitbot/chat', json={'mensagem': 'oi'})
    assert resp.status_code in (302, 401)