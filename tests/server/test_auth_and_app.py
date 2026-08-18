from __future__ import annotations

import hmac
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from zeny_project_handler_contracts import (
    API_VERSION,
    MAX_COMPATIBLE_API_VERSION,
    MIN_COMPATIBLE_API_VERSION,
)
from zeny_project_handler_contracts.enums import OcrStatus
from zeny_project_handler_contracts.session import (
    OcrDiagnosticDto,
    SessionCapabilitiesResponse,
)
from zeny_project_handler_server.app import CORRELATION_HEADER, create_app
from zeny_project_handler_server.composition import JobLifecycle, ServerRuntimeProtocol
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha correta somente para teste"


class FakeRuntime:
    def __init__(self) -> None:
        self.closed = False
        self.project_api = None
        self.viewer_api = None
        self.review_api = None
        self.jobs = cast(JobLifecycle, FakeJobs())

    def session_capabilities(self) -> SessionCapabilitiesResponse:
        return SessionCapabilitiesResponse(
            server_version="0.1.0",
            api_version=API_VERSION,
            min_compatible_api_version=MIN_COMPATIBLE_API_VERSION,
            max_compatible_api_version=MAX_COMPATIBLE_API_VERSION,
            ready=True,
            capabilities=("authenticated-session", "persistent-storage"),
            ocr=OcrDiagnosticDto(
                status=OcrStatus.AVAILABLE,
                engine="tesseract",
                language="por+eng",
                message="OCR disponível.",
            ),
            server_time=datetime(2026, 8, 17, 22, 0, tzinfo=UTC),
        )

    def close(self) -> None:
        self.closed = True


class FakeJobs:
    def global_operation(self) -> None:
        return None


def _settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(password=PASSWORD, data_directory=tmp_path)


def test_health_is_public_and_session_has_uniform_401_or_authenticated_200(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()

    def runtime_factory(_settings: ServerSettings) -> ServerRuntimeProtocol:
        return runtime

    application = create_app(_settings(tmp_path), runtime_factory=runtime_factory)
    with TestClient(application) as client:
        health = client.get("/health/live")
        missing = client.get("/api/v1/session")
        wrong = client.get(
            "/api/v1/session",
            headers={"Authorization": "Bearer senha-incorreta"},
        )
        accepted = client.get(
            "/api/v1/session",
            headers={"Authorization": f"Bearer {PASSWORD}"},
        )

    assert runtime.closed
    assert health.status_code == 200
    assert health.json() == {"live": True}
    assert set(health.json()) == {"live"}
    assert health.headers[CORRELATION_HEADER]
    assert missing.status_code == wrong.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert wrong.headers["WWW-Authenticate"] == "Bearer"
    missing_body = missing.json()
    wrong_body = wrong.json()
    assert missing_body["code"] == wrong_body["code"] == "AUTHENTICATION_FAILED"
    assert missing_body["message"] == wrong_body["message"]
    assert missing_body.get("details") == wrong_body.get("details") is None
    assert missing_body["correlation_id"] != wrong_body["correlation_id"]
    assert accepted.status_code == 200
    assert accepted.json()["ready"] is True
    assert accepted.json()["api_version"] == API_VERSION
    serialized = accepted.text
    assert PASSWORD not in serialized
    assert str(tmp_path) not in serialized


def test_authentication_uses_constant_time_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    comparisons: list[tuple[bytes, bytes]] = []

    def compare_digest(supplied: bytes, expected: bytes) -> bool:
        comparisons.append((supplied, expected))
        return supplied == expected

    monkeypatch.setattr(hmac, "compare_digest", compare_digest)
    runtime = FakeRuntime()

    def runtime_factory(_settings: ServerSettings) -> ServerRuntimeProtocol:
        return runtime

    application = create_app(_settings(tmp_path), runtime_factory=runtime_factory)
    with TestClient(application) as client:
        response = client.get(
            "/api/v1/session",
            headers={"Authorization": f"Bearer {PASSWORD}"},
        )

    assert response.status_code == 200
    assert comparisons == [(PASSWORD.encode(), PASSWORD.encode())]


def test_create_app_fails_closed_before_startup_without_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENY_SERVER_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="ZENY_SERVER_PASSWORD"):
        create_app()
