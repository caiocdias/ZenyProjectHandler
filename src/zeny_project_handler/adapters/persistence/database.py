"""Criação segura do engine SQLite e execução programática das migrações."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlalchemy.engine import create_engine

MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


def create_sqlite_engine(database_path: Path) -> Engine:
    """Crie o engine; quem chama passa a ser responsável por ``dispose()``."""
    resolved_path = database_path.expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{resolved_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=FULL")
        finally:
            cursor.close()

    return engine


@contextmanager
def managed_sqlite_engine(database_path: Path) -> Iterator[Engine]:
    """Delimite explicitamente o ownership de um engine SQLite temporário."""
    engine = create_sqlite_engine(database_path)
    try:
        yield engine
    finally:
        engine.dispose()


def upgrade_database(engine: Engine, revision: str = "head") -> None:
    """Atualize o banco usando o histórico Alembic embarcado no pacote."""
    configuration = Config()
    configuration.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    configuration.attributes["connection"] = engine
    command.upgrade(configuration, revision)


def current_database_revision(engine: Engine) -> str | None:
    """Leia a revisão sem modificar o banco."""
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()
