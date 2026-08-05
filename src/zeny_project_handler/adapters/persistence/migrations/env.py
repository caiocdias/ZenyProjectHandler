"""Ambiente Alembic executado pela composição da aplicação."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, Engine, engine_from_config, pool

from zeny_project_handler.adapters.persistence.schema import metadata

configuration = context.config
target_metadata = metadata


def _run_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_engine = configuration.attributes.get("connection")
    if isinstance(supplied_engine, Engine):
        with supplied_engine.connect() as connection:
            _run_with_connection(connection)
        return

    engine = engine_from_config(
        configuration.get_section(configuration.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with engine.connect() as connection:
            _run_with_connection(connection)
    finally:
        engine.dispose()


run_migrations_online()
