"""Regressão: parâmetros SQL não podem vazar em exceções do SQLAlchemy.

str(IntegrityError) inclui os valores enviados (e-mail, hash de senha...).
Esse texto é gravado em CrashLog, logs e Sentry (ver app.py: erro_500).
"""
from config import Config, ProductionConfig


def test_config_base_oculta_parametros_sql():
    assert Config.SQLALCHEMY_ENGINE_OPTIONS.get('hide_parameters') is True


def test_producao_herda_hide_parameters():
    opcoes = ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS
    assert opcoes.get('hide_parameters') is True
    assert opcoes['connect_args']['connect_timeout'] == 10