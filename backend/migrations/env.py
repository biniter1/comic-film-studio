from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

import app.models  # noqa: F401  — registers all models with SQLModel.metadata

config = context.config

# When run from the app (app/migrate.py) we must not reconfigure logging.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    # B6: allow tests to inject a URL via config.attributes
    if "sqlalchemy.url" in (config.attributes or {}):
        return config.attributes["sqlalchemy.url"]  # type: ignore[index]

    # main.py sets the URL directly via config.set_main_option before calling upgrade
    url_from_ini = config.get_main_option("sqlalchemy.url")
    if url_from_ini and not url_from_ini.startswith("driver://"):
        return url_from_ini

    # Fallback: derive from settings (for manual `alembic` CLI usage)
    from app.config import settings

    db_path = settings.data_dir / "cfs.db"
    return f"sqlite:///{db_path.as_posix()}"


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(get_url(), connect_args={"check_same_thread": False})

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
