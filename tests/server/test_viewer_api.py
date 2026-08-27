from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image

from tests.pdf_fixtures import (
    create_clip_rotation_golden_pdf,
    create_golden_pdf,
    create_protected_pdf,
)
from zeny_project_handler.adapters.pdf.pymupdf_reader import PyMuPdfReader
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha do servidor para testes do viewer"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


def _settings(data: Path) -> ServerSettings:
    return ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        render_dpi=600,
        render_max_pixels=8_000_000,
        render_max_bytes=64 * 1024 * 1024,
        viewer_session_ttl_seconds=60,
    )


def _create_viewer_session(client: TestClient, paths: tuple[Path, ...]) -> Response:
    return client.post(
        "/api/v1/viewer-sessions",
        headers={**AUTH, "Idempotency-Key": "viewer-standalone-1"},
        files=[("files", (path.name, path.read_bytes(), "application/pdf")) for path in paths],
    )


def test_standalone_viewer_raster_parity_rotation_tiles_and_explicit_cleanup(
    tmp_path: Path,
) -> None:
    client_directory = tmp_path / "cliente"
    client_directory.mkdir()
    source = create_clip_rotation_golden_pdf(client_directory / "quadrantes.pdf")
    data = tmp_path / "server"
    application = create_app(_settings(data))
    with TestClient(application, raise_server_exceptions=False) as client:
        unauthorized = client.post(
            "/api/v1/viewer-sessions",
            headers={"Idempotency-Key": "sem-auth"},
            files={"files": (source.name, source.read_bytes(), "application/pdf")},
        )
        assert unauthorized.status_code == 401

        created = _create_viewer_session(client, (source,))
        assert created.status_code == 201, created.text
        payload = created.json()
        session_id = payload["viewer_session_id"]
        document = payload["documents"][0]
        page_id = document["pages"][0]["page_id"]
        assert payload["pending_uploads"] == []
        assert document["display_name"] == source.name
        assert str(source) not in created.text
        session_directory = data / "viewer-sessions" / session_id
        assert len(tuple(session_directory.glob("*.pdf"))) == 1

        preview = client.get(
            f"/api/v1/viewer-pages/{page_id}/preview",
            headers=AUTH,
            params={"dpi": 72, "rotation": 90},
        )
        assert preview.status_code == 200, preview.text
        assert preview.headers["content-type"].startswith("image/png")
        assert preview.headers["x-zeny-page-id"] == page_id
        assert preview.headers["x-zeny-requested-dpi"] == "72"
        assert preview.headers["x-zeny-effective-dpi"] == "72"
        assert preview.headers["x-zeny-rotation"] == "90"
        remote = Image.open(BytesIO(preview.content)).convert("RGB")
        local = PyMuPdfReader().renderizar_pagina(
            source,
            1,
            dpi=72,
            orcamento=OrcamentoRenderizacaoPdf(8_000_000, 64 * 1024 * 1024),
            rotacao_adicional_graus=90,
        )
        assert remote.size == (local.largura_pixels, local.altura_pixels)
        assert remote.tobytes() == bytes(local.dados_rgb)

        tile = client.get(
            f"/api/v1/viewer-pages/{page_id}/tiles",
            headers=AUTH,
            params={
                "x": "0",
                "y": "0",
                "width": "0.5",
                "height": "0.5",
                "dpi": 144,
                "rotation": 270,
            },
        )
        assert tile.status_code == 200, tile.text
        assert tile.headers["x-zeny-clip"] == "0.0,0.0,0.5,0.5"
        assert int(tile.headers["x-zeny-origin-x"]) >= 0
        assert int(tile.headers["x-zeny-origin-y"]) >= 0
        tile_image = Image.open(BytesIO(tile.content))
        assert tile_image.size == (
            int(tile.headers["x-zeny-pixel-width"]),
            int(tile.headers["x-zeny-pixel-height"]),
        )

        closed = client.delete(f"/api/v1/viewer-sessions/{session_id}", headers=AUTH)
        assert closed.status_code == 200
        assert closed.json()["closed"] is True
        assert not session_directory.exists()
        assert client.get(f"/api/v1/viewer-pages/{page_id}", headers=AUTH).status_code == 404


def test_standalone_password_attempts_ttl_and_secret_absence(tmp_path: Path) -> None:
    pdf_password = "segredo PDF somente memoria"
    source = create_protected_pdf(tmp_path / "protegido.pdf", pdf_password)
    data = tmp_path / "data"
    application = create_app(_settings(data))
    with TestClient(application) as client:
        created = _create_viewer_session(client, (source,))
        assert created.status_code == 201
        body = created.json()
        session_id = body["viewer_session_id"]
        pending = body["pending_uploads"][0]
        assert body["documents"] == []
        assert pending["password_attempts_remaining"] == 3
        assert pdf_password not in created.text

        wrong = client.post(
            f"/api/v1/viewer-sessions/{session_id}/uploads/{pending['upload_id']}/unlock",
            headers=AUTH,
            json={"password": "incorreta"},
        )
        assert wrong.status_code == 409
        assert wrong.json()["code"] == "PDF_PASSWORD_INVALID"
        assert wrong.json()["details"]["password_attempts_remaining"] == 2
        unlocked = client.post(
            f"/api/v1/viewer-sessions/{session_id}/uploads/{pending['upload_id']}/unlock",
            headers=AUTH,
            json={"password": pdf_password},
        )
        assert unlocked.status_code == 200, unlocked.text
        assert len(unlocked.json()["documents"]) == 1
        assert unlocked.json()["pending_uploads"] == []
        assert pdf_password not in unlocked.text

        runtime = cast(ServerRuntime, application.state.runtime)
        assert runtime.viewer_api is not None
        temporary = runtime.viewer_api._sessions[next(iter(runtime.viewer_api._sessions))]
        page_id = unlocked.json()["documents"][0]["pages"][0]["page_id"]
        temporary.expires_monotonic = 0
        assert runtime.viewer_api.cleanup_expired() == 1
        expired = client.get(f"/api/v1/viewer-pages/{page_id}", headers=AUTH)
        assert expired.status_code == 410
        assert expired.json()["code"] == "VIEWER_SESSION_EXPIRED"

    for path in data.rglob("*"):
        if path.is_file():
            assert pdf_password.encode() not in path.read_bytes()


def test_project_viewer_uses_managed_source_and_detects_source_change(tmp_path: Path) -> None:
    source = create_golden_pdf(tmp_path / "original.pdf")
    data = tmp_path / "data"
    application = create_app(_settings(data))
    with TestClient(application, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/projects",
            headers={**AUTH, "Idempotency-Key": "project-viewer"},
            json={"service_note": "0001234567"},
        )
        project_id = created.json()["project"]["project_id"]
        uploaded = client.post(
            f"/api/v1/projects/{project_id}/document-uploads",
            headers={**AUTH, "Idempotency-Key": "project-viewer-pdf"},
            files={"file": (source.name, source.read_bytes(), "application/pdf")},
        )
        assert uploaded.status_code == 201
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"]
        document_id = detail["documents"][0]["document_id"]
        source.unlink()

        viewer = client.get(f"/api/v1/projects/{project_id}/viewer", headers=AUTH)
        assert viewer.status_code == 200, viewer.text
        page_id = viewer.json()["pages"][0]["page_id"]
        raster = client.get(
            f"/api/v1/viewer-pages/{page_id}/preview",
            headers=AUTH,
            params={"dpi": 72},
        )
        assert raster.status_code == 200

        managed = data / "project-files" / project_id / "documents" / f"{document_id}.pdf"
        managed.write_bytes(managed.read_bytes() + b"\n")
        changed = client.get(
            f"/api/v1/viewer-pages/{page_id}/preview",
            headers=AUTH,
            params={"dpi": 72},
        )
        assert changed.status_code == 409
        assert changed.json()["code"] == "PDF_SOURCE_CHANGED"


def test_project_viewer_requests_password_again_after_server_restart(tmp_path: Path) -> None:
    pdf_password = "senha protegida do projeto"
    protected = create_protected_pdf(tmp_path / "projeto-protegido.pdf", pdf_password)
    data = tmp_path / "data"
    settings = _settings(data)
    first = create_app(settings)
    with TestClient(first) as client:
        created = client.post(
            "/api/v1/projects",
            headers={**AUTH, "Idempotency-Key": "protected-viewer-project"},
            json={"service_note": "0007654321"},
        )
        project_id = created.json()["project"]["project_id"]
        uploaded = client.post(
            f"/api/v1/projects/{project_id}/document-uploads",
            headers={**AUTH, "Idempotency-Key": "protected-viewer-upload"},
            files={"file": (protected.name, protected.read_bytes(), "application/pdf")},
        )
        upload_id = uploaded.json()["upload_id"]
        imported = client.post(
            f"/api/v1/uploads/{upload_id}/unlock",
            headers=AUTH,
            json={"password": pdf_password},
        )
        assert imported.status_code == 200

    restarted = create_app(settings)
    with TestClient(restarted, raise_server_exceptions=False) as client:
        viewer = client.get(f"/api/v1/projects/{project_id}/viewer", headers=AUTH)
        page_id = viewer.json()["pages"][0]["page_id"]
        document_id = viewer.json()["documents"][0]["document_id"]
        locked = client.get(
            f"/api/v1/viewer-pages/{page_id}/preview",
            headers=AUTH,
            params={"dpi": 72},
        )
        assert locked.status_code == 409
        assert locked.json()["code"] == "PDF_PASSWORD_REQUIRED"
        wrong = client.post(
            f"/api/v1/viewer-documents/{document_id}/unlock",
            headers=AUTH,
            json={"password": "incorreta"},
        )
        assert wrong.status_code == 409
        assert wrong.json()["code"] == "PDF_PASSWORD_INVALID"
        unlocked = client.post(
            f"/api/v1/viewer-documents/{document_id}/unlock",
            headers=AUTH,
            json={"password": pdf_password},
        )
        assert unlocked.status_code == 200
        rendered = client.get(
            f"/api/v1/viewer-pages/{page_id}/preview",
            headers=AUTH,
            params={"dpi": 72},
        )
        assert rendered.status_code == 200
        assert pdf_password not in unlocked.text
