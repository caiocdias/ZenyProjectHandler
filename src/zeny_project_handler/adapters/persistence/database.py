"""Criação segura do engine SQLite e execução programática das migrações."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, event
from sqlalchemy.engine import create_engine

from .errors import PersistenceError

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


def latest_database_revision() -> str:
    """Retorne o único ``head`` suportado pelo runtime empacotado."""
    script = ScriptDirectory.from_config(_migration_configuration())
    heads = script.get_heads()
    if len(heads) != 1:
        raise PersistenceError("O histórico de migrações não possui um único head suportado")
    return heads[0]


def is_known_database_revision(revision: str) -> bool:
    """Informe se uma revisão pertence ao histórico embarcado nesta imagem."""
    script = ScriptDirectory.from_config(_migration_configuration())
    try:
        return script.get_revision(revision) is not None
    except Exception:
        return False


def verify_database_integrity(engine: Engine) -> None:
    """Falhe fechado quando o SQLite não passar pelo ``quick_check`` de startup."""
    try:
        with engine.connect() as connection:
            results = tuple(
                str(item) for item in connection.exec_driver_sql("PRAGMA quick_check").scalars()
            )
    except Exception as error:
        raise PersistenceError("O banco SQLite não pôde ser verificado") from error
    if results != ("ok",):
        raise PersistenceError("O banco SQLite falhou na verificação de integridade")


def current_database_revision(engine: Engine) -> str | None:
    """Leia a revisão sem modificar o banco."""
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _migration_configuration() -> Config:
    configuration = Config()
    configuration.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    return configuration
