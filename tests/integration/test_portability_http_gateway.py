from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from socket import create_server
from threading import Event, Thread
from time import monotonic
from uuid import UUID, uuid4

import pytest
from tests.pdf_fixtures import create_golden_pdf
from uvicorn import Config, Server

from zeny_project_handler_client.ui.portability_gateway import HttpPortabilityGateway
from zeny_project_handler_client.ui.project_gateway import HttpProjectGateway
from zeny_project_handler_contracts.backup import (
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_contracts.portability import ConfirmProjectImportRequest
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration

PASSWORD = "senha da portabilidade HTTP real"


def test_http_round_trip_hash_repeated_download_restore_and_restart(tmp_path: Path) -> None:
    client_root = tmp_path / "client"
    client_root.mkdir()
    source = create_golden_pdf(client_root / "source.pdf")
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-volume",
        transfer_ttl_seconds=300,
    )
    export_download_id: UUID
    export_hash: str

    with _running_server(settings) as base_url:
        projects = HttpProjectGateway(base_url, PASSWORD)
        portability = HttpPortabilityGateway(base_url, PASSWORD)
        created = projects.create_project("0001234567", idempotency_key="http-project")
        project_id = created.project.project_id.root
        projects.upload_document(project_id, source, idempotency_key="http-pdf")
        project_version = projects.get_project(project_id).project.project_version

        export = portability.create_project_export_job(
            project_id,
            expected_project_version=project_version,
            idempotency_key="http-export",
        )
        export_result = _wait_result(portability, export.job_id.root)
        assert export_result.download is not None
        export_download_id = export_result.download.download_id.root
        export_hash = export_result.download.sha256
        first_package = client_root / "first.zphproj"
        second_package = client_root / "second.zphproj"
        portability.download_to(
            export_download_id,
            first_package,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        portability.download_to(
            export_download_id,
            second_package,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        assert first_package.read_bytes() == second_package.read_bytes()
        assert sha256(first_package.read_bytes()).hexdigest() == export_hash

        assert projects.delete_project(project_id).deleted
        import_preflight = portability.preflight_project_import(
            first_package,
            idempotency_key="http-import-preflight",
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        imported = portability.create_project_import_job(
            ConfirmProjectImportRequest(
                preflight_id=import_preflight.preflight_id,
                package_sha256=import_preflight.package_sha256,
                target_fingerprint=import_preflight.target_fingerprint,
                replace_existing=False,
                confirmed=True,
            ),
            idempotency_key="http-import",
        )
        _wait_result(portability, imported.job_id.root)
        restored_project = projects.get_project(project_id).project
        assert restored_project.documents[0].file.sha256 == sha256(source.read_bytes()).hexdigest()

        backup_preflight = portability.preflight_backup()
        backup = portability.create_backup_job(
            CreateBackupJobRequest(
                preflight_id=backup_preflight.preflight_id,
                source_fingerprint=backup_preflight.source_fingerprint,
                accept_degraded=False,
                confirmed=True,
            ),
            idempotency_key="http-backup",
        )
        backup_result = _wait_result(portability, backup.job_id.root)
        assert backup_result.download is not None
        backup_path = client_root / "round-trip.zphbackup"
        portability.download_to(
            backup_result.download.download_id.root,
            backup_path,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )

        assert projects.delete_project(project_id).deleted
        restore_preflight = portability.preflight_backup_restore(
            backup_path,
            idempotency_key="http-restore-preflight",
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        restore = portability.create_backup_restore_job(
            ConfirmBackupRestoreRequest(
                preflight_id=restore_preflight.preflight_id,
                package_sha256=restore_preflight.package_sha256,
                target_fingerprint=restore_preflight.target_fingerprint,
                accept_degraded=False,
                confirmed=True,
            ),
            idempotency_key="http-restore",
        )
        _wait_result(portability, restore.job_id.root)
        assert (
            projects.get_project(project_id).project.documents[0].file.sha256
            == sha256(source.read_bytes()).hexdigest()
        )

    with _running_server(settings) as restarted_url:
        restarted = HttpPortabilityGateway(restarted_url, PASSWORD)
        after_restart = client_root / "after-restart.zphproj"
        metadata = restarted.download_to(
            export_download_id,
            after_restart,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        assert metadata.sha256 == export_hash
        assert sha256(after_restart.read_bytes()).hexdigest() == export_hash


def _wait_result(gateway: HttpPortabilityGateway, job_id: UUID):  # type: ignore[no-untyped-def]
    deadline = monotonic() + 30
    tick = Event()
    while monotonic() < deadline:
        status = gateway.get_job(job_id)
        if status.status is JobStatus.SUCCEEDED:
            return gateway.get_job_result(job_id)
        if status.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise AssertionError(f"Job terminou em {status.status.value}: {status.error}")
        tick.wait(0.03)
    raise AssertionError("Job remoto não terminou no prazo")


@contextmanager
def _running_server(settings: ServerSettings) -> Iterator[str]:
    with closing(create_server(("127.0.0.1", 0))) as listener:
        port = int(listener.getsockname()[1])
        server = Server(
            Config(
                create_app(settings),
                log_level="critical",
                lifespan="on",
            )
        )

        def serve() -> None:
            server.run(sockets=[listener])

        thread = Thread(target=serve, name=f"portability-http-{uuid4().hex[:8]}", daemon=True)
        thread.start()
        _wait_until_started(server, thread)
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive()


def _wait_until_started(server: Server, thread: Thread) -> None:
    tick = Event()
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if server.started:
            return
        if not thread.is_alive():
            break
        tick.wait(0.01)
    raise RuntimeError("Servidor HTTP de portabilidade não iniciou no prazo")
