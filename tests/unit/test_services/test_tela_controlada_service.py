"""Testes para TelaControladaService (bloqueio dinâmico de tela pelo admin)."""

from models import db, TelaControlada
from services.tela_controlada_service import TelaControladaService
from services.base_service import CacheService


def test_seed_do_conftest_espelha_a_migration(app):
    """As 6 telas seedadas em tests/conftest.py precisam bater com o
    que a migration a1b2c3d4e5f6 semeia em produção -- senão os
    testes rodam contra um estado que não existe de verdade."""
    with app.app_context():
        chaves_bloqueadas = {t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=True).all()}
        chaves_livres = {t.chave for t in TelaControlada.query.filter_by(bloqueia_sem_plano=False).all()}
        assert chaves_bloqueadas == {'estatisticas', 'tabela_progresso', 'fitbot'}
        assert chaves_livres == {'calendario', 'ranking', 'dashboard'}


def test_esta_bloqueada_reflete_o_banco(app):
    with app.app_context():
        assert TelaControladaService.esta_bloqueada('estatisticas') is True
        assert TelaControladaService.esta_bloqueada('calendario') is False


def test_chave_sem_linha_cadastrada_e_tratada_como_livre(app):
    """Uma chave nova que ainda não foi seedada nunca deve travar a
    aplicação -- fica livre até alguém cadastrar a linha."""
    with app.app_context():
        assert TelaControladaService.esta_bloqueada('tela_que_nao_existe') is False


def test_atualizar_troca_o_estado_e_invalida_o_cache(app):
    with app.app_context():
        # Popula o cache com o estado antigo antes de mudar nada.
        assert TelaControladaService.esta_bloqueada('calendario') is False

        TelaControladaService.atualizar({'calendario', 'fitbot'})

        assert TelaControladaService.esta_bloqueada('calendario') is True
        assert TelaControladaService.esta_bloqueada('fitbot') is True
        # estatisticas não veio marcada -- deve ter sido desligada.
        assert TelaControladaService.esta_bloqueada('estatisticas') is False


def test_atualizar_com_conjunto_vazio_libera_todas(app):
    with app.app_context():
        TelaControladaService.atualizar(set())
        assert all(not t.bloqueia_sem_plano for t in TelaControlada.query.all())


def test_listar_todas_retorna_ordenado_por_nome(app):
    with app.app_context():
        nomes = [t.nome_exibicao for t in TelaControladaService.listar_todas()]
        assert nomes == sorted(nomes)
