"""Testes de integração para a rota professor.nova_versao_aluno --
faltava um jeito do professor criar a PRIMEIRA versão de um aluno que
ainda não tem nenhuma (todas as outras rotas de versão exigem uma
versao_id já existente)."""
from datetime import datetime, timezone

from models import db, User, AlunoProfessor, VersaoGlobal


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False, ativo=True):
    u = User(username=username, email=f'{username}@teste.com',
              tipo_usuario=tipo_usuario, is_admin=is_admin, ativo=ativo,
              nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _associar(aluno_id, professor_id, ativo=True):
    assoc = AlunoProfessor(aluno_id=aluno_id, professor_id=professor_id, ativo=ativo,
                            data_associacao=datetime.now(timezone.utc))
    db.session.add(assoc)
    db.session.commit()
    return assoc


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestNovaVersaoAluno:
    def test_professor_cria_primeira_versao_de_aluno_sem_versoes(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_ok_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_ok_1a')
            _associar(aluno.id, prof.id)
            username, aluno_id = prof.username, aluno.id
            assert VersaoGlobal.query.filter_by(user_id=aluno_id).count() == 0

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/nova',
                            data={'descricao': 'Versão Inicial'}, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Versão criada'.encode() in resp.data

        with app.app_context():
            versoes = VersaoGlobal.query.filter_by(user_id=aluno_id).all()
            assert len(versoes) == 1
            assert versoes[0].descricao == 'Versão Inicial'
            assert versoes[0].numero_versao == 1
            assert versoes[0].data_fim is None

    def test_formulario_aparece_para_get(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_get_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_get_1a')
            _associar(aluno.id, prof.id)
            username, aluno_id, nome = prof.username, aluno.id, aluno.nome_completo

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/nova')
        assert resp.status_code == 200
        assert nome.encode() in resp.data

    def test_descricao_vazia_nao_cria_versao(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_vazio_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_vazio_1a')
            _associar(aluno.id, prof.id)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/nova',
                            data={'descricao': ''}, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno_id).count() == 0

    def test_bloqueia_se_aluno_ja_tem_versao_ativa(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_ativa_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_ativa_1a')
            _associar(aluno.id, prof.id)
            v = VersaoGlobal(numero_versao=1, descricao='Já ativa', divisao='LIVRE',
                              data_inicio=datetime.now(timezone.utc).date(), user_id=aluno.id)
            db.session.add(v)
            db.session.commit()
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versao/nova', follow_redirects=True)
        assert resp.status_code == 200
        assert 'já tem uma versão ativa'.encode() in resp.data

        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno_id).count() == 1

    def test_professor_nao_cria_versao_para_aluno_de_outro_professor(self, client, app):
        with app.app_context():
            prof1 = _criar_usuario('nv_idor_1a', tipo_usuario='professor')
            prof2 = _criar_usuario('nv_idor_1b', tipo_usuario='professor')
            aluno = _criar_usuario('nv_idor_aluno')
            _associar(aluno.id, prof2.id)
            username, aluno_id = prof1.username, aluno.id

        _login(client, username)
        resp = client.post(f'/professor/aluno/{aluno_id}/versao/nova',
                            data={'descricao': 'Invasão'}, follow_redirects=True)
        assert resp.status_code == 200
        assert 'não tem permissão'.encode() in resp.data
        with app.app_context():
            assert VersaoGlobal.query.filter_by(user_id=aluno_id).count() == 0

    def test_link_criar_versao_aparece_na_lista_quando_aluno_sem_versoes(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_link_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_link_1a')
            _associar(aluno.id, prof.id)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/versoes')
        assert resp.status_code == 200
        assert f'/professor/aluno/{aluno_id}/versao/nova'.encode() in resp.data

    def test_link_criar_versao_aparece_na_pagina_do_aluno_sem_versao_ativa(self, client, app):
        with app.app_context():
            prof = _criar_usuario('nv_pg_1p', tipo_usuario='professor')
            aluno = _criar_usuario('nv_pg_1a')
            _associar(aluno.id, prof.id)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}')
        assert resp.status_code == 200
        assert f'/professor/aluno/{aluno_id}/versao/nova'.encode() in resp.data
