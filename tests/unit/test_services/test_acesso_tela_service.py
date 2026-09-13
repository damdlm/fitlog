"""Testes para AcessoTelaService -- contagem agregada de acessos por
tela (ver models.AcessoTela)."""
from datetime import date, timedelta

from models import db, AcessoTela
from services.acesso_tela_service import AcessoTelaService


class TestDeveContar:

    def test_ignora_endpoints_tecnicos(self, app):
        assert AcessoTelaService.deve_contar('static', '/static/x.css') is False
        assert AcessoTelaService.deve_contar('health', '/health') is False
        assert AcessoTelaService.deve_contar('admin.api_monitoramento', '/admin/api/monitoramento') is False
        assert AcessoTelaService.deve_contar(None, '/qualquer') is False

    def test_ignora_endpoints_de_api_e_caminhos_tecnicos(self, app):
        assert AcessoTelaService.deve_contar('api.notificacoes', '/api/notificacoes') is False
        assert AcessoTelaService.deve_contar('aluno.foto', '/exercicios-media/x.gif') is False

    def test_conta_tela_normal(self, app):
        assert AcessoTelaService.deve_contar('aluno.versoes', '/aluno/versoes') is True


class TestRegistrarAcesso:

    def test_primeiro_acesso_do_dia_cria_linha(self, app):
        with app.app_context():
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')

            linha = AcessoTela.query.one()
            assert linha.endpoint == 'aluno.versoes'
            assert linha.papel == 'aluno'
            assert linha.contagem == 1
            assert linha.data == date.today()

    def test_segundo_acesso_no_mesmo_dia_incrementa(self, app):
        with app.app_context():
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')

            linha = AcessoTela.query.one()
            assert linha.contagem == 3

    def test_papeis_diferentes_geram_linhas_separadas(self, app):
        with app.app_context():
            AcessoTelaService.registrar_acesso('admin.monitoramento', 'admin')
            AcessoTelaService.registrar_acesso('admin.monitoramento', 'anonimo')

            assert AcessoTela.query.count() == 2

    def test_papel_invalido_vira_anonimo(self, app):
        with app.app_context():
            AcessoTelaService.registrar_acesso('main.index', 'papel-esquisito')

            linha = AcessoTela.query.one()
            assert linha.papel == 'anonimo'

    def test_falha_ao_gravar_nao_propaga_excecao(self, app, monkeypatch):
        with app.app_context():
            def commit_quebrado():
                raise RuntimeError("banco fora do ar")
            monkeypatch.setattr(db.session, 'commit', commit_quebrado)

            AcessoTelaService.registrar_acesso('main.index', 'aluno')


class TestGetRelatorio:

    def test_sem_acessos_retorna_lista_vazia(self, app):
        with app.app_context():
            resultado = AcessoTelaService.get_relatorio(dias=30)

        assert resultado['disponivel'] is True
        assert resultado['telas'] == []
        assert resultado['total_geral'] == 0

    def test_agrega_por_endpoint_e_papel_ordenado_por_total(self, app):
        with app.app_context():
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')
            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')
            AcessoTelaService.registrar_acesso('aluno.versoes', 'professor')
            AcessoTelaService.registrar_acesso('admin.monitoramento', 'admin')

            resultado = AcessoTelaService.get_relatorio(dias=30)

        assert resultado['total_geral'] == 4
        assert resultado['telas'][0]['endpoint'] == 'aluno.versoes'
        assert resultado['telas'][0]['total'] == 3
        assert resultado['telas'][0]['por_papel']['aluno'] == 2
        assert resultado['telas'][0]['por_papel']['professor'] == 1
        assert resultado['telas'][0]['nome_amigavel'] == 'Aluno · Versoes'
        assert resultado['telas'][1]['endpoint'] == 'admin.monitoramento'

    def test_ignora_acessos_fora_da_janela(self, app):
        with app.app_context():
            antigo = AcessoTela(
                endpoint='aluno.versoes', papel='aluno',
                data=date.today() - timedelta(days=40), contagem=10,
            )
            db.session.add(antigo)
            db.session.commit()

            AcessoTelaService.registrar_acesso('aluno.versoes', 'aluno')

            resultado = AcessoTelaService.get_relatorio(dias=30)

        assert resultado['total_geral'] == 1
