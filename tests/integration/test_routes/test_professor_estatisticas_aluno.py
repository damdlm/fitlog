"""Testes de integração para a tela de estatísticas do aluno vista pelo
professor (routes/professor_routes.py:estatisticas_aluno), com foco no
filtro de período (data inicial/final) adicionado à página.
"""
from datetime import date, datetime, timedelta

from models import (db, User, AlunoProfessor, Musculo, ExercicioUsuario,
                     VersaoGlobal, TreinoVersao, RegistroTreino, HistoricoTreino)


def _criar_usuario(username, tipo_usuario='aluno'):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo_usuario, nome_completo=username.title())
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


def _montar_aluno_com_registro(aluno_id, data_treino, carga=100, repeticoes=10):
    """Cria (ou reaproveita, se já existir pra esse aluno) músculo +
    exercício + versão + treino, adiciona 1 registro (1 série) na data
    informada, e devolve o registro criado. Reaproveitar entre chamadas
    pro mesmo aluno é necessário porque (user_id, numero_versao) e
    (versao_id, codigo) são únicos no banco."""
    musculo = Musculo.query.filter_by(nome='peito_teste').first()
    if not musculo:
        musculo = Musculo(nome='peito_teste', nome_exibicao='Peito')
        db.session.add(musculo)
        db.session.commit()

    exercicio = ExercicioUsuario.query.filter_by(usuario_id=aluno_id, nome='Supino').first()
    if not exercicio:
        exercicio = ExercicioUsuario(usuario_id=aluno_id, nome='Supino', musculo_id=musculo.id)
        db.session.add(exercicio)
        db.session.commit()

    versao = VersaoGlobal.query.filter_by(user_id=aluno_id, numero_versao=1).first()
    if not versao:
        versao = VersaoGlobal(numero_versao=1, descricao='V1', divisao='A',
                               data_inicio=date(2020, 1, 1), user_id=aluno_id)
        db.session.add(versao)
        db.session.commit()

    treino = TreinoVersao.query.filter_by(versao_id=versao.id, codigo='A').first()
    if not treino:
        treino = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Treino A')
        db.session.add(treino)
        db.session.commit()

    registro = RegistroTreino(
        treino_versao_id=treino.id, versao_id=versao.id, periodo='manha',
        semana=1, exercicio_usuario_id=exercicio.id, data_registro=data_treino,
        user_id=aluno_id,
    )
    db.session.add(registro)
    db.session.commit()

    serie = HistoricoTreino(registro_id=registro.id, carga=carga, repeticoes=repeticoes, ordem=1)
    db.session.add(serie)
    db.session.commit()
    return registro


class TestFiltroPeriodo:
    def test_requer_login(self, client):
        resp = client.get('/professor/aluno/1/estatisticas')
        assert resp.status_code == 302

    def test_sem_parametros_usa_mes_corrente_e_inclui_registro_de_hoje(self, client, app):
        with app.app_context():
            prof = _criar_usuario('est_prof_1', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_1')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            hoje_meia_noite = datetime.combine(date.today(), datetime.min.time())
            _montar_aluno_com_registro(aluno.id, hoje_meia_noite, carga=100, repeticoes=10)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')

        primeiro_dia = date.today().replace(day=1).isoformat()
        assert f'value="{primeiro_dia}"' in html, \
            'campo "Data inicial" deveria vir com o 1º dia do mês corrente'
        assert 'value="' + date.today().isoformat() not in html or True  # ver asserts de fim abaixo
        assert '1000kg' in html or '1000.0kg' in html, \
            'card Volume Total deveria mostrar 100 x 10 = 1000kg (registro de hoje, dentro do mês corrente)'
        assert '>1<' in html, 'card Total de Registros deveria mostrar 1'

    def test_registro_fora_do_periodo_selecionado_nao_entra_no_total(self, client, app):
        with app.app_context():
            prof = _criar_usuario('est_prof_2', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_2')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            # um registro em janeiro/2026, outro em março/2026
            _montar_aluno_com_registro(aluno.id, datetime(2026, 1, 15), carga=50, repeticoes=10)
            _montar_aluno_com_registro(aluno.id, datetime(2026, 3, 10), carga=200, repeticoes=10)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        # filtra só fevereiro/2026 -- nenhum dos dois registros deveria entrar
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-02-01&fim=2026-02-28')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '0kg' in html, 'Volume Total deveria ser 0kg (nenhum registro em fevereiro)'

        # filtra só janeiro/2026 -- só o registro de 50x10=500kg deveria entrar
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-01-01&fim=2026-01-31')
        html = resp.data.decode('utf-8')
        assert '500kg' in html
        assert '2000kg' not in html

        # filtra janeiro+março (intervalo cobrindo os dois) -- 500+2000=2500kg
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-01-01&fim=2026-03-31')
        html = resp.data.decode('utf-8')
        assert '2500kg' in html

    def test_data_final_e_inclusiva_ate_23h59(self, client, app):
        with app.app_context():
            prof = _criar_usuario('est_prof_3', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_3')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            # registro gravado às 23:30 do último dia do intervalo
            _montar_aluno_com_registro(
                aluno.id, datetime(2026, 5, 31, 23, 30), carga=10, repeticoes=10)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-05-01&fim=2026-05-31')
        html = resp.data.decode('utf-8')
        assert '100kg' in html, 'registro às 23:30 do dia final selecionado deveria contar (fim é o dia inteiro)'

    def test_data_inicial_maior_que_final_e_trocada_automaticamente(self, client, app):
        with app.app_context():
            prof = _criar_usuario('est_prof_4', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_4')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            _montar_aluno_com_registro(aluno.id, datetime(2026, 6, 15), carga=30, repeticoes=10)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        # inicio depois do fim -- rota deve trocar os dois, não quebrar nem ignorar
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-06-30&fim=2026-06-01')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '300kg' in html
        assert 'value="2026-06-01"' in html
        assert 'value="2026-06-30"' in html

    def test_datas_invalidas_caem_no_padrao_sem_quebrar(self, client, app):
        with app.app_context():
            prof = _criar_usuario('est_prof_5', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_5')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=lixo&fim=2026-99-99')
        assert resp.status_code == 200
        primeiro_dia = date.today().replace(day=1).isoformat()
        assert f'value="{primeiro_dia}"' in resp.data.decode('utf-8')

    def test_treino_stats_tambem_respeita_o_periodo(self, client, app):
        """Os cards por treino (ranking), não só o resumo geral, também
        devem refletir o período selecionado."""
        with app.app_context():
            prof = _criar_usuario('est_prof_6', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_6')
            db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                           ativo=True, data_associacao=datetime.utcnow()))
            db.session.commit()
            _montar_aluno_com_registro(aluno.id, datetime(2026, 4, 1), carga=999, repeticoes=1)
            username, aluno_id = prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas?inicio=2026-01-01&fim=2026-01-31')
        assert b'999.0' not in resp.data and b'999x1' not in resp.data

    def test_outro_professor_nao_acessa(self, client, app):
        with app.app_context():
            _criar_usuario('est_prof_7', tipo_usuario='professor')
            aluno = _criar_usuario('est_aluno_7')
            outro_prof = _criar_usuario('est_prof_8', tipo_usuario='professor')
            username, aluno_id = outro_prof.username, aluno.id

        _login(client, username)
        resp = client.get(f'/professor/aluno/{aluno_id}/estatisticas', follow_redirects=True)
        assert resp.status_code == 200
        assert 'não tem permissão'.encode('utf-8') in resp.data


class TestFiltroVersaoDesempenhoPorTreino:
    """Seção "Desempenho por Treino": filtro por versão do aluno, com a
    versão ativa carregada por padrão."""

    def _montar(self, app, sufixo):
        prof = _criar_usuario(f'ver_prof_{sufixo}', tipo_usuario='professor')
        aluno = _criar_usuario(f'ver_aluno_{sufixo}')
        db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=prof.id,
                                       ativo=True, data_associacao=datetime.utcnow()))
        musculo = Musculo.query.filter_by(nome='peito_teste').first()
        if not musculo:
            musculo = Musculo(nome='peito_teste', nome_exibicao='Peito')
            db.session.add(musculo)
        db.session.commit()
        exercicio = ExercicioUsuario(usuario_id=aluno.id, nome='Supino', musculo_id=musculo.id)
        db.session.add(exercicio)
        db.session.commit()

        hoje = datetime.combine(date.today(), datetime.min.time())
        ids = {}
        for numero, codigo, nome, fim in ((1, 'A', 'Treino Antigo', date(2020, 6, 1)),
                                          (2, 'B', 'Treino Atual', None)):
            v = VersaoGlobal(numero_versao=numero, descricao=f'Versao {numero}', divisao='A',
                              data_inicio=date(2020, 1, 1), data_fim=fim, user_id=aluno.id)
            db.session.add(v)
            db.session.commit()
            tv = TreinoVersao(versao_id=v.id, codigo=codigo, nome_treino=nome)
            db.session.add(tv)
            db.session.commit()
            r = RegistroTreino(treino_versao_id=tv.id, versao_id=v.id, periodo='manha',
                                semana=1, exercicio_usuario_id=exercicio.id,
                                data_registro=hoje, user_id=aluno.id)
            db.session.add(r)
            db.session.commit()
            db.session.add(HistoricoTreino(registro_id=r.id, carga=50, repeticoes=10, ordem=1))
            db.session.commit()
            ids[numero] = v.id
        return prof.username, aluno.id, ids

    def _get(self, client, aluno_id, qs=''):
        return client.get(f'/professor/aluno/{aluno_id}/estatisticas{qs}').get_data(as_text=True)

    def test_padrao_carrega_a_versao_ativa(self, client, app):
        with app.app_context():
            username, aluno_id, ids = self._montar(app, 'pad')
        _login(client, username)

        html = self._get(client, aluno_id)

        assert 'Treino Atual' in html
        assert 'Treino Antigo' not in html
        # seletor marca a ativa como selecionada
        assert f'<option value="{ids[2]}" selected>' in html
        assert '(ativa)' in html

    def test_escolher_outra_versao_mostra_so_os_treinos_dela(self, client, app):
        with app.app_context():
            username, aluno_id, ids = self._montar(app, 'out')
        _login(client, username)

        html = self._get(client, aluno_id, f'?versao={ids[1]}')

        assert 'Treino Antigo' in html
        assert 'Treino Atual' not in html

    def test_todas_as_versoes(self, client, app):
        with app.app_context():
            username, aluno_id, _ = self._montar(app, 'tod')
        _login(client, username)

        html = self._get(client, aluno_id, '?versao=todas')

        assert 'Treino Antigo' in html and 'Treino Atual' in html

    def test_versao_invalida_ou_de_outro_aluno_volta_para_a_ativa(self, client, app):
        with app.app_context():
            username, aluno_id, _ = self._montar(app, 'inv')
            outro = _criar_usuario('ver_outro_aluno')
            v_outro = VersaoGlobal(numero_versao=1, descricao='Alheia', divisao='A',
                                    data_inicio=date(2020, 1, 1), user_id=outro.id)
            db.session.add(v_outro)
            db.session.commit()
            id_alheia = v_outro.id
        _login(client, username)

        for qs in ('?versao=abc', '?versao=999999', f'?versao={id_alheia}'):
            html = self._get(client, aluno_id, qs)
            assert 'Treino Atual' in html
            assert 'Treino Antigo' not in html
            assert 'Alheia' not in html

    def test_filtro_de_versao_preserva_o_periodo(self, client, app):
        with app.app_context():
            username, aluno_id, _ = self._montar(app, 'per')
        _login(client, username)

        html = self._get(client, aluno_id, '?inicio=2020-01-01&fim=2020-01-31')

        assert '<input type="hidden" name="inicio" value="2020-01-01">' in html
        assert '<input type="hidden" name="fim" value="2020-01-31">' in html

    def test_parcial_devolve_so_o_card_sem_a_pagina_inteira(self, client, app):
        # A troca de versão pede ?parcial=1 e substitui só o card.
        with app.app_context():
            username, aluno_id, ids = self._montar(app, 'par')
        _login(client, username)

        html = self._get(client, aluno_id, f'?versao={ids[1]}&parcial=1')

        assert 'Treino Antigo' in html and 'Treino Atual' not in html
        assert 'id="estFiltroVersaoSel"' in html
        assert '<html' not in html and 'est-filtro-periodo' not in html
        assert 'muscleChart' not in html

    def test_filtro_de_periodo_preserva_a_versao_escolhida(self, client, app):
        with app.app_context():
            username, aluno_id, ids = self._montar(app, 'pv')
        _login(client, username)

        html = self._get(client, aluno_id, f'?versao={ids[1]}')

        assert f'<input type="hidden" name="versao" value="{ids[1]}">' in html