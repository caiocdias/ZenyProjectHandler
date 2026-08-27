from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image
from sqlalchemy import update

from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf, create_protected_pdf
from zeny_project_handler.adapters.pdf.pymupdf_reader import PyMuPdfReader
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork, create_sqlite_engine
from zeny_project_handler.adapters.persistence.schema import api_uploads
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto
from zeny_project_handler.domain.project import Poste
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.upload_storage import ManagedUploadStorage, ReceivedUpload

PASSWORD = "senha do servidor para testes da etapa tres"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


def _settings(data_directory: Path, *, upload_max_bytes: int = 8 * 1024 * 1024) -> ServerSettings:
    return ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data_directory,
        upload_max_bytes=upload_max_bytes,
    )


def _create_project(client: TestClient, *, key: str = "create-project-1") -> dict[str, object]:
    response = client.post(
        "/api/v1/projects",
        headers={**AUTH, "Idempotency-Key": key},
        json={"service_note": "0001234567"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json()["project"])


def _upload_pdf(
    client: TestClient,
    project_id: str,
    source: Path,
    *,
    key: str,
    display_name: str | None = None,
) -> Response:
    return client.post(
        f"/api/v1/projects/{project_id}/document-uploads",
        headers={**AUTH, "Idempotency-Key": key},
        files={
            "file": (
                display_name or source.name,
                source.read_bytes(),
                "application/pdf",
            )
        },
    )


def test_project_crud_managed_upload_idempotency_order_and_restart(tmp_path: Path) -> None:
    data = tmp_path / "server-data"
    local = tmp_path / "client-files"
    local.mkdir()
    first_pdf = create_golden_pdf(local / "primeira-folha.pdf")
    second_pdf = create_feature_pdf(local / "segunda-folha.pdf")
    first_pdf_bytes = first_pdf.read_bytes()
    settings = _settings(data)
    application = create_app(settings)

    with TestClient(application) as client:
        created = _create_project(client)
        project_id = str(created["project_id"])
        repeated = _create_project(client)
        assert repeated["project_id"] == project_id
        assert client.get("/api/v1/projects", headers=AUTH).json()["page"]["total"] == 1

        conflict = client.post(
            "/api/v1/projects",
            headers={**AUTH, "Idempotency-Key": "create-project-1"},
            json={"service_note": "0007654321"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

        first = _upload_pdf(client, project_id, first_pdf, key="upload-1")
        assert first.status_code == 201
        assert first.json()["state"] == "IMPORTED"
        replay = _upload_pdf(client, project_id, first_pdf, key="upload-1")
        assert replay.status_code == 201
        assert replay.json() == first.json()

        duplicate = _upload_pdf(client, project_id, first_pdf, key="upload-duplicate")
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "OPERATION_CONFLICT"

        second = _upload_pdf(client, project_id, second_pdf, key="upload-2")
        assert second.status_code == 201
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert detail.status_code == 200
        payload = detail.json()["project"]
        assert len(payload["documents"]) == 2
        assert str(data) not in detail.text
        assert str(local) not in detail.text
        page_ids = [item["page_id"] for item in payload["pages"]]
        version = payload["project_version"]

        reordered = client.put(
            f"/api/v1/projects/{project_id}/page-order",
            headers=AUTH,
            json={
                "page_ids": list(reversed(page_ids)),
                "expected_project_version": version,
            },
        )
        assert reordered.status_code == 200
        assert [item["page_id"] for item in reordered.json()["pages"]] == list(reversed(page_ids))
        stale = client.put(
            f"/api/v1/projects/{project_id}/page-order",
            headers=AUTH,
            json={"page_ids": page_ids, "expected_project_version": version},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "STALE_STATE"

    first_pdf.unlink()
    second_pdf.unlink()
    restarted = create_app(settings)
    with TestClient(restarted) as client:
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert detail.status_code == 200
        project = detail.json()["project"]
        assert len(project["documents"]) == 2
        assert [item["page_id"] for item in project["pages"]] == list(reversed(page_ids))
        for item in project["documents"]:
            assert set(item["file"]) == {"display_name", "mime_type", "size_bytes", "sha256"}
        assert not any("canonical" in key or "path" in key for key in _all_json_keys(project))
        replay_after_restart = client.post(
            f"/api/v1/projects/{project_id}/document-uploads",
            headers={**AUTH, "Idempotency-Key": "upload-1"},
            files={"file": ("primeira-folha.pdf", first_pdf_bytes, "application/pdf")},
        )
        assert replay_after_restart.status_code == 201
        assert replay_after_restart.json()["upload_id"] == first.json()["upload_id"]
        assert (
            len(
                client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"][
                    "documents"
                ]
            )
            == 2
        )

        first_document_id = project["documents"][0]["document_id"]
        managed_pdf = data / "project-files" / project_id / "documents" / f"{first_document_id}.pdf"
        assert PyMuPdfReader().inspecionar(managed_pdf).documento.paginas
        removed = client.delete(
            f"/api/v1/projects/{project_id}/documents/{first_document_id}",
            headers=AUTH,
        )
        assert removed.status_code == 200
        assert removed.json()["removed_page_count"] >= 1
        assert not managed_pdf.exists()

        current = client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"]
        changed = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=AUTH,
            json={
                "service_note": "0007654321",
                "expected_project_version": current["project_version"],
            },
        )
        assert changed.status_code == 200
        assert changed.json()["project"]["service_note"] == "0007654321"
        deleted = client.delete(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert deleted.status_code == 200
        assert deleted.json()["counts"]["documents"] == 1
        assert client.get(f"/api/v1/projects/{project_id}", headers=AUTH).status_code == 404
        assert not (data / "project-files" / project_id).exists()


def test_protected_pdf_attempts_restart_and_absence_of_secret(tmp_path: Path) -> None:
    data = tmp_path / "server-data"
    secret = "senha-pdf-super-secreta"
    protected = create_protected_pdf(tmp_path / "cliente-protegido.pdf", secret)
    settings = _settings(data)
    first_app = create_app(settings)

    with TestClient(first_app) as client:
        project = _create_project(client, key="protected-project")
        project_id = str(project["project_id"])
        uploaded = _upload_pdf(client, project_id, protected, key="protected-upload")
        assert uploaded.status_code == 201
        body = uploaded.json()
        assert body["state"] == "PASSWORD_REQUIRED"
        assert body["preflight"]["password_required"] is True
        upload_id = body["upload_id"]
        assert secret not in uploaded.text
        assert (
            client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"][
                "documents"
            ]
            == []
        )

    second_app = create_app(settings)
    with TestClient(second_app) as client:
        wrong = client.post(
            f"/api/v1/uploads/{upload_id}/unlock",
            headers=AUTH,
            json={"password": "incorreta"},
        )
        assert wrong.status_code == 422
        assert wrong.json()["code"] == "PDF_PASSWORD_INVALID"
        assert wrong.json()["details"]["password_attempts_remaining"] == 2
        accepted = client.post(
            f"/api/v1/uploads/{upload_id}/unlock",
            headers=AUTH,
            json={"password": secret},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "IMPORTED"
        runtime = cast(ServerRuntime, second_app.state.runtime)
        assert runtime.project_api is not None
        assert runtime.project_api.credential_count == 1
        assert secret not in accepted.text

    for path in data.rglob("*"):
        if path.is_file():
            assert secret.encode("utf-8") not in path.read_bytes(), path

    third_app = create_app(settings)
    with TestClient(third_app) as client:
        runtime = cast(ServerRuntime, third_app.state.runtime)
        assert runtime.project_api is not None
        assert runtime.project_api.credential_count == 0
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert len(detail.json()["project"]["documents"]) == 1


def test_protected_pdf_rejects_and_deletes_pending_content_after_three_attempts(
    tmp_path: Path,
) -> None:
    data = tmp_path / "server-data"
    protected = create_protected_pdf(tmp_path / "tres-tentativas.pdf", "correta")
    application = create_app(_settings(data))
    with TestClient(application) as client:
        project_id = str(_create_project(client, key="attempt-project")["project_id"])
        uploaded = _upload_pdf(client, project_id, protected, key="attempt-upload")
        upload_id = uploaded.json()["upload_id"]
        for remaining in (2, 1, 0):
            response = client.post(
                f"/api/v1/uploads/{upload_id}/unlock",
                headers=AUTH,
                json={"password": "incorreta"},
            )
            assert response.status_code == 422
            assert response.json()["details"]["password_attempts_remaining"] == remaining
        exhausted = client.post(
            f"/api/v1/uploads/{upload_id}/unlock",
            headers=AUTH,
            json={"password": "correta"},
        )
        assert exhausted.status_code == 409
        assert (
            client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"][
                "documents"
            ]
            == []
        )
    assert list((data / "uploads" / "pending").glob("*.pdf")) == []


def test_restart_expires_abandoned_protected_upload_without_orphan(tmp_path: Path) -> None:
    data = tmp_path / "server-data"
    protected = create_protected_pdf(tmp_path / "abandonado.pdf", "correta")
    settings = _settings(data)
    application = create_app(settings)
    with TestClient(application) as client:
        project_id = str(_create_project(client, key="abandoned-project")["project_id"])
        uploaded = _upload_pdf(client, project_id, protected, key="abandoned-upload")
        upload_id = uploaded.json()["upload_id"]
    assert len(tuple((data / "uploads" / "pending").glob("*.pdf"))) == 1

    engine = create_sqlite_engine(settings.core_settings().database_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                update(api_uploads)
                .where(api_uploads.c.id == upload_id)
                .values(updated_at=(datetime.now(UTC) - timedelta(days=2)).isoformat())
            )
    finally:
        engine.dispose()

    restarted = create_app(settings)
    with TestClient(restarted) as client:
        expired = client.post(
            f"/api/v1/uploads/{upload_id}/unlock",
            headers=AUTH,
            json={"password": "correta"},
        )
        assert expired.status_code == 409
        assert (
            client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"][
                "documents"
            ]
            == []
        )
    assert list((data / "uploads" / "pending").glob("*.pdf")) == []


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("GET", "/api/v1/projects"),
        ("POST", "/api/v1/projects"),
        ("GET", f"/api/v1/projects/{uuid4()}"),
        ("PATCH", f"/api/v1/projects/{uuid4()}"),
        ("DELETE", f"/api/v1/projects/{uuid4()}"),
        ("POST", f"/api/v1/projects/{uuid4()}/document-uploads"),
        ("POST", f"/api/v1/uploads/{uuid4()}/unlock"),
        ("PUT", f"/api/v1/projects/{uuid4()}/page-order"),
        ("DELETE", f"/api/v1/projects/{uuid4()}/documents/{uuid4()}"),
        ("GET", f"/api/v1/projects/{uuid4()}/photos"),
        ("POST", f"/api/v1/projects/{uuid4()}/elements/{uuid4()}/photos"),
        ("DELETE", f"/api/v1/projects/{uuid4()}/elements/{uuid4()}/photos/{uuid4()}"),
        ("GET", f"/api/v1/projects/{uuid4()}/photos/{uuid4()}/content"),
    ),
)
def test_every_stage_three_route_requires_bearer(
    tmp_path: Path,
    method: str,
    path: str,
) -> None:
    application = create_app(_settings(tmp_path / "server-data"))
    with TestClient(application) as client:
        response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_FAILED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_path_traversal_limit_and_interrupted_stream_leave_no_partial_files(
    tmp_path: Path,
) -> None:
    data = tmp_path / "server-data"
    pdf = create_golden_pdf(tmp_path / "small.pdf")
    application = create_app(_settings(data, upload_max_bytes=len(pdf.read_bytes()) - 1))
    with TestClient(application) as client:
        project_id = str(_create_project(client)["project_id"])
        traversal = _upload_pdf(
            client,
            project_id,
            pdf,
            key="traversal",
            display_name="..\\segredo\\projeto.pdf",
        )
        assert traversal.status_code == 422
        assert traversal.json()["code"] == "VALIDATION_ERROR"
        oversized = _upload_pdf(client, project_id, pdf, key="oversized")
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "UPLOAD_TOO_LARGE"
        assert (
            client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"][
                "documents"
            ]
            == []
        )
    assert list((data / "uploads" / "incoming").glob("*.part")) == []

    storage = ManagedUploadStorage(data / "stream-failure", maximum_bytes=1024)

    class BrokenUpload:
        filename = "interrompido.pdf"
        content_type = "application/pdf"

        def __init__(self) -> None:
            self.calls = 0

        async def read(self, _size: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"%PDF-partial"
            raise ConnectionError("cliente desconectou")

    with pytest.raises(ConnectionError, match="desconectou"):
        asyncio.run(storage.receive(cast(UploadFile, BrokenUpload())))
    assert list(storage.incoming_root.glob("*.part")) == []


def test_database_failure_rolls_back_managed_pdf_and_project_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "server-data"
    pdf = create_golden_pdf(tmp_path / "falha.pdf")
    application = create_app(_settings(data))
    with TestClient(application, raise_server_exceptions=False) as client:
        project_id = str(_create_project(client)["project_id"])
        runtime = cast(ServerRuntime, application.state.runtime)
        assert runtime.project_api is not None

        def fail_import(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("falha injetada antes do commit")

        monkeypatch.setattr(runtime.project_api._importer, "executar", fail_import)
        failed = _upload_pdf(client, project_id, pdf, key="database-failure")
        assert failed.status_code == 500
        assert failed.json()["code"] == "INTERNAL_ERROR"
        assert "falha injetada" not in failed.text
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert detail.json()["project"]["documents"] == []

    document_root = data / "project-files" / project_id / "documents"
    assert not document_root.exists() or list(document_root.iterdir()) == []
    assert list((data / "uploads" / "incoming").glob("*.part")) == []


def test_recovery_keeps_preexisting_managed_pdf_during_rollback_and_pending_move(
    tmp_path: Path,
) -> None:
    storage = ManagedUploadStorage(tmp_path / "server-data", maximum_bytes=1024)
    project_id = uuid4()
    document_id = uuid4()
    payload = b"%PDF-1.7\nrecovery identity\n%%EOF"

    def received(name: str) -> ReceivedUpload:
        source = storage.incoming_root / name
        source.write_bytes(payload)
        return ReceivedUpload(
            path=source,
            display_name="recuperacao.pdf",
            content_type="application/pdf",
            size_bytes=len(payload),
            sha256=sha256(payload).hexdigest(),
        )

    initial = storage.publish_document(
        received("initial.part"),
        project_id=project_id,
        document_id=document_id,
    )
    initial.complete()
    destination = initial.destination
    assert destination.read_bytes() == payload

    retry = received("retry.part")
    rollback = storage.publish_document(
        retry,
        project_id=project_id,
        document_id=document_id,
    )
    assert rollback.destination_preexisted is True
    rollback.restore_source()
    assert destination.read_bytes() == payload
    assert retry.path.read_bytes() == payload
    storage.discard(retry)

    protected_retry = received("protected-retry.part")
    pending_publication = storage.publish_document(
        protected_retry,
        project_id=project_id,
        document_id=document_id,
    )
    pending = storage.pending_path(uuid4())
    pending_publication.move_to_pending(pending)
    assert destination.read_bytes() == payload
    assert pending.read_bytes() == payload
    assert not protected_retry.path.exists()


def test_two_concurrent_clients_replay_one_upload_without_duplication(tmp_path: Path) -> None:
    data = tmp_path / "server-data"
    pdf = create_golden_pdf(tmp_path / "concorrente.pdf")
    payload = pdf.read_bytes()
    application = create_app(_settings(data))
    with TestClient(application) as client:
        project_id = str(_create_project(client, key="concurrent-project")["project_id"])

        def send() -> Response:
            return client.post(
                f"/api/v1/projects/{project_id}/document-uploads",
                headers={**AUTH, "Idempotency-Key": "same-concurrent-upload"},
                files={"file": ("concorrente.pdf", payload, "application/pdf")},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = tuple(executor.map(lambda _index: send(), range(2)))
        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json() == responses[1].json()
        detail = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert len(detail.json()["project"]["documents"]) == 1


def test_managed_photo_upload_download_idempotency_and_removal(tmp_path: Path) -> None:
    data = tmp_path / "server-data"
    photo_path = tmp_path / "client-photo.png"
    Image.new("RGB", (8, 6), (12, 34, 56)).save(photo_path)
    application = create_app(_settings(data))
    with TestClient(application) as client:
        created = _create_project(client, key="photo-project")
        project_id = UUID(str(created["project_id"]))
        runtime = cast(ServerRuntime, application.state.runtime)
        pole_type = runtime.core.catalog.itens_ativos(CategoriaElemento.POSTE)[0].id
        pole = Poste(
            id=uuid4(),
            tipo_catalogo_id=pole_type,
            situacao=SituacaoProjeto.EXISTENTE,
        )
        with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
            project = work.projetos.obter(project_id)
            assert project is not None
            work.projetos.salvar(replace(project, elementos=(pole,)))
            work.commit()

        route = f"/api/v1/projects/{project_id}/elements/{pole.id}/photos"
        headers = {**AUTH, "Idempotency-Key": "photo-upload"}
        files = {"file": ("poste.png", photo_path.read_bytes(), "image/png")}
        attached = client.post(route, headers=headers, files=files)
        replay = client.post(route, headers=headers, files=files)
        assert attached.status_code == replay.status_code == 201
        assert attached.json() == replay.json()
        photo = attached.json()["photo"]
        listed = client.get(f"/api/v1/projects/{project_id}/photos", headers=AUTH)
        assert listed.json()["items"] == [photo]
        downloaded = client.get(
            f"/api/v1/projects/{project_id}/photos/{photo['photo_id']}/content",
            headers=AUTH,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == photo_path.read_bytes()
        assert "sha-256=" in downloaded.headers["Digest"]
        removed = client.delete(
            f"{route}/{photo['photo_id']}",
            headers=AUTH,
        )
        assert removed.status_code == 200
        assert removed.json()["removed"] is True
        missing = client.get(
            f"/api/v1/projects/{project_id}/photos/{photo['photo_id']}/content",
            headers=AUTH,
        )
        assert missing.status_code == 404


def _all_json_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {nested for item in value.values() for nested in _all_json_keys(item)}
    if isinstance(value, list):
        return {nested for item in value for nested in _all_json_keys(item)}
    return set()
