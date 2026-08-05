"""Adaptadores de persistência local."""

from zeny_project_handler.config import DATABASE_FILE_NAME

from .backup import (
    SqliteBackupManager,
    create_atomic_backup,
    restore_atomic_backup,
    rewrite_backup_pdf_sources,
)
from .database import (
    create_sqlite_engine,
    current_database_revision,
    managed_sqlite_engine,
    upgrade_database,
)
from .portable_database import SqlitePortableProjectDatabase
from .unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "DATABASE_FILE_NAME",
    "SqlAlchemyUnitOfWork",
    "SqliteBackupManager",
    "SqlitePortableProjectDatabase",
    "create_atomic_backup",
    "create_sqlite_engine",
    "current_database_revision",
    "managed_sqlite_engine",
    "restore_atomic_backup",
    "rewrite_backup_pdf_sources",
    "upgrade_database",
]
