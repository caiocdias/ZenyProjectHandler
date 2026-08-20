"""Backup consistente do SQLite com publicação atômica no destino."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing, suppress
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.ports.portability import ResumoSnapshotBackup

from .errors import PersistenceError


def create_atomic_backup(database_path: Path, destination: Path) -> Path:
    """Copie um snapshot consistente e substitua o destino somente após validação."""
    try:
        source_path = database_path.expanduser().resolve()
        target_path = destination.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise PersistenceError("Caminho do backup SQLite é inválido") from error
    if not source_path.is_file():
        raise PersistenceError("Banco de dados de origem não existe")
    if source_path == target_path:
        raise PersistenceError("Backup deve usar um caminho diferente do banco de origem")

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with sibling_temporary_file(target_path) as temporary_path:
            try:
                with (
                    closing(sqlite3.connect(source_path)) as source,
                    closing(sqlite3.connect(temporary_path)) as target,
                ):
                    source.backup(target)
                    integrity = target.execute("PRAGMA integrity_check").fetchone()
                    if integrity != ("ok",):
                        raise PersistenceError(
                            "Snapshot SQLite falhou na verificação de integridade"
                        )
                    target.commit()
                os.replace(temporary_path, target_path)
            finally:
                _remove_sqlite_sidecars(temporary_path)
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError(
            "Não foi possível criar o backup SQLite no destino informado"
        ) from error
    return target_path


def restore_atomic_backup(source: Path, database_path: Path) -> Path:
    """Valide um snapshot e publique uma cópia nova no caminho do banco local."""
    try:
        source_path = source.expanduser().resolve()
        target_path = database_path.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise PersistenceError("Caminho da recuperação SQLite é inválido") from error
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

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with sibling_temporary_file(target_path) as temporary_path:
            try:
                with (
                    closing(sqlite3.connect(source_path)) as snapshot,
                    closing(sqlite3.connect(temporary_path)) as restored,
                ):
                    snapshot.backup(restored)
                    restored.commit()
                    integrity = restored.execute("PRAGMA integrity_check").fetchone()
                    if integrity != ("ok",):
                        raise PersistenceError(
                            "Banco restaurado falhou na verificação de integridade"
                        )
                os.replace(temporary_path, target_path)
            finally:
                _remove_sqlite_sidecars(temporary_path)
        _remove_sqlite_sidecars(target_path)
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError(
            "Não foi possível restaurar o banco SQLite no destino informado"
        ) from error
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


def inspect_backup_snapshot(snapshot: Path) -> ResumoSnapshotBackup:
    """Valide e resuma um snapshot sem alterar seu conteúdo."""
    source = snapshot.expanduser().resolve()
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise PersistenceError("Snapshot de recuperação está corrompido")
            project_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute("SELECT id FROM projects ORDER BY id")
            )
            document_count = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            photo_count = 0
            for (payload,) in connection.execute("SELECT payload FROM elements"):
                decoded = json.loads(str(payload))
                photos = decoded.get("fotos", []) if isinstance(decoded, dict) else []
                if isinstance(photos, list):
                    photo_count += len(photos)
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        raise PersistenceError("Não foi possível inspecionar o snapshot de recuperação") from error
    return ResumoSnapshotBackup(
        projetos_ids=project_ids,
        quantidade_documentos=document_count,
        quantidade_fotos=photo_count,
    )


def fingerprint_database(database_path: Path) -> str:
    """Assine o estado persistente ignorando apenas journals HTTP voláteis de jobs."""
    source = database_path.expanduser().resolve()
    digest = sha256()
    excluded = {"api_idempotency_records", "api_jobs", "sqlite_sequence"}
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise PersistenceError("Banco atual falhou na verificação de integridade")
            tables = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                if str(row[0]) not in excluded
            )
            for table in tables:
                quoted = table.replace('"', '""')
                columns = tuple(
                    str(row[1]) for row in connection.execute(f'PRAGMA table_info("{quoted}")')
                )
                digest.update(table.encode("utf-8"))
                digest.update(b"\0")
                digest.update("\x1f".join(columns).encode("utf-8"))
                digest.update(b"\0")
                rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()
                canonical_rows = sorted(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
                    for row in rows
                )
                for row in canonical_rows:
                    digest.update(row.encode("utf-8"))
                    digest.update(b"\0")
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError("Não foi possível assinar o estado do banco") from error
    return digest.hexdigest()


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-journal", "-wal", "-shm"):
        with suppress(OSError):
            path.with_name(path.name + suffix).unlink(missing_ok=True)


class SqliteBackupManager:
    def criar_snapshot(self, banco: Path, destino: Path) -> Path:
        return create_atomic_backup(banco, destino)

    def restaurar_snapshot(self, origem: Path, banco: Path) -> Path:
        return restore_atomic_backup(origem, banco)

    def preparar_origens_pdf(self, snapshot: Path, caminhos: dict[UUID, Path]) -> None:
        rewrite_backup_pdf_sources(snapshot, caminhos)

    def inspecionar_snapshot(self, snapshot: Path) -> ResumoSnapshotBackup:
        return inspect_backup_snapshot(snapshot)

    def fingerprint_banco(self, banco: Path) -> str:
        return fingerprint_database(banco)
