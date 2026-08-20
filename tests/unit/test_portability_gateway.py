from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from zeny_project_handler_client.ui.portability_gateway import (
    HttpPortabilityGateway,
    PortabilityGatewayError,
)
from zeny_project_handler_contracts.base import DownloadId
from zeny_project_handler_contracts.common import DownloadMetadataDto
from zeny_project_handler_contracts.errors import ErrorCode


class InterruptedResponse:
    status = 200

    def __init__(self) -> None:
        self.reads = 0

    def getheaders(self) -> tuple[tuple[str, str], ...]:
        return ()

    def read(self, _size: int = -1) -> bytes:
        self.reads += 1
        if self.reads == 1:
            return b"parte do download"
        raise ConnectionResetError("servidor desconectou")


class InterruptedConnection:
    def __init__(self) -> None:
        self.response = InterruptedResponse()
        self.closed = False

    def request(self, *_args: object, **_kwargs: object) -> None:
        return None

    def getresponse(self) -> InterruptedResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_interrupted_download_preserves_previous_destination_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = HttpPortabilityGateway("http://127.0.0.1:8765", "segredo")
    destination = tmp_path / "project.zphproj"
    destination.write_bytes(b"previous-published-version")
    download_id = uuid4()
    metadata = DownloadMetadataDto(
        download_id=DownloadId(download_id),
        file_name="project.zphproj",
        mime_type="application/octet-stream",
        size_bytes=100,
        sha256="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    connection = InterruptedConnection()
    monkeypatch.setattr(
        HttpPortabilityGateway,
        "get_download_metadata",
        lambda _self, _download_id: metadata,
    )
    monkeypatch.setattr(HttpPortabilityGateway, "_connection", lambda _self: connection)

    with pytest.raises(PortabilityGatewayError) as failure:
        gateway.download_to(
            download_id,
            destination,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )

    assert failure.value.code is ErrorCode.INTERNAL_ERROR
    assert destination.read_bytes() == b"previous-published-version"
    assert not tuple(tmp_path.glob(".z-*.tmp"))
    assert connection.closed


def test_interrupted_upload_is_not_retried_and_keeps_client_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "project.zphproj"
    source.write_bytes(b"x" * (1024 * 1024 + 10))
    attempts = 0

    def interrupt(
        _self: HttpPortabilityGateway,
        _method: str,
        _path: str,
        *,
        headers: Mapping[str, str],
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        nonlocal attempts
        attempts += 1
        assert headers["Idempotency-Key"] == "upload-network-failure"
        assert body is not None and not isinstance(body, bytes)
        iterator = iter(body)
        next(iterator)
        next(iterator)
        raise ConnectionResetError("rede caiu durante upload")

    monkeypatch.setattr(HttpPortabilityGateway, "_request_once", interrupt)
    gateway = HttpPortabilityGateway("http://127.0.0.1:8765", "segredo")

    with pytest.raises(PortabilityGatewayError) as failure:
        gateway.preflight_project_import(
            source,
            idempotency_key="upload-network-failure",
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )

    assert failure.value.code is ErrorCode.INTERNAL_ERROR
    assert attempts == 1
    assert sha256(source.read_bytes()).hexdigest() == sha256(b"x" * (1024 * 1024 + 10)).hexdigest()
