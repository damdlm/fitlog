"""Integridade do histórico de migrations (Alembic), sem banco.

Pega, ainda no CI, os erros que derrubam o preDeployCommand do Railway:
mais de uma head (duas migrations apontando para o mesmo pai) e revision id
duplicado (duas migrations com o mesmo id -- aconteceu com e7f8a9b0c1d2).
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

RAIZ = Path(__file__).resolve().parents[2]
VERSOES = RAIZ / 'migrations' / 'versions'


def _script():
    cfg = Config()
    cfg.set_main_option('script_location', str(RAIZ / 'migrations'))
    return ScriptDirectory.from_config(cfg)


def test_existe_uma_unica_head():
    heads = _script().get_heads()
    assert len(heads) == 1, (
        f'O histórico de migrations tem {len(heads)} heads: {sorted(heads)}. '
        'Duas migrations apontam para o mesmo down_revision -- ajuste o '
        'down_revision de uma delas para encadear (ou use `alembic merge`).'
    )


def test_nenhum_revision_id_duplicado():
    arquivos = sorted(p.name for p in VERSOES.glob('*.py') if p.name != '__init__.py')
    revisoes = [r.revision for r in _script().walk_revisions()]
    assert len(revisoes) == len(arquivos), (
        f'{len(arquivos)} arquivos de migration, mas só {len(revisoes)} revision ids distintos: '
        'há revision id duplicado entre arquivos (confira o prefixo e a linha `revision =`).'
    )


def test_todo_down_revision_existe():
    # walk_revisions levanta erro se algum down_revision apontar para um id inexistente.
    assert list(_script().walk_revisions())
