from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zeny_project_handler.adapters.persistence import (
    create_sqlite_engine,
    current_database_revision,
    upgrade_database,
)
from zeny_project_handler.config import DATABASE_FILE_NAME
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.volume_lifecycle import (
    VOLUME_METADATA_FILE_NAME,
    VolumeLifecycleError,
    prepare_server_volume,
)


def _database(root: Path) -> Path:
    return root / DATABASE_FILE_NAME


def test_fresh_volume_migrates_once_and_restart_only_revalidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "volume"
    migration_calls: list[str] = []
    real_upgrade = upgrade_database

    def recording_upgrade(engine, revision: str = "head") -> None:  # type: ignore[no-untyped-def]
        migration_calls.append(revision)
        real_upgrade(engine, revision)

    monkeypatch.setattr(
        "zeny_project_handler_server.volume_lifecycle.upgrade_database",
        recording_upgrade,
    )
    first = prepare_server_volume(
        root,
        _database(root),
        now=lambda: datetime(2026, 8, 20, 21, 0, tzinfo=UTC),
    )
    second = prepare_server_volume(
        root,
        _database(root),
        now=lambda: datetime(2026, 8, 20, 21, 5, tzinfo=UTC),
    )

    assert first.previous_database_revision is None
    assert first.database_revision == "0009_remote_jobs"
    assert first.migrated
    assert not second.migrated
    assert migration_calls == ["0009_remote_jobs"]
    metadata = json.loads((root / VOLUME_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    assert metadata == {
        "database_revision": "0009_remote_jobs",
        "format_version": 1,
        "initialized_at": "2026-08-20T21:00:00Z",
        "last_migrated_at": "2026-08-20T21:00:00Z",
        "last_prepared_at": "2026-08-20T21:05:00Z",
    }
    assert not tuple(root.glob(".z-*.tmp"))


def test_previous_revision_is_upgraded_before_volume_is_published(tmp_path: Path) -> None:
    root = tmp_path / "old-volume"
    engine = create_sqlite_engine(_database(root))
    upgrade_database(engine, "0001_initial")
    engine.dispose()

    report = prepare_server_volume(root, _database(root))

    assert report.previous_database_revision == "0001_initial"
    assert report.database_revision == "0009_remote_jobs"
    engine = create_sqlite_engine(_database(root))
    try:
        assert current_database_revision(engine) == "0009_remote_jobs"
    finally:
        engine.dispose()


def test_future_revision_fails_closed_without_rewriting_volume(tmp_path: Path) -> None:
    root = tmp_path / "future-volume"
    prepare_server_volume(root, _database(root))
    with closing(sqlite3.connect(_database(root))) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '9999_future_schema'")
        connection.commit()
    database_digest = sha256(_database(root).read_bytes()).hexdigest()
    metadata_before = (root / VOLUME_METADATA_FILE_NAME).read_bytes()

    with pytest.raises(VolumeLifecycleError, match="revisão de banco incompatível"):
        prepare_server_volume(root, _database(root))

    assert sha256(_database(root).read_bytes()).hexdigest() == database_digest
    assert (root / VOLUME_METADATA_FILE_NAME).read_bytes() == metadata_before
    with closing(sqlite3.connect(_database(root))) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "9999_future_schema",
        )


def test_corrupted_database_and_newer_volume_format_preserve_existing_bytes(
    tmp_path: Path,
) -> None:
    corrupt_root = tmp_path / "corrupt-volume"
    corrupt_root.mkdir()
    _database(corrupt_root).write_bytes(b"not a sqlite database")

    with pytest.raises(VolumeLifecycleError, match=r"corrompido|preparação|íntegro"):
        prepare_server_volume(corrupt_root, _database(corrupt_root))

    assert _database(corrupt_root).read_bytes() == b"not a sqlite database"
    assert not (corrupt_root / VOLUME_METADATA_FILE_NAME).exists()

    future_root = tmp_path / "future-format"
    prepare_server_volume(future_root, _database(future_root))
    database_before = _database(future_root).read_bytes()
    metadata_path = future_root / VOLUME_METADATA_FILE_NAME
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["format_version"] = 2
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(VolumeLifecycleError, match="formato do volume é incompatível"):
        prepare_server_volume(future_root, _database(future_root))

    assert _database(future_root).read_bytes() == database_before


def test_corrupted_volume_prevents_asgi_startup_and_business_readiness(tmp_path: Path) -> None:
    root = tmp_path / "server-volume"
    root.mkdir()
    _database(root).write_bytes(b"corrupted sqlite")
    application = create_app(
        ServerSettings(
            password="senha do teste fail closed",
            market_sqlserver_connection_string="fixture-market-connection",
            data_directory=root,
        )
    )

    with pytest.raises(VolumeLifecycleError), TestClient(application):
        pass
