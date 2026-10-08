"""Plano padrão para alunos novos: o admin escolhe uma de suas versões como
modelo e todo aluno que se cadastra sozinho (sem professor) recebe uma
CÓPIA independente dela -- treinos + exercícios já prontos, editáveis.

Cobre: serviço de cópia (VersaoService.aplicar_plano_padrao_ao_aluno),
configuração (ConfiguracaoService.set_versao_padrao), o gancho no
/auth/register e a tela do admin em /admin/telas-controladas.
"""
from datetime import date

import pytest

from models import (
    db, User, Musculo, VersaoGlobal, TreinoVersao, VersaoExercicio,
    ExercicioUsuario, ExercicioSistema, ConfiguracaoApp,
)
from services.versao_service import VersaoService
from services.configuracao_service import ConfiguracaoService

SENHA = 'Treino#Forte9'


def _usuario(username, tipo='aluno', is_admin=False):
    u = User(username=username, email=f'{username}@teste.com',
             tipo_usuario=tipo, is_admin=is_admin)
    u.set_password('123456')
    db.session.add(u)
    db.session.commit()
    return u


def _montar_modelo(admin, finalizada=False):
    """Versão do admin: treino A (1 exercício do catálogo + 1 personalizado
    do admin, com observação) e treino B (o MESMO exercício personalizado,
    pra checar que a cópia do aluno é reaproveitada)."""
    musculo = Musculo(nome='peito', nome_exibicao='Peito')
    db.session.add(musculo)
    db.session.flush()

    base = ExercicioSistema(id_original='0001', nome='Agachamento', grupo_muscular='Pernas')
    custom = ExercicioUsuario(usuario_id=admin.id, nome='Supino do admin',
                              descricao='desc', musculo_id=musculo.id)
    db.session.add_all([base, custom])
    db.session.flush()

    versao = VersaoGlobal(numero_versao=1, descricao='Plano iniciante', divisao='LIVRE',
                          data_inicio=date(2026, 1, 1),
                          data_fim=date(2026, 2, 1) if finalizada else None,
                          user_id=admin.id, validade_meses=3)
    db.session.add(versao)
    db.session.flush()

    tv_a = TreinoVersao(versao_id=versao.id, codigo='A', nome_treino='Peito e pernas',
                        descricao_treino='dia 1', ordem=0)
    tv_b = TreinoVersao(versao_id=versao.id, codigo='B', nome_treino='Reforço', ordem=1)
    db.session.add_all([tv_a, tv_b])
    db.session.flush()

    db.session.add_all([
        VersaoExercicio(treino_versao_id=tv_a.id, exercicio_base_id=base.id, ordem=0),
        VersaoExercicio(treino_versao_id=tv_a.id, exercicio_usuario_id=custom.id,
                        ordem=1, observacao='pegada aberta'),
        VersaoExercicio(treino_versao_id=tv_b.id, exercicio_usuario_id=custom.id, ordem=0),
    ])
    db.session.commit()
    return versao, base, custom


class TestAplicarPlanoPadrao:

    def test_sem_plano_padrao_configurado_nao_faz_nada(self, app):
        with app.app_context():
            aluno = _usuario('aluno_sem_padrao')
            assert VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id) is None
            db.session.commit()
            assert VersaoGlobal.query.filter_by(user_id=aluno.id).count() == 0

    def test_copia_treinos_exercicios_e_observacoes(self, app):
        with app.app_context():
            admin = _usuario('admin1', 'professor', is_admin=True)
            versao, base, custom = _montar_modelo(admin)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)

            aluno = _usuario('aluno_novo')
            nova = VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id)
            db.session.commit()

            assert nova is not None and nova.user_id == aluno.id
            assert nova.id != versao.id
            assert nova.data_fim is None  # ativa
            assert nova.numero_versao == 1
            assert nova.descricao == 'Plano iniciante'
            assert nova.validade_meses == 3

            treinos = TreinoVersao.query.filter_by(versao_id=nova.id) \
                .order_by(TreinoVersao.ordem).all()
            assert [(t.codigo, t.nome_treino) for t in treinos] == [
                ('A', 'Peito e pernas'), ('B', 'Reforço')]

            ex_a = treinos[0].exercicios
            assert len(ex_a) == 2
            # catálogo: reaproveitado direto
            assert ex_a[0].exercicio_base_id == base.id
            # personalizado: vira exercício PRÓPRIO do aluno, sem vínculo
            copia = ExercicioUsuario.query.get(ex_a[1].exercicio_usuario_id)
            assert copia.usuario_id == aluno.id
            assert copia.id != custom.id
            assert copia.nome == 'Supino do admin'
            assert copia.copiado_de_professor_id is None
            assert copia.copiado_de_exercicio_id is None
            assert ex_a[1].observacao == 'pegada aberta'

            # mesmo exercício do admin em dois treinos -> uma só cópia
            assert treinos[1].exercicios[0].exercicio_usuario_id == copia.id
            assert ExercicioUsuario.query.filter_by(usuario_id=aluno.id).count() == 1

    def test_copia_e_independente_do_modelo(self, app):
        """Aluno edita a cópia; o modelo do admin não muda -- e mudar o
        modelo depois não altera quem já recebeu."""
        with app.app_context():
            admin = _usuario('admin2', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(admin)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)

            aluno = _usuario('aluno_edita')
            nova = VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id)
            db.session.commit()

            tv_aluno = TreinoVersao.query.filter_by(versao_id=nova.id, codigo='A').first()
            tv_aluno.nome_treino = 'Meu treino editado'
            db.session.commit()
            assert TreinoVersao.query.filter_by(versao_id=versao.id, codigo='A') \
                .first().nome_treino == 'Peito e pernas'

            tv_admin = TreinoVersao.query.filter_by(versao_id=versao.id, codigo='B').first()
            tv_admin.nome_treino = 'Mudou depois'
            db.session.commit()
            assert TreinoVersao.query.filter_by(versao_id=nova.id, codigo='B') \
                .first().nome_treino == 'Reforço'

    def test_modelo_finalizado_tambem_serve(self, app):
        with app.app_context():
            admin = _usuario('admin3', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(admin, finalizada=True)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)

            aluno = _usuario('aluno_fin')
            nova = VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id)
            db.session.commit()
            assert nova is not None and nova.data_fim is None

    def test_nao_cria_segunda_versao_ativa(self, app):
        with app.app_context():
            admin = _usuario('admin4', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(admin)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)

            aluno = _usuario('aluno_ja_tem')
            db.session.add(VersaoGlobal(numero_versao=1, descricao='Minha', divisao='LIVRE',
                                        data_inicio=date(2026, 1, 1), user_id=aluno.id))
            db.session.commit()

            assert VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id) is None
            assert VersaoGlobal.query.filter_by(user_id=aluno.id).count() == 1

    def test_excluir_versao_modelo_desliga_o_recurso(self, app):
        with app.app_context():
            admin = _usuario('admin5', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(admin, finalizada=True)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)

            VersaoService.excluir_versao(versao.id, user_id=admin.id)
            assert ConfiguracaoService.get_versao_padrao_id() is None

            aluno = _usuario('aluno_pos_exclusao')
            assert VersaoService.aplicar_plano_padrao_ao_aluno(aluno.id) is None


class TestSetVersaoPadrao:

    def test_so_aceita_versao_do_proprio_admin(self, app):
        with app.app_context():
            admin = _usuario('adm_a', 'professor', is_admin=True)
            outro = _usuario('adm_b', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(outro)
            try:
                ConfiguracaoService.set_versao_padrao(versao.id, admin.id)
                assert False, 'deveria levantar ValueError'
            except ValueError as e:
                assert 'não encontrada' in str(e)
            assert ConfiguracaoService.get_versao_padrao_id() is None

    def test_recusa_versao_sem_exercicios(self, app):
        with app.app_context():
            admin = _usuario('adm_vazio', 'professor', is_admin=True)
            v = VersaoGlobal(numero_versao=1, descricao='Vazia', divisao='LIVRE',
                             data_inicio=date(2026, 1, 1), user_id=admin.id)
            db.session.add(v)
            db.session.commit()
            try:
                ConfiguracaoService.set_versao_padrao(v.id, admin.id)
                assert False, 'deveria levantar ValueError'
            except ValueError as e:
                assert 'exercícios' in str(e)

    def test_none_desliga(self, app):
        with app.app_context():
            admin = _usuario('adm_off', 'professor', is_admin=True)
            versao, _, _ = _montar_modelo(admin)
            ConfiguracaoService.set_versao_padrao(versao.id, admin.id)
            assert ConfiguracaoService.get_versao_padrao_id() == versao.id
            ConfiguracaoService.set_versao_padrao(None, admin.id)
            assert ConfiguracaoService.get_versao_padrao_id() is None


class TestCadastroAplicaPlanoPadrao:

    def _registrar(self, client, username, tipo='aluno'):
        return client.post('/auth/register', data={
            'username': username, 'email': f'{username}@t.com',
            'password': SENHA, 'confirm_password': SENHA,
            'tipo_usuario': tipo, 'aceite_termos': 'on',
        }, follow_redirects=True)

    def _configurar_modelo(self):
        admin = _usuario('admin_reg', 'professor', is_admin=True)
        versao, _, _ = _montar_modelo(admin)
        ConfiguracaoService.set_versao_padrao(versao.id, admin.id)
        return versao

    def test_aluno_que_se_cadastra_recebe_o_plano(self, client, app):
        with app.app_context():
            self._configurar_modelo()
            self._registrar(client, 'aluno_auto')
            aluno = User.query.filter_by(username='aluno_auto').first()
            assert aluno is not None
            ativa = VersaoService.get_ativa(user_id=aluno.id)
            assert ativa is not None
            assert TreinoVersao.query.filter_by(versao_id=ativa.id).count() == 2

    def test_professor_que_se_cadastra_nao_recebe(self, client, app):
        with app.app_context():
            self._configurar_modelo()
            self._registrar(client, 'prof_auto', tipo='professor')
            prof = User.query.filter_by(username='prof_auto').first()
            assert prof is not None
            assert VersaoGlobal.query.filter_by(user_id=prof.id).count() == 0

    def test_sem_plano_configurado_cadastro_funciona_como_antes(self, client, app):
        with app.app_context():
            self._registrar(client, 'aluno_sem_cfg')
            aluno = User.query.filter_by(username='aluno_sem_cfg').first()
            assert aluno is not None
            assert VersaoGlobal.query.filter_by(user_id=aluno.id).count() == 0

    def test_falha_na_copia_nao_derruba_o_cadastro(self, client, app, monkeypatch):
        with app.app_context():
            self._configurar_modelo()

            def _explode(*a, **kw):
                raise RuntimeError('falha simulada')
            monkeypatch.setattr(ExercicioUsuario, 'query',
                                type('Q', (), {'get': staticmethod(_explode)})())

            self._registrar(client, 'aluno_falha')
            aluno = User.query.filter_by(username='aluno_falha').first()
            assert aluno is not None  # cadastro sobreviveu
            assert VersaoGlobal.query.filter_by(user_id=aluno.id).count() == 0  # savepoint desfeito

    def test_aluno_criado_por_professor_nao_recebe(self, app):
        """Criar o usuário direto (como o professor faz em
        professor_routes.novo_aluno / AlunoService.criar_aluno) não passa
        pelo /register, então nunca recebe o plano padrão."""
        with app.app_context():
            self._configurar_modelo()
            aluno = _usuario('aluno_do_prof')
            assert VersaoGlobal.query.filter_by(user_id=aluno.id).count() == 0


class TestTelaAdminPlanoPadrao:

    def _login_admin(self, client):
        admin = _usuario('admin_tela', 'professor', is_admin=True)
        client.post('/auth/login', data={'username': 'admin_tela', 'password': '123456'})
        return admin

    def test_tela_lista_versoes_do_admin(self, client, app):
        with app.app_context():
            admin = self._login_admin(client)
            _montar_modelo(admin)
            resp = client.get('/admin/telas-controladas')
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert 'Plano padrão para alunos novos' in html
            assert 'Plano iniciante' in html

    def test_admin_define_e_desliga_o_plano_padrao(self, client, app):
        with app.app_context():
            admin = self._login_admin(client)
            versao, _, _ = _montar_modelo(admin)

            client.post('/admin/telas-controladas',
                        data={'acao': 'plano_padrao', 'versao_padrao_id': str(versao.id)})
            assert ConfiguracaoService.get_versao_padrao_id() == versao.id

            client.post('/admin/telas-controladas',
                        data={'acao': 'plano_padrao', 'versao_padrao_id': ''})
            assert ConfiguracaoService.get_versao_padrao_id() is None

    def test_nao_admin_nao_define(self, client, app):
        with app.app_context():
            outro = _usuario('nao_admin', 'aluno')
            client.post('/auth/login', data={'username': 'nao_admin', 'password': '123456'})
            client.post('/admin/telas-controladas',
                        data={'acao': 'plano_padrao', 'versao_padrao_id': '1'})
            assert ConfiguracaoService.get_versao_padrao_id() is None


class TestAdminCadastraTreinosModelo:
    """O admin usa a tela "Cadastrar Treinos" (a mesma do aluno) para montar
    a versão-modelo, escolhe-a como plano padrão e o aluno novo recebe a
    cópia -- fluxo completo, sem montar nada direto no banco."""

    @pytest.mark.parametrize('tipo', ['aluno', 'professor', 'admin'])
    def test_admin_abre_a_tela_e_cria_versao(self, client, app, tipo):
        with app.app_context():
            admin = _usuario(f'admin_ct_{tipo}', tipo, is_admin=True)
            client.post('/auth/login', data={'username': admin.username, 'password': '123456'})

            assert client.get('/aluno/cadastrar-treinos').status_code == 200

            client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Plano iniciante'})
            versao = VersaoGlobal.query.filter_by(user_id=admin.id).first()
            assert versao is not None and versao.descricao == 'Plano iniciante'

    def test_fluxo_completo_admin_monta_define_e_aluno_recebe(self, client, app):
        with app.app_context():
            admin = _usuario('admin_fluxo', 'aluno', is_admin=True)
            base = ExercicioSistema(id_original='0100', nome='Remada', grupo_muscular='Costas')
            db.session.add(base)
            db.session.commit()
            base_id = base.id

            client.post('/auth/login', data={'username': 'admin_fluxo', 'password': '123456'})
            client.post('/aluno/cadastrar-treinos/versao', data={'descricao': 'Plano padrão'})
            versao = VersaoGlobal.query.filter_by(user_id=admin.id).first()
            client.post(f'/aluno/cadastrar-treinos/{versao.id}/treino', data={
                'nome_treino': 'Costas', 'descricao_treino': '',
                'exercicios[]': [f'b_{base_id}'],
            })
            tv = TreinoVersao.query.filter_by(versao_id=versao.id).first()
            assert tv is not None and len(tv.exercicios) == 1

            # a versão aparece na tela do admin e pode ser definida como padrão
            html = client.get('/admin/telas-controladas').get_data(as_text=True)
            assert 'Plano padrão' in html
            client.post('/admin/telas-controladas',
                        data={'acao': 'plano_padrao', 'versao_padrao_id': str(versao.id)})
            assert ConfiguracaoService.get_versao_padrao_id() == versao.id

            client.get('/auth/logout')
            client.post('/auth/register', data={
                'username': 'aluno_novo_fluxo', 'email': 'aluno_novo_fluxo@t.com',
                'password': SENHA, 'confirm_password': SENHA,
                'tipo_usuario': 'aluno', 'aceite_termos': 'on',
            })
            novo = User.query.filter_by(username='aluno_novo_fluxo').first()
            copia = VersaoGlobal.query.filter_by(user_id=novo.id).first()
            assert copia is not None and copia.id != versao.id
            treinos = TreinoVersao.query.filter_by(versao_id=copia.id).all()
            assert [t.nome_treino for t in treinos] == ['Costas']
            assert treinos[0].exercicios[0].exercicio_base_id == base_id

    def test_menu_do_admin_tem_link_para_cadastrar_treinos(self, client, app):
        with app.app_context():
            _usuario('admin_menu', 'aluno', is_admin=True)
            client.post('/auth/login', data={'username': 'admin_menu', 'password': '123456'})
            html = client.get('/admin/telas-controladas').get_data(as_text=True)
            assert '/aluno/cadastrar-treinos' in html