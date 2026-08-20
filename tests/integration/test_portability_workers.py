from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Event, get_ident
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressBar, QPushButton
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory

import zeny_project_handler_client.ui.main_window as main_window_module
from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.portability_gateway import (
    CancelCallback,
    PortabilityGatewayError,
    PortabilityTransferCancelledError,
    ProgressCallback,
)
from zeny_project_handler_client.ui.portability_panel import PortabilityPanelWidget
from zeny_project_handler_client.ui.portability_worker import (
    PortabilityCommand,
    PortabilityOperation,
    PortabilityWorker,
)
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.base import (
    DownloadId,
    JobId,
    ProjectId,
    ProjectImportPreflightId,
)
from zeny_project_handler_contracts.common import DownloadMetadataDto, PageMetadataDto
from zeny_project_handler_contracts.enums import (
    IntegrityState,
    JobKind,
    JobStatus,
    PreflightDisposition,
    ProjectState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
    ProjectImportSummaryDto,
)
from zeny_project_handler_contracts.projects import (
    ProjectAnalysisSummaryDto,
    ProjectSummaryDto,
    ProjectSummaryListResponse,
)

pytestmark = pytest.mark.integration

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000007")


@dataclass(slots=True)
class ControlledRun:
    progress: tuple[tuple[int, str], ...] = (
        (50, "metade"),
        (25, "atrasado"),
        (75, "quase"),
    )
    failure: PortabilityGatewayError | None = None
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    cancellation_seen: Event = field(default_factory=Event)
    progress_index: int = 0
    cancelled: bool = False


class ControlledPortabilityGateway:
    def __init__(self, *runs: ControlledRun) -> None:
        self.runs = list(runs)
        self.calls = 0
        self.worker_thread_ids: list[int] = []
        self.events: list[str] = []
        self.confirmed_imports: list[ConfirmProjectImportRequest] = []
        self._active: ControlledRun | None = None
        self._kind = JobKind.PROJECT_EXPORT
        self._job_id = uuid4()
        self.import_preflight = _conflicting_import_preflight()
        self.download_payload = b"pacote remoto validado"

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> ProjectSummaryListResponse:
        now = datetime.now(UTC)
        summary = ProjectSummaryDto(
            project_id=ProjectId(PROJECT_ID),
            service_note="Projeto controlado",
            state=ProjectState.READY,
            project_version=7,
            document_count=1,
            page_count=1,
            analysis=ProjectAnalysisSummaryDto(
                pending_proposals=0,
                completed_decisions=0,
            ),
            created_at=now,
            updated_at=now,
        )
        return ProjectSummaryListResponse(
            items=(summary,),
            page=PageMetadataDto(limit=limit, offset=offset, total=1),
        )

    def create_project_export_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        assert project_id == PROJECT_ID
        assert expected_project_version == 7
        assert idempotency_key
        self._kind = JobKind.PROJECT_EXPORT
        self._start_run()
        return self._accepted()

    def preflight_project_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> ProjectImportPreflightResponse:
        assert path.suffix == ".zphproj"
        assert idempotency_key
        if cancelled():
            raise PortabilityTransferCancelledError("Upload cancelado")
        progress(1, 1, "Upload validado")
        self.events.append("preflight")
        return self.import_preflight

    def create_project_import_job(
        self,
        request: ConfirmProjectImportRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        assert idempotency_key
        self.events.append("confirm")
        self.confirmed_imports.append(request)
        self._kind = JobKind.PROJECT_IMPORT
        self._start_run()
        return self._accepted()

    def preflight_backup(self) -> BackupPreflightResponse:
        raise AssertionError("backup não esperado neste teste")

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        raise AssertionError((request, idempotency_key))

    def preflight_backup_restore(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> BackupRestorePreflightResponse:
        raise AssertionError((path, idempotency_key, progress, cancelled))

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        raise AssertionError((request, idempotency_key))

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        assert job_id == self._job_id
        run = self._required_run()
        if run.progress_index < len(run.progress):
            percent, message = run.progress[run.progress_index]
            run.progress_index += 1
            return self._status(JobStatus.RUNNING, percent, message)
        run.entered.set()
        if not run.release.wait(timeout=5):
            raise RuntimeError("Teste não liberou o gateway controlado")
        if run.cancelled:
            run.cancellation_seen.set()
            return self._status(JobStatus.CANCELLED, 75, "Exportação cancelada em ponto seguro")
        if run.failure is not None:
            raise run.failure
        return self._status(JobStatus.SUCCEEDED, 100, "Operação concluída")

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        assert job_id == self._job_id
        download = None
        if self._kind is JobKind.PROJECT_EXPORT:
            download = self.get_download_metadata(uuid4())
        return JobResultResponse(
            job_id=JobId(job_id),
            status=JobStatus.SUCCEEDED,
            result={"project_id": str(PROJECT_ID), "integrity_state": "INTACT"},
            download=download,
        )

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        assert job_id == self._job_id
        run = self._required_run()
        run.cancelled = True
        run.cancellation_seen.set()
        return CancelJobResponse(
            job_id=JobId(job_id),
            status=JobStatus.CANCELLING,
            cancellation_requested=True,
        )

    def get_download_metadata(self, download_id: UUID) -> DownloadMetadataDto:
        return DownloadMetadataDto(
            download_id=DownloadId(download_id),
            file_name="projeto.zphproj",
            mime_type="application/octet-stream",
            size_bytes=len(self.download_payload),
            sha256=sha256(self.download_payload).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def download_to(
        self,
        download_id: UUID,
        destination: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> DownloadMetadataDto:
        metadata = self.get_download_metadata(download_id)
        if cancelled():
            raise PortabilityTransferCancelledError("Download cancelado")
        destination.write_bytes(self.download_payload)
        progress(len(self.download_payload), len(self.download_payload), "Download validado")
        return metadata

    def _start_run(self) -> None:
        run = self.runs[self.calls]
        self.calls += 1
        self.worker_thread_ids.append(get_ident())
        self._active = run
        self._job_id = uuid4()

    def _required_run(self) -> ControlledRun:
        if self._active is None:
            raise AssertionError("job não iniciado")
        return self._active

    def _accepted(self) -> JobAcceptedResponse:
        return JobAcceptedResponse(
            job_id=JobId(self._job_id),
            kind=self._kind,
            status=JobStatus.QUEUED,
            poll_after_ms=250,
        )

    def _status(self, status: JobStatus, progress: int, message: str) -> JobStatusResponse:
        now = datetime.now(UTC)
        return JobStatusResponse(
            job_id=JobId(self._job_id),
            project_id=ProjectId(PROJECT_ID),
            kind=self._kind,
            status=status,
            progress_percent=progress,
            message=message,
            result_available=status is JobStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
        )


def _conflicting_import_preflight() -> ProjectImportPreflightResponse:
    return ProjectImportPreflightResponse(
        preflight_id=ProjectImportPreflightId(uuid4()),
        package_sha256="a" * 64,
        target_fingerprint="b" * 64,
        disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
        integrity_state=IntegrityState.INTACT,
        summary=ProjectImportSummaryDto(
            project_id=ProjectId(PROJECT_ID),
            service_note="Projeto controlado",
            document_count=1,
            page_count=2,
            photo_count=3,
            replaces_existing=True,
        ),
        issues=(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def _panel(qtbot: QtBot, gateway: ControlledPortabilityGateway) -> PortabilityPanelWidget:
    panel = PortabilityPanelWidget(gateway=gateway)
    qtbot.addWidget(panel)
    panel.show()
    panel._project.setCurrentIndex(panel._project.findData(str(PROJECT_ID)))
    return panel


def _export_button(panel: PortabilityPanelWidget) -> QPushButton:
    button = panel.findChild(QPushButton, "portabilityExportButton")
    assert button is not None
    return button


def _start_export(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    panel: PortabilityPanelWidget,
    destination: Path,
) -> None:
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Projeto Zeny (*.zphproj)"),
    )
    qtbot.mouseClick(_export_button(panel), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]


@pytest.mark.parametrize("accepted", [False, True])
def test_import_worker_confirms_remote_preflight_before_job(
    tmp_path: Path,
    accepted: bool,
) -> None:
    package = tmp_path / "controlled.zphproj"
    package.write_bytes(b"client package")
    run = ControlledRun(progress=())
    run.release.set()
    gateway = ControlledPortabilityGateway(run)
    worker = PortabilityWorker(
        gateway,
        PortabilityCommand(PortabilityOperation.IMPORT, package),
        Event(),
        "a" * 32,
    )
    confirmations: list[tuple[str, object, tuple[str, ...]]] = []
    failures: list[tuple[str, bool]] = []
    successes: list[object] = []

    def confirm(_execution_id: str, kind: str, payload: object) -> None:
        confirmations.append((kind, payload, tuple(gateway.events)))
        worker.resolve_confirmation(accepted)

    worker.confirmation_required.connect(confirm)
    worker.failed.connect(
        lambda _execution_id, message, cancelled: failures.append((message, cancelled))
    )
    worker.succeeded.connect(lambda _execution_id, result: successes.append(result))
    worker.run()

    assert confirmations == [("replace_project", gateway.import_preflight, ("preflight",))]
    if accepted:
        assert gateway.events == ["preflight", "confirm"]
        assert gateway.confirmed_imports[0].replace_existing
        assert len(successes) == 1
        assert failures == []
    else:
        assert gateway.events == ["preflight"]
        assert successes == []
        assert failures == [("Importação cancelada antes da substituição", True)]


def test_import_panel_shows_remote_summary_and_refusal_never_creates_job(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "panel-controlled.zphproj"
    package.write_bytes(b"package")
    gateway = ControlledPortabilityGateway(ControlledRun(progress=()))
    panel = _panel(qtbot, gateway)
    questions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(package), "Projeto Zeny (*.zphproj)"),
    )

    def refuse(_parent: object, title: str, message: str, *_args: object) -> object:
        questions.append((title, message))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", refuse)
    qtbot.mouseClick(panel._import, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    qtbot.waitUntil(lambda: not panel.processando)

    assert gateway.events == ["preflight"]
    assert gateway.calls == 0
    assert len(questions) == 1
    assert questions[0][0] == "Substituir projeto existente"
    assert "Projeto controlado" in questions[0][1]
    assert str(PROJECT_ID)[:8] in questions[0][1]
    assert gateway.import_preflight.target_fingerprint[:12] in questions[0][1]


def test_worker_keeps_gui_responsive_and_reports_monotonic_success_once(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun()
    gateway = ControlledPortabilityGateway(run)
    panel = _panel(qtbot, gateway)
    busy: list[bool] = []
    statuses: list[str] = []
    panel.busy_changed.connect(busy.append)
    panel.status_changed.connect(statuses.append)
    main_thread_id = get_ident()

    destination = tmp_path / "responsive.zphproj"
    _start_export(qtbot, monkeypatch, panel, destination)
    qtbot.waitUntil(run.entered.is_set)
    gui_tick = Event()
    QTimer.singleShot(0, gui_tick.set)
    qtbot.waitUntil(gui_tick.is_set)
    progress = panel.findChild(QProgressBar, "portabilityProgress")
    assert progress is not None
    qtbot.waitUntil(lambda: progress.value() == 56)
    assert progress.maximum() == 100
    assert len(gateway.worker_thread_ids) == 1
    assert gateway.worker_thread_ids[0] != main_thread_id
    assert not _export_button(panel).isEnabled()
    assert panel._cancel.isEnabled()

    panel.exportar_projeto()
    assert gateway.calls == 1
    panel._show_progress("f" * 32, 100, 100, "resultado obsoleto")
    assert progress.value() == 56
    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)

    assert destination.read_bytes() == gateway.download_payload
    assert busy == [True, False]
    assert _export_button(panel).isEnabled()
    assert not panel._cancel.isEnabled()
    assert any(message.startswith("Projeto exportado para") for message in statuses)


def test_worker_and_thread_are_destroyed_before_panel_reuse(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = tuple(ControlledRun(progress=()) for _index in range(4))
    gateway = ControlledPortabilityGateway(*runs)
    panel = _panel(qtbot, gateway)
    for index, run in enumerate(runs):
        _start_export(qtbot, monkeypatch, panel, tmp_path / f"lifecycle-{index}.zphproj")
        qtbot.waitUntil(run.entered.is_set)
        worker = panel._worker
        thread = panel._thread
        assert worker is not None and thread is not None
        worker_destroyed = Event()
        thread_destroyed = Event()
        worker.destroyed.connect(worker_destroyed.set)
        thread.destroyed.connect(thread_destroyed.set)
        run.release.set()
        qtbot.waitUntil(lambda: not panel.processando)
        qtbot.waitUntil(worker_destroyed.is_set)
        qtbot.waitUntil(thread_destroyed.is_set)
        assert panel._worker is None
        assert panel._thread is None


def test_worker_failure_restores_controls_once(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun(
        progress=(),
        failure=PortabilityGatewayError(ErrorCode.INTERNAL_ERROR, "falha remota controlada"),
    )
    gateway = ControlledPortabilityGateway(run)
    panel = _panel(qtbot, gateway)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    _start_export(qtbot, monkeypatch, panel, tmp_path / "failure.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)
    assert warnings == ["falha remota controlada"]
    assert _export_button(panel).isEnabled()


def test_worker_cancellation_calls_remote_job_and_has_no_error_dialog(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun(progress=())
    gateway = ControlledPortabilityGateway(run)
    panel = _panel(qtbot, gateway)
    warnings: list[str] = []
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    _start_export(qtbot, monkeypatch, panel, tmp_path / "cancel.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    qtbot.mouseClick(panel._cancel, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)
    assert run.cancellation_seen.is_set()
    assert warnings == []
    assert "Exportação cancelada em ponto seguro" in statuses


def test_window_disables_incompatible_panels_and_close_wait_is_bounded(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _application, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "window")
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.portability_panel
    project_panel = window.project_panel
    review_panel = window.review_panel
    documentation_panel = window.documentation_panel
    assert panel is not None
    assert project_panel is not None
    assert review_panel is not None
    assert documentation_panel is not None
    run = ControlledRun(progress=())
    gateway = ControlledPortabilityGateway(run)
    panel._gateway = gateway
    panel.atualizar_projetos()
    panel._project.setCurrentIndex(panel._project.findData(str(PROJECT_ID)))
    information: list[str] = []
    monkeypatch.setattr(main_window_module, "_CLOSE_WAIT_MS", 20)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: information.append(str(message)),
    )

    _start_export(qtbot, monkeypatch, panel, tmp_path / "window.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    qtbot.waitUntil(lambda: not project_panel.isEnabled())
    assert not review_panel.isEnabled()
    assert not documentation_panel.isEnabled()
    assert not window.close()
    assert information
    assert panel._cancellation is not None and panel._cancellation.is_set()
    assert panel._thread is not None and panel._thread.isRunning()

    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)
    assert project_panel.isEnabled()
    assert review_panel.isEnabled()
    assert documentation_panel.isEnabled()
    assert window.close()
