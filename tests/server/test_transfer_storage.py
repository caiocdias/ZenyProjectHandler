from __future__ import annotations

import asyncio
from pathlib import Path
from time import sleep
from typing import cast
from uuid import uuid4

import pytest
from fastapi import UploadFile

from zeny_project_handler_server.api_errors import ApiError
from zeny_project_handler_server.transfer_storage import ManagedTransferStorage


class InterruptedUpload:
    filename = "interrompido.zphproj"
    content_type = "application/octet-stream"

    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    async def read(self, _size: int) -> bytes:
        self.reads += 1
        if self.reads == 1:
            return b"parte recebida"
        raise ConnectionResetError("cliente desconectou durante upload")

    async def close(self) -> None:
        self.closed = True


def test_interrupted_upload_removes_partial_artifact(tmp_path: Path) -> None:
    storage = ManagedTransferStorage(tmp_path, maximum_bytes=1024, ttl_seconds=60)
    upload = InterruptedUpload()

    with pytest.raises(ConnectionResetError, match="desconectou"):
        asyncio.run(
            storage.receive(
                cast(UploadFile, upload),
                expected_suffix=".zphproj",
            )
        )

    assert upload.closed
    assert not tuple(storage.incoming_root.iterdir())


def test_download_survives_storage_restart_then_expires_by_ttl(tmp_path: Path) -> None:
    storage = ManagedTransferStorage(tmp_path, maximum_bytes=1024, ttl_seconds=1)
    pending = storage.pending_download_path(uuid4(), ".zphproj")
    pending.write_bytes(b"download persistente")
    metadata = storage.publish_download(
        pending,
        file_name="project.zphproj",
        mime_type="application/octet-stream",
    )

    restarted = ManagedTransferStorage(tmp_path, maximum_bytes=1024, ttl_seconds=1)
    assert restarted.get_download(metadata.download_id.root).path.read_bytes() == (
        b"download persistente"
    )
    sleep(1.05)

    with pytest.raises(ApiError) as expired:
        restarted.get_download(metadata.download_id.root)
    assert expired.value.status_code == 404
    assert not tuple(restarted.download_root.iterdir())


def test_startup_cleanup_removes_interrupted_incoming_and_pending_files(tmp_path: Path) -> None:
    storage = ManagedTransferStorage(tmp_path, maximum_bytes=1024, ttl_seconds=60)
    (storage.incoming_root / "abandoned.part").write_bytes(b"partial upload")
    (storage.pending_download_root / "abandoned.zphbackup").write_bytes(b"partial job")

    restarted = ManagedTransferStorage(tmp_path, maximum_bytes=1024, ttl_seconds=60)

    assert not tuple(restarted.incoming_root.iterdir())
    assert not tuple(restarted.pending_download_root.iterdir())
