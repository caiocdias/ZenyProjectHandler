from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from typing import cast
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from tests.pdf_fixtures import create_golden_pdf
from zeny_project_handler.application.errors import PortabilidadeCanceladaError
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler_contracts.backup import CreateBackupJobRequest
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha segura para portabilidade remota"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


def _wait_job(client: TestClient, job_id: str, *, timeout: float = 15) -> dict[str, object]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        payload = cast(dict[str, object], response.json())
        if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return payload
        sleep(0.02)
    raise AssertionError("job remoto não terminou no prazo")


def _create_project_with_pdf(client: TestClient, source: Path) -> tuple[str, str]:
    created = client.post(
        "/api/v1/projects",
        headers={**AUTH, "Idempotency-Key": "stage8-create-project"},
        json={"service_note": "0001234567"},
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    project_id = str(project["project_id"])
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/document-uploads",
        headers={**AUTH, "Idempotency-Key": "stage8-upload-pdf"},
        files={"file": (source.name, source.read_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    current = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
    assert current.status_code == 200
    return project_id, str(current.json()["project"]["project_version"])


def _download_job(client: TestClient, job_id: str) -> tuple[dict[str, object], bytes]:
    terminal = _wait_job(client, job_id)
    assert terminal["status"] == "SUCCEEDED", terminal
    result_response = client.get(f"/api/v1/jobs/{job_id}/result", headers=AUTH)
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    metadata = result["download"]
    assert metadata is not None
    download_id = metadata["download_id"]
    first = client.get(f"/api/v1/downloads/{download_id}", headers=AUTH)
    second = client.get(f"/api/v1/downloads/{download_id}", headers=AUTH)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert len(first.content) == metadata["size_bytes"]
    assert sha256(first.content).hexdigest() == metadata["sha256"]
    metadata_response = client.get(
        f"/api/v1/downloads/{download_id}/metadata",
        headers=AUTH,
    )
    assert metadata_response.status_code == 200
    assert metadata_response.json() == metadata
    return result, first.content


def _project_document_sha256(client: TestClient, project_id: str) -> str:
    response = client.get(f"/api/v1/projects/{project_id}/viewer", headers=AUTH)
    assert response.status_code == 200, response.text
    return str(response.json()["documents"][0]["sha256"])


def _with_traversal_member(package: bytes) -> bytes:
    source = BytesIO(package)
    target = BytesIO()
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as unsafe:
        for member in original.infolist():
            unsafe.writestr(member, original.read(member.filename))
        unsafe.writestr("../escape.txt", b"unsafe")
    return target.getvalue()


def test_project_and_backup_round_trip_integrity_repeated_download_and_restart(
    tmp_path: Path,
) -> None:
    data = tmp_path / "server-data"
    source = create_golden_pdf(tmp_path / "client-only.pdf")
    settings = ServerSettings(
        password=PASSWORD,
        data_directory=data,
        upload_max_bytes=16 * 1024 * 1024,
        transfer_ttl_seconds=300,
    )

    with TestClient(create_app(settings)) as client:
        project_id, project_version = _create_project_with_pdf(client, source)
        exported = client.post(
            f"/api/v1/projects/{project_id}/export-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-export-job"},
            json={"expected_project_version": int(project_version)},
        )
        assert exported.status_code == 202, exported.text
        export_result, project_package = _download_job(client, exported.json()["job_id"])
        exported_payload = export_result["result"]
        assert isinstance(exported_payload, dict)
        assert exported_payload["project_id"] == project_id

        deleted = client.delete(f"/api/v1/projects/{project_id}", headers=AUTH)
        assert deleted.status_code == 200
        preflight = client.post(
            "/api/v1/project-import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-project-preflight"},
            files={
                "file": (
                    "round-trip.zphproj",
                    project_package,
                    "application/octet-stream",
                )
            },
        )
        assert preflight.status_code == 201, preflight.text
        prepared = preflight.json()
        assert prepared["package_sha256"] == sha256(project_package).hexdigest()
        imported = client.post(
            "/api/v1/project-import-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-import-job"},
            json={
                "preflight_id": prepared["preflight_id"],
                "package_sha256": prepared["package_sha256"],
                "target_fingerprint": prepared["target_fingerprint"],
                "replace_existing": False,
                "confirmed": True,
            },
        )
        assert imported.status_code == 202, imported.text
        assert _wait_job(client, imported.json()["job_id"])["status"] == "SUCCEEDED"
        assert (
            _project_document_sha256(client, project_id) == sha256(source.read_bytes()).hexdigest()
        )

        backup_preflight = client.post("/api/v1/backup-preflights", headers=AUTH)
        assert backup_preflight.status_code == 201, backup_preflight.text
        backup_plan = backup_preflight.json()
        backup_job = client.post(
            "/api/v1/backup-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-backup-job"},
            json={
                "preflight_id": backup_plan["preflight_id"],
                "source_fingerprint": backup_plan["source_fingerprint"],
                "accept_degraded": False,
                "confirmed": True,
            },
        )
        assert backup_job.status_code == 202, backup_job.text
        _backup_result, backup_package = _download_job(client, backup_job.json()["job_id"])

        assert client.delete(f"/api/v1/projects/{project_id}", headers=AUTH).status_code == 200
        restore_preflight = client.post(
            "/api/v1/backup-restore-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-restore-preflight"},
            files={
                "file": (
                    "round-trip.zphbackup",
                    backup_package,
                    "application/octet-stream",
                )
            },
        )
        assert restore_preflight.status_code == 201, restore_preflight.text
        restore_plan = restore_preflight.json()
        restore_request = {
            "preflight_id": restore_plan["preflight_id"],
            "package_sha256": restore_plan["package_sha256"],
            "target_fingerprint": restore_plan["target_fingerprint"],
            "accept_degraded": False,
            "confirmed": True,
        }
        restore_job = client.post(
            "/api/v1/backup-restore-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-restore-job"},
            json=restore_request,
        )
        assert restore_job.status_code == 202, restore_job.text
        restored = _wait_job(client, restore_job.json()["job_id"])
        assert restored["status"] == "SUCCEEDED", restored
        assert client.get(f"/api/v1/projects/{project_id}", headers=AUTH).status_code == 200
        replayed_restore = client.post(
            "/api/v1/backup-restore-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-restore-job"},
            json=restore_request,
        )
        assert replayed_restore.status_code == 202, replayed_restore.text
        assert replayed_restore.json() == restore_job.json()

    with TestClient(create_app(settings)) as restarted:
        assert (
            _project_document_sha256(restarted, project_id)
            == sha256(source.read_bytes()).hexdigest()
        )


def test_preflight_rejects_corruption_traversal_and_stale_target(tmp_path: Path) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        data_directory=tmp_path / "server-data",
        upload_max_bytes=16 * 1024 * 1024,
    )
    source = create_golden_pdf(tmp_path / "client.pdf")
    with TestClient(create_app(settings)) as client:
        project_id, project_version = _create_project_with_pdf(client, source)
        export = client.post(
            f"/api/v1/projects/{project_id}/export-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-stale-export"},
            json={"expected_project_version": int(project_version)},
        )
        _result, package = _download_job(client, export.json()["job_id"])

        corrupt = bytearray(package)
        corrupt[len(corrupt) // 2] ^= 0xFF
        invalid = client.post(
            "/api/v1/project-import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-corrupt"},
            files={"file": ("corrupt.zphproj", bytes(corrupt), "application/octet-stream")},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "INTEGRITY_ERROR"

        traversal = client.post(
            "/api/v1/project-import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-traversal"},
            files={
                "file": (
                    "unsafe.zphproj",
                    _with_traversal_member(package),
                    "application/octet-stream",
                )
            },
        )
        assert traversal.status_code == 422

        prepared_response = client.post(
            "/api/v1/project-import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-stale-preflight"},
            files={"file": ("valid.zphproj", package, "application/octet-stream")},
        )
        assert prepared_response.status_code == 201
        prepared = prepared_response.json()
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
        stale = client.post(
            "/api/v1/project-import-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-stale-confirm"},
            json={
                "preflight_id": prepared["preflight_id"],
                "package_sha256": prepared["package_sha256"],
                "target_fingerprint": prepared["target_fingerprint"],
                "replace_existing": True,
                "confirmed": True,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "STALE_STATE"

        backup_preflight = client.post("/api/v1/backup-preflights", headers=AUTH)
        assert backup_preflight.status_code == 201
        backup_plan = backup_preflight.json()
        current = client.get(f"/api/v1/projects/{project_id}", headers=AUTH).json()["project"]
        changed_again = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=AUTH,
            json={
                "service_note": "0009999999",
                "expected_project_version": current["project_version"],
            },
        )
        assert changed_again.status_code == 200
        stale_backup = client.post(
            "/api/v1/backup-jobs",
            headers={**AUTH, "Idempotency-Key": "stage8-stale-backup-confirm"},
            json={
                "preflight_id": backup_plan["preflight_id"],
                "source_fingerprint": backup_plan["source_fingerprint"],
                "accept_degraded": False,
                "confirmed": True,
            },
        )
        assert stale_backup.status_code == 409
        assert stale_backup.json()["code"] == "STALE_STATE"


def test_interrupted_upload_is_removed_and_expired_download_is_unavailable(
    tmp_path: Path,
) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        data_directory=tmp_path / "server-data",
        upload_max_bytes=64,
        transfer_ttl_seconds=1,
    )
    with TestClient(create_app(settings)) as client:
        too_large = client.post(
            "/api/v1/project-import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage8-too-large"},
            files={"file": ("large.zphproj", b"x" * 65, "application/octet-stream")},
        )
        assert too_large.status_code == 413
        assert not tuple((settings.data_directory / "transfers" / "incoming").glob("*.part"))


def test_backup_job_cancellation_removes_pending_artifact_and_has_no_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        data_directory=tmp_path / "server-data",
    )
    runtime = compose_server_runtime(settings)
    assert runtime.portability_api is not None
    started = Event()

    def controlled_backup(
        _self: ServicoPortabilidadeProjeto,
        destination: Path,
        **options: object,
    ) -> object:
        destination.write_bytes(b"partial package")
        started.set()
        cancelled = options["cancelado"]
        assert callable(cancelled)
        while not cancelled():
            sleep(0.01)
        raise PortabilidadeCanceladaError("Backup cancelado em ponto seguro")

    monkeypatch.setattr(ServicoPortabilidadeProjeto, "criar_backup", controlled_backup)
    try:
        preflight = runtime.portability_api.preflight_backup()
        accepted = runtime.jobs.create_backup_job(
            CreateBackupJobRequest(
                preflight_id=preflight.preflight_id,
                source_fingerprint=preflight.source_fingerprint,
                accept_degraded=False,
                confirmed=True,
            ),
            idempotency_key="stage8-cancel-backup",
            correlation_id=str(uuid4()),
        )
        assert started.wait(2)
        cancelled = runtime.jobs.cancel(accepted.job_id.root)
        assert cancelled.cancellation_requested
        deadline = monotonic() + 5
        while monotonic() < deadline:
            status = runtime.jobs.get_job(accepted.job_id.root)
            if status.status is JobStatus.CANCELLED:
                break
            sleep(0.01)
        else:
            raise AssertionError("Job de backup não cancelou no prazo")
        result = runtime.jobs.get_result(accepted.job_id.root)
        assert result.result is None
        assert result.download is None
        transfer_root = settings.data_directory / "transfers"
        assert not tuple((transfer_root / "download-pending").iterdir())
        assert not tuple((transfer_root / "downloads").iterdir())
    finally:
        runtime.close()
