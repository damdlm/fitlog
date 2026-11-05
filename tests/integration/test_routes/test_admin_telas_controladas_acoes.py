"""
POST /admin/telas-controladas -- os 5 formulários da página do admin,
distinguidos pelo campo oculto `acao`. O formulário "telas" (acao ausente)
já é coberto em test_admin_routes.py; aqui ficam os demais:

  planos          -> preço dos planos (dinheiro)
  cobranca        -> liga/desliga a cobrança no app inteiro (modo grátis)
  tela_assinatura -> liga/desliga a tela "Minha Assinatura"
  plano_padrao    -> versão-modelo dada a todo aluno novo
  telas_professor -> telas de gestão bloqueadas ao professor inadimplente

São chaves-mestras do negócio: um erro aqui afeta TODOS os usuários.
"""

import pytest

from models import (
    db, User, Plano, VersaoGlobal, TreinoVersao, VersaoExercicio, ExercicioUsuario,
    TelaControladaProfessor, TelaControlada,
)
from services.configuracao_service import ConfiguracaoService

URL = '/admin/telas-controladas'


def _user(username, admin=False, tipo='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo, is_admin=admin)
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u.id


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': 'SenhaForte123!'})


@pytest.fixture
def admin(app, client):
    uid = _user('adm_telas', admin=True)
    _login(client, 'adm_telas')
    return uid


@pytest.fixture
def planos(app):
    db.session.add_all([
        Plano(codigo='aluno_fit', nome='Plano Fit', tipo_usuario='aluno', preco_centavos=599),
        Plano(codigo='professor_pro', nome='Plano Pró', tipo_usuario='professor', preco_centavos=2990),
        Plano(codigo='professor_premium', nome='Plano Premium', tipo_usuario='professor', preco_centavos=9990),
    ])
    db.session.commit()


def _flashes(client):
    with client.session_transaction() as sess:
        return list(sess.get('_flashes', []))


def _preco(codigo):
    db.session.expire_all()
    return Plano.query.filter_by(codigo=codigo).one().preco_centavos


def _post(client, **campos):
    return client.post(URL, data=campos)


# ------------------------------------------------------------------
# acesso
# ------------------------------------------------------------------

class TestAcesso:

    def test_usuario_comum_nao_altera_precos(self, client, app, planos):
        _user('aluno_curioso')
        _login(client, 'aluno_curioso')

        resp = _post(client, acao='planos', preco_aluno_fit='0.01',
                     preco_professor_pro='0.01', preco_professor_premium='0.01')

        assert resp.status_code == 302
        assert _preco('aluno_fit') == 599

    def test_usuario_comum_nao_desliga_a_cobranca(self, client, app):
        _user('aluno_curioso2')
        _login(client, 'aluno_curioso2')
        antes = ConfiguracaoService.cobranca_ativa()

        _post(client, acao='cobranca')              # sem checkbox = "desativar"

        assert ConfiguracaoService.cobranca_ativa() is antes

    def test_anonimo_vai_para_o_login(self, app):
        with app.app_context():
            resp = app.test_client().post(URL, data={'acao': 'cobranca'})
        assert resp.status_code == 302 and '/auth/login' in resp.headers['Location']


# ------------------------------------------------------------------
# acao = planos
# ------------------------------------------------------------------

class TestAcaoPlanos:

    def test_valores_validos_atualizam_e_avisam(self, client, admin, planos):
        resp = _post(client, acao='planos', preco_aluno_fit='6,90',
                     preco_professor_pro='31.90', preco_professor_premium='109')

        assert resp.status_code == 302 and resp.headers['Location'].endswith(URL)
        assert ('success', 'Preço dos planos atualizado!') in _flashes(client)
        assert (_preco('aluno_fit'), _preco('professor_pro'), _preco('professor_premium')) == (690, 3190, 10900)

    def test_valor_invalido_mostra_um_aviso_por_erro_e_nao_salva_nada(self, client, admin, planos):
        resp = _post(client, acao='planos', preco_aluno_fit='6.90',
                     preco_professor_pro='abc', preco_professor_premium='0')

        assert resp.status_code == 302
        erros = [m for cat, m in _flashes(client) if cat == 'danger']
        assert len(erros) == 2 and any('Plano Pró' in e for e in erros) and any('Plano Premium' in e for e in erros)
        assert not any(cat == 'success' for cat, _ in _flashes(client))
        assert (_preco('aluno_fit'), _preco('professor_pro'), _preco('professor_premium')) == (599, 2990, 9990)


# ------------------------------------------------------------------
# acao = cobranca / tela_assinatura
# ------------------------------------------------------------------

class TestAcaoCobranca:

    def test_checkbox_marcado_reativa_a_cobranca(self, client, admin):
        ConfiguracaoService.set_cobranca_ativa(False)

        resp = _post(client, acao='cobranca', cobranca_ativa='on')

        assert resp.status_code == 302
        assert ConfiguracaoService.cobranca_ativa() is True
        assert ('success', 'Cobrança reativada -- planos voltam a ser exigidos normalmente.') in _flashes(client)

    def test_checkbox_desmarcado_liga_o_modo_gratis(self, client, admin):
        ConfiguracaoService.set_cobranca_ativa(True)

        _post(client, acao='cobranca')

        assert ConfiguracaoService.cobranca_ativa() is False
        assert any(cat == 'warning' and 'modo grátis' in m for cat, m in _flashes(client))

    def test_valor_diferente_de_on_conta_como_desmarcado(self, client, admin):
        ConfiguracaoService.set_cobranca_ativa(True)

        _post(client, acao='cobranca', cobranca_ativa='true')

        assert ConfiguracaoService.cobranca_ativa() is False


class TestAcaoTelaAssinatura:

    def test_marcado_reativa(self, client, admin):
        ConfiguracaoService.set_tela_assinatura_ativa(False)

        _post(client, acao='tela_assinatura', tela_assinatura_ativa='on')

        assert ConfiguracaoService.tela_assinatura_ativa() is True
        assert any(cat == 'success' and 'reativada' in m for cat, m in _flashes(client))

    def test_desmarcado_esconde_a_tela(self, client, admin):
        ConfiguracaoService.set_tela_assinatura_ativa(True)

        _post(client, acao='tela_assinatura')

        assert ConfiguracaoService.tela_assinatura_ativa() is False
        assert any(cat == 'warning' and 'desativada' in m for cat, m in _flashes(client))

    def test_nao_mexe_na_chave_de_cobranca(self, client, admin):
        ConfiguracaoService.set_cobranca_ativa(True)
        ConfiguracaoService.set_tela_assinatura_ativa(True)

        _post(client, acao='tela_assinatura')

        assert ConfiguracaoService.cobranca_ativa() is True


# ------------------------------------------------------------------
# acao = plano_padrao
# ------------------------------------------------------------------

def _versao_com_exercicio(user_id, com_exercicio=True):
    v = VersaoGlobal(numero_versao=1, descricao='modelo', divisao='LIVRE',
                     data_inicio=__import__('datetime').date(2024, 1, 1), user_id=user_id)
    db.session.add(v)
    db.session.commit()
    t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='Treino A', ordem=0)
    db.session.add(t)
    db.session.commit()
    if com_exercicio:
        ex = ExercicioUsuario(usuario_id=user_id, nome='Supino')
        db.session.add(ex)
        db.session.commit()
        db.session.add(VersaoExercicio(treino_versao_id=t.id, exercicio_usuario_id=ex.id, ordem=0))
        db.session.commit()
    return v.id


class TestAcaoPlanoPadrao:

    def test_define_uma_versao_valida_do_proprio_admin(self, client, admin):
        v = _versao_com_exercicio(admin)

        resp = _post(client, acao='plano_padrao', versao_padrao_id=str(v))

        assert resp.status_code == 302
        assert ConfiguracaoService.get_versao_padrao_id() == v
        assert any(cat == 'success' and 'Plano padrão definido' in m for cat, m in _flashes(client))

    def test_valor_vazio_desliga_o_plano_padrao(self, client, admin):
        v = _versao_com_exercicio(admin)
        ConfiguracaoService.set_versao_padrao(v, admin_id=admin)

        _post(client, acao='plano_padrao', versao_padrao_id='')

        assert ConfiguracaoService.get_versao_padrao_id() is None
        assert any(cat == 'warning' and 'desligado' in m for cat, m in _flashes(client))

    def test_campo_ausente_tambem_desliga(self, client, admin):
        v = _versao_com_exercicio(admin)
        ConfiguracaoService.set_versao_padrao(v, admin_id=admin)

        _post(client, acao='plano_padrao')

        assert ConfiguracaoService.get_versao_padrao_id() is None

    @pytest.mark.parametrize('lixo', ['abc', '1.5', '1; DROP TABLE users', '0x10'])
    def test_id_nao_numerico_mostra_erro_e_nao_altera(self, client, admin, lixo):
        v = _versao_com_exercicio(admin)
        ConfiguracaoService.set_versao_padrao(v, admin_id=admin)

        _post(client, acao='plano_padrao', versao_padrao_id=lixo)

        assert ('danger', 'Versão inválida.') in _flashes(client)
        assert ConfiguracaoService.get_versao_padrao_id() == v

    def test_versao_de_outro_usuario_e_recusada(self, client, admin):
        outro = _user('outro_dono')
        v_alheia = _versao_com_exercicio(outro)

        _post(client, acao='plano_padrao', versao_padrao_id=str(v_alheia))

        assert ('danger', 'Versão não encontrada.') in _flashes(client)
        assert ConfiguracaoService.get_versao_padrao_id() is None

    def test_versao_inexistente_e_recusada(self, client, admin):
        _post(client, acao='plano_padrao', versao_padrao_id='999999')

        assert ('danger', 'Versão não encontrada.') in _flashes(client)

    def test_versao_sem_exercicios_e_recusada(self, client, admin):
        v = _versao_com_exercicio(admin, com_exercicio=False)

        _post(client, acao='plano_padrao', versao_padrao_id=str(v))

        assert any(cat == 'danger' for cat, _ in _flashes(client))
        assert ConfiguracaoService.get_versao_padrao_id() is None


# ------------------------------------------------------------------
# acao = telas_professor
# ------------------------------------------------------------------

class TestAcaoTelasProfessor:

    def test_atualiza_so_as_telas_marcadas(self, client, admin):
        _post(client, acao='telas_professor', bloqueia_professor=['professor_dashboard', 'professor_solicitacoes'])

        db.session.expire_all()
        bloqueadas = {t.chave for t in TelaControladaProfessor.query.filter_by(bloqueia_sem_plano=True)}
        assert bloqueadas == {'professor_dashboard', 'professor_solicitacoes'}
        assert ('success', 'Configuração de telas do professor salva!') in _flashes(client)

    def test_nenhuma_marcada_libera_todas_as_telas_do_professor(self, client, admin):
        _post(client, acao='telas_professor')

        db.session.expire_all()
        assert TelaControladaProfessor.query.filter_by(bloqueia_sem_plano=True).count() == 0

    def test_nao_mexe_nas_telas_do_aluno(self, client, admin):
        antes = {t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=True)}

        _post(client, acao='telas_professor', bloqueia_professor=['professor_dashboard'])

        db.session.expire_all()
        assert {t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=True)} == antes


class TestAcaoDesconhecida:

    def test_acao_desconhecida_cai_no_formulario_de_telas_do_aluno(self, client, admin):
        """Comportamento atual: sem `acao` reconhecida, vale o formulário
        antigo de telas -- logo, enviar vazio LIBERA todas as telas."""
        _post(client, acao='qualquer-coisa')

        db.session.expire_all()
        assert TelaControlada.query.filter_by(bloqueia_sem_plano=True).count() == 0


# ------------------------------------------------------------------
# GET
# ------------------------------------------------------------------

class TestGet:

    def test_renderiza_com_os_campos_de_preco_dos_planos(self, client, admin, planos):
        resp = client.get(URL)

        corpo = resp.get_data(as_text=True)
        assert resp.status_code == 200
        for codigo in ('aluno_fit', 'professor_pro', 'professor_premium'):
            assert f'preco_{codigo}' in corpo

    def test_lista_so_versoes_do_proprio_admin_no_plano_padrao(self, client, admin):
        minha = _versao_com_exercicio(admin)
        outro = _user('outro_adm')
        alheia = _versao_com_exercicio(outro)

        corpo = client.get(URL).get_data(as_text=True)

        assert f'value="{minha}"' in corpo
        assert f'value="{alheia}"' not in corpo
