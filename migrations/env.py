from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Importa o metadata dos models para que o Alembic detecte mudanças automaticamente
from models import db

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.metadata


def get_url():
    """Lê a URL do banco do ambiente Flask, com fallback para alembic.ini."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    """Modo offline: gera SQL sem conectar ao banco.
    Útil para revisar migrações antes de aplicar.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: conecta ao banco e aplica as migrações."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
