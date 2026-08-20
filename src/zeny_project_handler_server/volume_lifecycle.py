"""Lifecycle fail-closed do volume persistente pertencente ao servidor."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.adapters.persistence import (
    create_sqlite_engine,
    current_database_revision,
    is_known_database_revision,
    latest_database_revision,
    upgrade_database,
    verify_database_integrity,
)
from zeny_project_handler.application.recovery_journal import (
    read_json_object,
    write_json_object_atomic,
)

VOLUME_FORMAT_VERSION = 1
VOLUME_METADATA_FILE_NAME = ".zeny-volume.json"
_METADATA_MAX_BYTES = 4096


class VolumeLifecycleError(RuntimeError):
    """O volume não pode ser liberado com segurança para operações de negócio."""


@dataclass(frozen=True, slots=True)
class VolumePreparationReport:
    """Resultado não sensível da preparação executada antes da prontidão."""

    format_version: int
    previous_database_revision: str | None
    database_revision: str
    migrated: bool


@dataclass(frozen=True, slots=True)
class _VolumeMetadata:
    format_version: int
    database_revision: str
    initialized_at: str
    last_prepared_at: str
    last_migrated_at: str | None


def prepare_server_volume(
    data_directory: Path,
    database_path: Path,
    *,
    now: Callable[[], datetime] | None = None,
) -> VolumePreparationReport:
    """Valide, migre uma única vez quando necessário e publique o manifesto do volume."""
    clock = now or (lambda: datetime.now(UTC))
    root = data_directory.expanduser().resolve()
    database = database_path.expanduser().resolve()
    if database.parent != root:
        raise VolumeLifecycleError("O banco do servidor deve pertencer à raiz do volume")

    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise OSError("volume root is not a directory")
        _verify_writable_root(root)
        metadata_path = root / VOLUME_METADATA_FILE_NAME
        metadata = _read_metadata(metadata_path) if metadata_path.exists() else None
        database_existed = database.is_file()
        if metadata is not None and not database_existed:
            raise VolumeLifecycleError(
                "O manifesto do volume existe, mas o banco canônico está ausente"
            )
        if database_existed:
            _verify_existing_sqlite_file(database)
        engine = create_sqlite_engine(database)
    except VolumeLifecycleError:
        raise
    except Exception as error:
        raise VolumeLifecycleError("O volume do servidor não está gravável ou íntegro") from error

    try:
        previous_revision = _prepare_database(engine, metadata)
        target_revision = latest_database_revision()
        migrated = previous_revision != target_revision
        if migrated:
            upgrade_database(engine, target_revision)
        current_revision = current_database_revision(engine)
        if current_revision != target_revision:
            raise VolumeLifecycleError("A migração não alcançou a revisão exigida por esta imagem")
        verify_database_integrity(engine)
    except VolumeLifecycleError:
        raise
    except Exception as error:
        raise VolumeLifecycleError(
            "A preparação do banco falhou; o servidor permanecerá indisponível"
        ) from error
    finally:
        engine.dispose()

    instant = _utc_text(clock())
    initialized_at = metadata.initialized_at if metadata is not None else instant
    last_migrated_at = (
        instant if migrated else (metadata.last_migrated_at if metadata is not None else None)
    )
    _write_metadata(
        root / VOLUME_METADATA_FILE_NAME,
        _VolumeMetadata(
            format_version=VOLUME_FORMAT_VERSION,
            database_revision=current_revision,
            initialized_at=initialized_at,
            last_prepared_at=instant,
            last_migrated_at=last_migrated_at,
        ),
    )
    return VolumePreparationReport(
        format_version=VOLUME_FORMAT_VERSION,
        previous_database_revision=previous_revision,
        database_revision=current_revision,
        migrated=migrated,
    )


def _prepare_database(engine: Engine, metadata: _VolumeMetadata | None) -> str | None:
    verify_database_integrity(engine)
    revision = current_database_revision(engine)
    if revision is not None and not is_known_database_revision(revision):
        raise VolumeLifecycleError(
            "O volume usa uma revisão de banco incompatível com esta imagem; restaure o backup "
            "correspondente ou use uma imagem compatível"
        )
    if metadata is not None and metadata.database_revision != revision:
        raise VolumeLifecycleError(
            "O manifesto do volume diverge da revisão real do banco; preserve o volume para "
            "recuperação"
        )
    return revision


def _verify_writable_root(root: Path) -> None:
    probe = root / ".zeny-write-probe"
    with sibling_temporary_file(probe) as temporary:
        temporary.write_bytes(b"volume-write-probe")


def _verify_existing_sqlite_file(database: Path) -> None:
    try:
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
            results = tuple(str(item[0]) for item in connection.execute("PRAGMA quick_check"))
    except sqlite3.Error as error:
        raise VolumeLifecycleError(
            "O banco SQLite existente está corrompido ou ilegível"
        ) from error
    if results != ("ok",):
        raise VolumeLifecycleError("O banco SQLite existente falhou na verificação de integridade")


def _read_metadata(path: Path) -> _VolumeMetadata:
    payload = read_json_object(
        path,
        max_bytes=_METADATA_MAX_BYTES,
        error=VolumeLifecycleError,
    )
    expected = {
        "format_version",
        "database_revision",
        "initialized_at",
        "last_prepared_at",
        "last_migrated_at",
    }
    if set(payload) != expected:
        raise VolumeLifecycleError("O manifesto do volume possui estrutura inválida")
    format_version = payload["format_version"]
    if format_version != VOLUME_FORMAT_VERSION:
        raise VolumeLifecycleError(
            "O formato do volume é incompatível com esta imagem; não altere o volume"
        )
    revision = payload["database_revision"]
    initialized_at = payload["initialized_at"]
    last_prepared_at = payload["last_prepared_at"]
    last_migrated_at = payload["last_migrated_at"]
    if (
        not isinstance(revision, str)
        or not revision
        or not isinstance(initialized_at, str)
        or not initialized_at
        or not isinstance(last_prepared_at, str)
        or not last_prepared_at
        or (last_migrated_at is not None and not isinstance(last_migrated_at, str))
    ):
        raise VolumeLifecycleError("O manifesto do volume possui valores inválidos")
    return _VolumeMetadata(
        format_version=format_version,
        database_revision=revision,
        initialized_at=initialized_at,
        last_prepared_at=last_prepared_at,
        last_migrated_at=last_migrated_at,
    )


def _write_metadata(path: Path, metadata: _VolumeMetadata) -> None:
    write_json_object_atomic(
        path,
        {
            "format_version": metadata.format_version,
            "database_revision": metadata.database_revision,
            "initialized_at": metadata.initialized_at,
            "last_prepared_at": metadata.last_prepared_at,
            "last_migrated_at": metadata.last_migrated_at,
        },
        max_bytes=_METADATA_MAX_BYTES,
        error=VolumeLifecycleError,
    )


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise VolumeLifecycleError("O relógio do lifecycle deve fornecer data com timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
