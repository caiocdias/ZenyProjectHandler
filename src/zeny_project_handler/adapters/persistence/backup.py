"""Backup consistente do SQLite com publicação atômica no destino."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing, suppress
from pathlib import Path
from uuid import UUID, uuid4

from .errors import PersistenceError


def create_atomic_backup(database_path: Path, destination: Path) -> Path:
    """Copie um snapshot consistente e substitua o destino somente após validação."""
    source_path = database_path.expanduser().resolve()
    target_path = destination.expanduser().resolve()
    if not source_path.is_file():
        raise PersistenceError("Banco de dados de origem não existe")
    if source_path == target_path:
        raise PersistenceError("Backup deve usar um caminho diferente do banco de origem")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        with (
            closing(sqlite3.connect(source_path)) as source,
            closing(sqlite3.connect(temporary_path)) as target,
        ):
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise PersistenceError("Snapshot SQLite falhou na verificação de integridade")
            target.commit()
        os.replace(temporary_path, target_path)
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError("Não foi possível criar o backup SQLite") from error
    finally:
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)
    return target_path


def restore_atomic_backup(source: Path, database_path: Path) -> Path:
    """Valide um snapshot e publique uma cópia nova no caminho do banco local."""
    source_path = source.expanduser().resolve()
    target_path = database_path.expanduser().resolve()
    if not source_path.is_file():
        raise PersistenceError("Snapshot de recuperação não existe")
    if source_path == target_path:
        raise PersistenceError("Recuperação deve usar um snapshot separado do banco atual")
    try:
        with closing(sqlite3.connect(source_path)) as snapshot:
            integrity = snapshot.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise PersistenceError("Snapshot de recuperação está corrompido")
    except sqlite3.Error as error:
        raise PersistenceError("Não foi possível validar o snapshot de recuperação") from error

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.restore")
    try:
        with (
            closing(sqlite3.connect(source_path)) as snapshot,
            closing(sqlite3.connect(temporary_path)) as restored,
        ):
            snapshot.backup(restored)
            restored.commit()
            integrity = restored.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise PersistenceError("Banco restaurado falhou na verificação de integridade")
        os.replace(temporary_path, target_path)
        for suffix in ("-wal", "-shm"):
            with suppress(OSError):
                target_path.with_name(target_path.name + suffix).unlink(missing_ok=True)
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError("Não foi possível restaurar o banco SQLite") from error
    finally:
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)
    return target_path


def rewrite_backup_pdf_sources(snapshot: Path, paths: dict[UUID, Path]) -> None:
    """Aponte origens PDF do snapshot para as cópias gerenciadas restauráveis."""
    snapshot_path = snapshot.expanduser().resolve()
    try:
        with closing(sqlite3.connect(snapshot_path)) as connection:
            connection.executemany(
                "UPDATE document_sources SET canonical_path = ? WHERE document_id = ?",
                [
                    (str(path.expanduser().resolve()), str(document_id))
                    for document_id, path in paths.items()
                ],
            )
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise PersistenceError("Snapshot alterado falhou na verificação de integridade")
    except sqlite3.Error as error:
        raise PersistenceError("Não foi possível preparar as origens PDF do backup") from error


class SqliteBackupManager:
    def criar_snapshot(self, banco: Path, destino: Path) -> Path:
        return create_atomic_backup(banco, destino)

    def restaurar_snapshot(self, origem: Path, banco: Path) -> Path:
        return restore_atomic_backup(origem, banco)

    def preparar_origens_pdf(self, snapshot: Path, caminhos: dict[UUID, Path]) -> None:
        rewrite_backup_pdf_sources(snapshot, caminhos)
