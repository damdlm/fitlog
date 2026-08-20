"""Testes de integração para routes/admin_routes.py:contas -- painel de
cobrança do admin (listagem de alunos/professores com situação e
filtros por tipo/plano/situação)."""
from datetime import datetime, timedelta, timezone

from models import db, User, AlunoProfessor, Plano
from services.billing_service import BillingService


def _criar_usuario(username, tipo_usuario='aluno', is_admin=False):
    user = User(username=username, email=f'{username}@teste.com',
                tipo_usuario=tipo_usuario, is_admin=is_admin)
    user.set_password('SenhaForte123!')
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['sv'] = user.session_version


def _vincular(professor, aluno):
    db.session.add(AlunoProfessor(professor_id=professor.id, aluno_id=aluno.id, ativo=True))


class TestAdminContas:
    def test_exige_login(self, client):
        resp = client.get('/admin/contas')
        assert resp.status_code in (302, 401)

    def test_nao_admin_e_bloqueado(self, client, app):
        with app.app_context():
            aluno = _criar_usuario('contas_nao_admin')
            db.session.commit()
            aluno_ref = User.query.get(aluno.id)

        _login(client, aluno_ref)
        resp = client.get('/admin/contas', follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/contas' not in resp.headers.get('Location', '')

    def test_admin_ve_lista_com_aluno_e_professor(self, client, app):
        with app.app_context():
            admin = _criar_usuario('contas_admin', is_admin=True)
            aluno = _criar_usuario('contas_aluno_trial')
            BillingService.iniciar_trial_aluno(aluno)
            professor = _criar_usuario('contas_professor', tipo_usuario='professor')
            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/contas')
        assert resp.status_code == 200
        assert b'contas_aluno_trial' in resp.data
        assert b'contas_professor' in resp.data

    def test_filtro_inadimplente_so_mostra_quem_deve(self, client, app):
        with app.app_context():
            admin = _criar_usuario('contas_admin_filtro', is_admin=True)

            aluno_ok = _criar_usuario('contas_aluno_ok')
            BillingService.iniciar_trial_aluno(aluno_ok)

            aluno_bloqueado = _criar_usuario('contas_aluno_bloqueado')
            assinatura = BillingService.iniciar_trial_aluno(aluno_bloqueado)
            assinatura.status = 'blocked'

            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/contas?situacao=inadimplente')
        assert resp.status_code == 200
        assert b'contas_aluno_bloqueado' in resp.data
        assert b'contas_aluno_ok' not in resp.data

    def test_filtro_tipo_professor_esconde_alunos(self, client, app):
        with app.app_context():
            admin = _criar_usuario('contas_admin_tipo', is_admin=True)
            aluno = _criar_usuario('contas_aluno_tipo')
            professor = _criar_usuario('contas_professor_tipo', tipo_usuario='professor')
            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/contas?tipo=professor')
        assert resp.status_code == 200
        assert b'contas_professor_tipo' in resp.data
        assert b'contas_aluno_tipo' not in resp.data

    def test_professor_com_11_alunos_aparece_pendente_de_pagamento(self, client, app):
        with app.app_context():
            db.session.add(Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor',
                                  preco_centavos=2990, min_alunos=3, max_alunos=10))
            db.session.add(Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor',
                                  preco_centavos=9990, min_alunos=11, max_alunos=None))
            admin = _criar_usuario('contas_admin_pendente', is_admin=True)
            professor = _criar_usuario('contas_prof_pendente', tipo_usuario='professor')
            for i in range(11):
                aluno = _criar_usuario(f'contas_aluno_pend_{i}')
                _vincular(professor, aluno)
            db.session.commit()
            admin_ref = User.query.get(admin.id)

        _login(client, admin_ref)
        resp = client.get('/admin/contas?situacao=pendente')
        assert resp.status_code == 200
        assert b'contas_prof_pendente' in resp.data
