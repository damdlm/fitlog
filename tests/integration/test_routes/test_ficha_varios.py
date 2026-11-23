"""Lote 4: mesma ficha para vários alunos -- substituir agora, quando a
atual vencer (cron), como sugestão (aceitar/recusar), resultado por aluno
e alerta "sugestão sem resposta" no painel."""
from datetime import datetime, timedelta, timezone

from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioSistema,
                    ExercicioUsuario, FichaEnviada, Notificacao)
from services.base_service import CacheService
from services.ficha_lote_service import FichaLoteService
from tests.integration.test_routes.test_lote6c import _semear_catalogo
from utils.format_utils import data_atual


def _usuario(username, tipo='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo, ativo=True,
             nome_completo=username.replace('_', ' ').title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _vincular(aluno, prof):
    db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id, ativo=True))
    db.session.commit()


_N = [0]


def _base(nome='Supino'):
    _N[0] += 1
    ex = ExercicioSistema(id_original=f'fv_{_N[0]}', nome=nome, grupo_muscular='Peito')
    db.session.add(ex)
    db.session.commit()
    return ex


def _ficha(dono, descricao='Hipertrofia', validade=None, dias_atras=0, exercicios=()):
    ultima = db.session.query(db.func.max(VersaoGlobal.numero_versao)).filter_by(user_id=dono.id).scalar() or 0
    v = VersaoGlobal(numero_versao=ultima + 1, descricao=descricao, divisao='LIVRE', user_id=dono.id,
                     data_inicio=data_atual() - timedelta(days=dias_atras), validade_meses=validade)
    db.session.add(v)
    db.session.flush()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='Peito', ordem=0)
    db.session.add(t)
    db.session.flush()
    for i, ex in enumerate(exercicios or [_base()]):
        campo = 'exercicio_usuario_id' if isinstance(ex, ExercicioUsuario) else 'exercicio_base_id'
        db.session.add(VersaoExercicio(treino_versao_id=t.id, ordem=i, observacao='pegada aberta',
                                       meta_series=4, meta_reps_min=8, meta_reps_max=12, **{campo: ex.id}))
    db.session.commit()
    return v


def _ativa(aluno):
    return VersaoGlobal.query.filter_by(user_id=aluno.id, data_fim=None).first()


def _cenario(prefixo, n_alunos=2):
    prof = _usuario(f'{prefixo}_prof', 'professor')
    alunos = []
    for i in range(n_alunos):
        a = _usuario(f'{prefixo}_aluno{i}')
        _vincular(a, prof)
        alunos.append(a)
    return prof, alunos


class TestSubstituirAgora:
    def test_encerra_a_atual_e_copia_treinos_metas_e_observacoes(self, app):
        with app.app_context():
            prof, (a1, a2) = _cenario('agora')
            origem = _ficha(prof, 'Força 4x', validade=3)
            antiga = _ficha(a1, 'Antiga')
            res = FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id, a2.id], 'agora')
            assert [r['status'] for r in res] == ['aplicada', 'aplicada']
            assert res[0]['texto'] == 'já é a ficha ativa (v2)'
            assert db.session.get(VersaoGlobal, antiga.id).data_fim == data_atual()
            nova = _ativa(a1)
            assert nova.descricao == 'Força 4x' and nova.validade_meses == 3 and nova.data_inicio == data_atual()
            ve = VersaoExercicio.query.join(TreinoVersao).filter(TreinoVersao.versao_id == nova.id).one()
            assert (ve.meta_series, ve.meta_reps_min, ve.meta_reps_max, ve.observacao) == (4, 8, 12, 'pegada aberta')
            assert _ativa(a2).numero_versao == 1
            assert Notificacao.query.filter_by(destinatario_id=a2.id, titulo='Você tem uma nova ficha').count() == 1

    def test_exercicio_do_professor_vira_copia_do_aluno(self, app):
        with app.app_context():
            prof, (a1,) = _cenario('exprof', 1)
            meu = ExercicioUsuario(usuario_id=prof.id, nome='Remada do Prof')
            db.session.add(meu)
            db.session.commit()
            origem = _ficha(prof, exercicios=[meu])
            FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id], 'agora')
            ve = VersaoExercicio.query.join(TreinoVersao).filter(TreinoVersao.versao_id == _ativa(a1).id).one()
            copia = db.session.get(ExercicioUsuario, ve.exercicio_usuario_id)
            assert copia.usuario_id == a1.id and copia.nome == 'Remada do Prof'
            assert copia.copiado_de_exercicio_id == meu.id

    def test_ficha_de_um_aluno_para_os_outros(self, app):
        with app.app_context():
            prof, (a1, a2) = _cenario('deal', 2)
            proprio = ExercicioUsuario(usuario_id=a1.id, nome='Exercício da Ana')
            db.session.add(proprio)
            db.session.commit()
            origem = _ficha(a1, 'Ficha da Ana', exercicios=[proprio, _base()])
            res = FichaLoteService.aplicar(prof, f'a:{origem.id}', [a1.id, a2.id], 'agora')
            assert res[0] == {'aluno_id': a1.id, 'nome': a1.nome_completo, 'status': 'ignorado',
                              'texto': 'esta já é a ficha atual dele'}
            assert res[1]['status'] == 'aplicada'
            nomes = {ve.exercicio_usuario.nome for ve in VersaoExercicio.query.join(TreinoVersao)
                     .filter(TreinoVersao.versao_id == _ativa(a2).id) if ve.exercicio_usuario_id}
            assert nomes == {'Exercício da Ana'}
            assert ExercicioUsuario.query.filter_by(usuario_id=a2.id, nome='Exercício da Ana').count() == 1

    def test_ficha_pronta_com_validade_definida(self, app):
        with app.app_context():
            _semear_catalogo()
            prof, (a1,) = _cenario('pronta', 1)
            _ficha(a1, 'Antiga')
            res = FichaLoteService.aplicar(prof, 'm:full-body', [a1.id], 'agora', validade='2')
            assert res[0]['status'] == 'aplicada'
            nova = _ativa(a1)
            assert nova.descricao == 'Full body' and nova.validade_meses == 2
            assert VersaoGlobal.query.filter_by(user_id=a1.id).count() == 2


class TestQuandoVencer:
    def test_agenda_ignora_e_aplica_conforme_a_ficha_atual(self, app):
        with app.app_context():
            prof, (com_prazo, sem_prazo, vencida, sem_ficha) = _cenario('venc', 4)
            origem = _ficha(prof, 'Próxima')
            atual = _ficha(com_prazo, 'Atual', validade=1, dias_atras=10)
            _ficha(sem_prazo, 'Sem prazo')
            _ficha(vencida, 'Velha', validade=1, dias_atras=40)
            res = FichaLoteService.aplicar(prof, f'p:{origem.id}',
                                           [com_prazo.id, sem_prazo.id, vencida.id, sem_ficha.id], 'vencer')
            por = {r['aluno_id']: r for r in res}
            assert por[com_prazo.id]['status'] == 'agendada'
            assert atual.data_expiracao.strftime('%d/%m/%Y') in por[com_prazo.id]['texto']
            assert por[sem_prazo.id]['status'] == 'ignorado'
            assert 'não tem data de vencimento' in por[sem_prazo.id]['texto']
            assert por[vencida.id]['status'] == 'aplicada'
            assert 'a ficha atual já tinha vencido' in por[vencida.id]['texto']
            assert por[sem_ficha.id]['status'] == 'aplicada'
            assert 'não tinha ficha ativa' in por[sem_ficha.id]['texto']
            assert _ativa(com_prazo).id == atual.id
            envio = FichaEnviada.query.filter_by(aluno_id=com_prazo.id).one()
            assert (envio.status, envio.versao_alvo_id) == ('pendente', atual.id)

    def test_cron_aplica_quando_vence_e_cancela_se_o_aluno_trocou(self, app):
        with app.app_context():
            prof, (a1, a2, a3) = _cenario('cron', 3)
            origem = _ficha(prof, 'Próxima', validade=2)
            atual1 = _ficha(a1, 'Atual 1', validade=1, dias_atras=10)
            _ficha(a2, 'Atual 2', validade=1, dias_atras=10)
            _ficha(a3, 'Atual 3', validade=2, dias_atras=10)
            FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id, a2.id, a3.id], 'vencer')
            # a1: a ficha venceu; a2: trocou de ficha antes; a3: ainda não venceu
            atual1.data_inicio = data_atual() - timedelta(days=40)
            VersaoGlobal.query.filter_by(user_id=a2.id).one().data_fim = data_atual()
            db.session.commit()
            _ficha(a2, 'Outra')
            assert FichaLoteService.aplicar_agendadas() == (1, 1)
            assert _ativa(a1).descricao == 'Próxima' and _ativa(a1).validade_meses == 2
            assert FichaEnviada.query.filter_by(aluno_id=a1.id).one().status == 'aplicada'
            cancelada = FichaEnviada.query.filter_by(aluno_id=a2.id).one()
            assert (cancelada.status, cancelada.motivo) == ('cancelada', 'o aluno trocou de ficha antes do vencimento')
            assert FichaEnviada.query.filter_by(aluno_id=a3.id).one().status == 'pendente'

    def test_comando_do_cron(self, app):
        with app.app_context():
            saida = app.test_cli_runner().invoke(args=['versoes-alertar-expiracao']).output
            assert 'ficha(s) agendada(s) aplicada(s)' in saida


class TestSugestao:
    def test_envio_novo_substitui_o_pendente(self, app):
        with app.app_context():
            prof, (a1,) = _cenario('subst', 1)
            f1, f2 = _ficha(prof, 'Uma'), _ficha(prof, 'Outra')
            FichaLoteService.aplicar(prof, f'p:{f1.id}', [a1.id], 'sugestao')
            res = FichaLoteService.aplicar(prof, f'p:{f2.id}', [a1.id], 'sugestao')
            assert res[0]['texto'] == 'o aluno escolhe se aceita · substituiu o envio anterior'
            assert [e.status for e in FichaEnviada.query.filter_by(aluno_id=a1.id).order_by(FichaEnviada.id)] \
                == ['cancelada', 'pendente']

    def test_alerta_no_painel_depois_de_3_dias(self, app):
        with app.app_context():
            prof, (a1,) = _cenario('alsug', 1)
            origem = _ficha(prof, 'Sugerida')
            _ficha(a1, 'Atual')
            FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id], 'sugestao')
            from services.dashboard_service import DashboardService
            CacheService.invalidate(f'dashboard_professor:{prof.id}')
            assert not [a for a in DashboardService.dados_professor(prof.id)['alertas'] if a['tipo'] == 'sugestao']
            envio = FichaEnviada.query.filter_by(aluno_id=a1.id).one()
            envio.criada_em = datetime.now(timezone.utc) - timedelta(days=4)
            db.session.commit()
            CacheService.invalidate(f'dashboard_professor:{prof.id}')
            alerta = [a for a in DashboardService.dados_professor(prof.id)['alertas'] if a['tipo'] == 'sugestao']
            assert alerta[0]['detalhe'] == '"Sugerida" sem resposta há 4 dias'
            assert alerta[0]['chave'] == f's{envio.id}'


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


class TestTelas:
    def test_tela_do_professor_e_resultado_por_aluno(self, client, app):
        with app.app_context():
            prof, (a1, a2) = _cenario('tela', 2)
            outro_prof, (alheio,) = _cenario('tela_outro', 1)
            origem = _ficha(prof, 'Para Todos')
            _ficha(a1, 'Atual Um', validade=2)
            ids = (origem.id, a1.id, a2.id, alheio.id)
        _login(client, 'tela_prof')
        html = client.get('/professor/fichas/aplicar').get_data(as_text=True)
        assert f'value="p:{ids[0]}"' in html and 'Suas fichas' in html
        assert 'Fichas atuais dos seus alunos' in html and 'de Tela Aluno0' in html
        assert 'Tela Aluno1' in html and 'sem ficha ativa' in html and 'vence em' in html
        assert 'Tela_Outro' not in html
        r = client.post('/professor/fichas/aplicar', data={
            'fonte': f'p:{ids[0]}', 'alunos': [ids[1], ids[2], ids[3]], 'modo': 'sugestao', 'validade': 'sem'})
        html = r.get_data(as_text=True)
        assert '2 sugestões enviadas' in html and '1 ignorado' in html
        assert 'Ignorado: não está na sua lista de alunos ativos' in html
        assert 'Envios pendentes' in html
        with app.app_context():
            assert FichaEnviada.query.filter_by(aluno_id=ids[1]).one().validade_meses is None

    def test_validacoes_da_tela(self, client, app):
        with app.app_context():
            prof, (a1,) = _cenario('val', 1)
            outro, _ = _cenario('val_outro', 0)
            alheia = _ficha(outro, 'Alheia')
            ids = (a1.id, alheia.id)
        _login(client, 'val_prof')
        html = client.post('/professor/fichas/aplicar', data={'fonte': f'p:{ids[1]}', 'alunos': [ids[0]],
                                                              'modo': 'agora'}).get_data(as_text=True)
        assert 'Escolha uma ficha da lista.' in html
        html = client.post('/professor/fichas/aplicar', data={'fonte': 'm:full-body', 'alunos': [],
                                                              'modo': 'agora'}).get_data(as_text=True)
        assert 'Marque pelo menos um aluno.' in html
        html = client.post('/professor/fichas/aplicar', data={'fonte': 'm:full-body', 'alunos': [ids[0]],
                                                              'modo': 'agora', 'validade': 'meses',
                                                              'validade_meses': '99'}).get_data(as_text=True)
        assert 'Validade deve ser entre 1 e 24 meses.' in html

    def test_aluno_ve_aceita_e_professor_cancela(self, client, app):
        with app.app_context():
            prof, (a1, a2) = _cenario('resp', 2)
            origem = _ficha(prof, 'Nova Sugerida', exercicios=[_base('Agachamento livre')])
            _ficha(a1, 'Atual')
            FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id, a2.id], 'sugestao')
            e1 = FichaEnviada.query.filter_by(aluno_id=a1.id).one().id
            e2 = FichaEnviada.query.filter_by(aluno_id=a2.id).one().id
        _login(client, 'resp_aluno0')
        assert 'Nova Sugerida' in client.get('/aluno/dashboard').get_data(as_text=True)
        html = client.get(f'/aluno/ficha-sugerida/{e1}').get_data(as_text=True)
        assert 'Agachamento livre' in html and '4 × 8–12' in html and 'Aceitar ficha' in html
        assert client.get(f'/aluno/ficha-sugerida/{e2}').status_code == 302  # de outro aluno
        r = client.post(f'/aluno/ficha-sugerida/{e1}/responder', data={'resposta': 'aceitar'})
        assert r.status_code == 302 and '/aluno/versao/' in r.headers['Location']
        with app.app_context():
            a1 = User.query.filter_by(username='resp_aluno0').one()
            assert _ativa(a1).descricao == 'Nova Sugerida'
            assert Notificacao.query.filter_by(titulo=f'{a1.nome_completo} aceitou a ficha sugerida').count() == 1
        client.get('/auth/logout')
        _login(client, 'resp_prof')
        client.post(f'/professor/fichas/envio/{e2}/cancelar')
        with app.app_context():
            assert db.session.get(FichaEnviada, e2).status == 'cancelada'

    def test_aluno_recusa(self, client, app):
        with app.app_context():
            prof, (a1,) = _cenario('recusa', 1)
            origem = _ficha(prof, 'Talvez')
            atual = _ficha(a1, 'Minha')
            FichaLoteService.aplicar(prof, f'p:{origem.id}', [a1.id], 'sugestao')
            envio_id, atual_id = FichaEnviada.query.filter_by(aluno_id=a1.id).one().id, atual.id
        _login(client, 'recusa_aluno0')
        client.post(f'/aluno/ficha-sugerida/{envio_id}/responder', data={'resposta': 'recusar'})
        with app.app_context():
            assert _ativa(User.query.filter_by(username='recusa_aluno0').one()).id == atual_id
            assert db.session.get(FichaEnviada, envio_id).status == 'recusada'
        r = client.post(f'/aluno/ficha-sugerida/{envio_id}/responder', data={'resposta': 'aceitar'})
        assert r.status_code == 302  # já respondida: só avisa
        with app.app_context():
            assert _ativa(User.query.filter_by(username='recusa_aluno0').one()).id == atual_id

    def test_atalhos(self, client, app):
        with app.app_context():
            _usuario('atalho_prof', 'professor')
        _login(client, 'atalho_prof')
        assert '/professor/fichas/aplicar' in client.get('/professor/alunos').get_data(as_text=True)
        assert '/professor/fichas/aplicar' in client.get('/professor/dashboard').get_data(as_text=True)


def test_migracao_cria_e_remove_a_tabela(app):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    spec = importlib.util.spec_from_file_location('mig_fichas', 'migrations/versions/d9e2f6a3b8c5_fichas_enviadas.py')
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == 'c8d1e5f2a7b4'
    with app.app_context():
        def rodar(f):
            with db.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    f()

        def existe():
            return 'fichas_enviadas' in inspect(db.engine).get_table_names()
        assert existe()
        rodar(mig.downgrade)
        assert not existe()
        rodar(mig.upgrade)
        assert existe()
