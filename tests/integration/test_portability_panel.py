from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QMessageBox, QPushButton
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import create_golden_pdf
from tests.remote_gateways import DirectPortabilityGateway, DirectProjectGateway

from zeny_project_handler.ui.portability_gateway import (
    CancelCallback,
    PortabilityGateway,
    ProgressCallback,
)
from zeny_project_handler.ui.portability_panel import PortabilityPanelWidget
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    BackupRestoreSummaryDto,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.base import (
    BackupPreflightId,
    BackupRestorePreflightId,
    DownloadId,
    JobId,
    ProjectId,
)
from zeny_project_handler_contracts.common import (
    DownloadMetadataDto,
    PageMetadataDto,
    PreflightIssueDto,
)
from zeny_project_handler_contracts.enums import (
    IntegrityState,
    IssueSeverity,
    JobKind,
    JobStatus,
    PreflightDisposition,
)
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.projects import ProjectSummaryListResponse
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration


class PanelScenarioGateway:
    def __init__(self, *, issue_code: str = "PDF_AUSENTE", issue_label: str = "ausente") -> None:
        self.issue_code = issue_code
        self.issue_label = issue_label
        self.backup_jobs: list[CreateBackupJobRequest] = []
        self.restore_jobs: list[ConfirmBackupRestoreRequest] = []
        self.restore_preflights = 0
        self._job_id = uuid4()
        self._download_id = uuid4()
        self._payload = b"backup remoto degradado"

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> ProjectSummaryListResponse:
        return ProjectSummaryListResponse(
            items=(),
            page=PageMetadataDto(limit=limit, offset=offset, total=0),
        )

    def preflight_backup(self) -> BackupPreflightResponse:
        return BackupPreflightResponse(
            preflight_id=BackupPreflightId(uuid4()),
            source_fingerprint="a" * 64,
            disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
            integrity_state=IntegrityState.DEGRADED,
            project_count=1,
            document_count=1,
            issues=(
                PreflightIssueDto(
                    code=self.issue_code,
                    severity=IssueSeverity.WARNING,
                    summary=f"PDF {self.issue_label}",
                    resource_id="10000000-0000-0000-0000-000000000007",
                ),
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        assert idempotency_key
        self.backup_jobs.append(request)
        return self._accepted(JobKind.BACKUP_CREATE)

    def preflight_backup_restore(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> BackupRestorePreflightResponse:
        assert path.suffix == ".zphbackup"
        assert idempotency_key
        assert not cancelled()
        self.restore_preflights += 1
        progress(1, 1, "Upload de backup validado")
        return BackupRestorePreflightResponse(
            preflight_id=BackupRestorePreflightId(uuid4()),
            package_sha256="b" * 64,
            target_fingerprint="c" * 64,
            disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
            summary=BackupRestoreSummaryDto(
                project_ids=(ProjectId(UUID("10000000-0000-0000-0000-000000000007")),),
                document_count=1,
                photo_count=0,
                integrity_state=IntegrityState.INTACT,
            ),
            issues=(),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        assert idempotency_key
        self.restore_jobs.append(request)
        return self._accepted(JobKind.BACKUP_RESTORE)

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        assert job_id == self._job_id
        now = datetime.now(UTC)
        kind = JobKind.BACKUP_RESTORE if self.restore_jobs else JobKind.BACKUP_CREATE
        return JobStatusResponse(
            job_id=JobId(job_id),
            kind=kind,
            status=JobStatus.SUCCEEDED,
            progress_percent=100,
            message="Operação remota concluída",
            result_available=True,
            created_at=now,
            updated_at=now,
        )

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        assert job_id == self._job_id
        restoring = bool(self.restore_jobs)
        return JobResultResponse(
            job_id=JobId(job_id),
            status=JobStatus.SUCCEEDED,
            result={"integrity_state": "INTACT" if restoring else "DEGRADED"},
            download=None if restoring else self.get_download_metadata(self._download_id),
        )

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        return CancelJobResponse(
            job_id=JobId(job_id),
            status=JobStatus.CANCELLED,
            cancellation_requested=True,
        )

    def get_download_metadata(self, download_id: UUID) -> DownloadMetadataDto:
        return DownloadMetadataDto(
            download_id=DownloadId(download_id),
            file_name="backup.zphbackup",
            mime_type="application/octet-stream",
            size_bytes=len(self._payload),
            sha256=sha256(self._payload).hexdigest(),
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
        assert not cancelled()
        metadata = self.get_download_metadata(download_id)
        destination.write_bytes(self._payload)
        progress(len(self._payload), len(self._payload), "Download validado")
        return metadata

    def _accepted(self, kind: JobKind) -> JobAcceptedResponse:
        self._job_id = uuid4()
        return JobAcceptedResponse(
            job_id=JobId(self._job_id),
            kind=kind,
            status=JobStatus.QUEUED,
            poll_after_ms=250,
        )


def _button(panel: PortabilityPanelWidget, name: str) -> QPushButton:
    button = panel.findChild(QPushButton, name)
    assert button is not None
    return button


def test_user_exports_imports_and_restores_backup_through_server_gateway(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_runtime = compose_server_runtime(
        ServerSettings(password="source password", data_directory=tmp_path / "source-server")
    )
    target_runtime = compose_server_runtime(
        ServerSettings(password="target password", data_directory=tmp_path / "target-server")
    )
    try:
        projects = DirectProjectGateway(source_runtime)
        created = projects.create_project("0001234567", idempotency_key="ui-create")
        project_id = created.project.project_id.root
        source_pdf = create_golden_pdf(tmp_path / "client-source.pdf")
        projects.upload_document(project_id, source_pdf, idempotency_key="ui-upload")

        panel = PortabilityPanelWidget(gateway=DirectPortabilityGateway(source_runtime))
        target_panel = PortabilityPanelWidget(gateway=DirectPortabilityGateway(target_runtime))
        qtbot.addWidget(panel)
        qtbot.addWidget(target_panel)
        panel.show()
        target_panel.show()
        project_combo = panel.findChild(QComboBox, "portabilityProjectCombo")
        assert project_combo is not None
        project_combo.setCurrentIndex(project_combo.findData(str(project_id)))
        assert panel.findChild(QPushButton, "portabilityAttachPhotoButton") is None
        assert panel.findChild(QPushButton, "portabilityIntegrityButton") is None
        assert panel.findChild(QPushButton, "portabilityLocatePdfButton") is None
        warnings: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda _parent, _title, message: warnings.append(str(message)),
        )

        project_package = tmp_path / "ui-project.zphproj"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(project_package), "Projeto Zeny (*.zphproj)"),
        )
        qtbot.mouseClick(_button(panel, "portabilityExportButton"), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
        qtbot.waitUntil(lambda: not panel.processando, timeout=10000)
        assert project_package.is_file(), warnings

        backup = tmp_path / "ui-backup.zphbackup"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(backup), "Backup Zeny (*.zphbackup)"),
        )
        qtbot.mouseClick(_button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
        qtbot.waitUntil(lambda: not panel.processando, timeout=10000)
        assert backup.is_file(), warnings

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *_args, **_kwargs: (str(project_package), "Projeto Zeny (*.zphproj)"),
        )
        qtbot.mouseClick(
            _button(target_panel, "portabilityImportButton"), Qt.MouseButton.LeftButton
        )  # type: ignore[no-untyped-call]
        qtbot.waitUntil(lambda: not target_panel.processando, timeout=10000)
        target_combo = target_panel.findChild(QComboBox, "portabilityProjectCombo")
        assert target_combo is not None
        assert target_combo.findData(str(project_id)) >= 0

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *_args, **_kwargs: (str(backup), "Backup Zeny (*.zphbackup)"),
        )
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        restored: list[bool] = []
        target_panel.data_restored.connect(lambda: restored.append(True))
        qtbot.mouseClick(
            _button(target_panel, "portabilityRestoreButton"), Qt.MouseButton.LeftButton
        )  # type: ignore[no-untyped-call]
        qtbot.waitUntil(lambda: not target_panel.processando, timeout=10000)
        assert restored, warnings
        assert (
            DirectPortabilityGateway(target_runtime).list_projects().items[0].project_id.root
            == project_id
        )
    finally:
        target_runtime.close()
        source_runtime.close()


def test_user_refuses_degraded_backup_without_overwriting_destination(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = PanelScenarioGateway()
    panel = PortabilityPanelWidget(gateway=cast(PortabilityGateway, gateway))
    qtbot.addWidget(panel)
    destination = tmp_path / "cancelled.zphbackup"
    destination.write_bytes(b"backup-anterior")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Backup Zeny (*.zphbackup)"),
    )
    questions: list[str] = []

    def reject(_parent: object, _title: str, message: str, *_args: object) -> object:
        questions.append(message)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", reject)
    qtbot.mouseClick(_button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    qtbot.waitUntil(lambda: not panel.processando)

    assert destination.read_bytes() == b"backup-anterior"
    assert gateway.backup_jobs == []
    assert len(questions) == 1
    assert "10000000" in questions[0]
    assert "ausente" in questions[0]


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ("PDF_AUSENTE", "ausente"),
        ("PDF_ADULTERADO", "alterado desde a importação"),
        ("PDF_ILEGIVEL", "ilegível"),
    ],
)
def test_user_explicitly_confirms_each_degraded_backup_problem(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    label: str,
) -> None:
    gateway = PanelScenarioGateway(issue_code=code, issue_label=label)
    panel = PortabilityPanelWidget(gateway=cast(PortabilityGateway, gateway))
    qtbot.addWidget(panel)
    destination = tmp_path / f"confirmed-{code}.zphbackup"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Backup Zeny (*.zphbackup)"),
    )
    questions: list[str] = []

    def accept(_parent: object, _title: str, message: str, *_args: object) -> object:
        questions.append(message)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept)
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)
    qtbot.mouseClick(_button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    qtbot.waitUntil(lambda: not panel.processando)

    assert destination.is_file()
    assert len(gateway.backup_jobs) == 1
    assert gateway.backup_jobs[0].accept_degraded
    assert label in questions[0]
    assert any("criado com ressalvas" in item.casefold() for item in statuses)


def test_cancelled_portability_dialogs_are_correlated_without_gateway_calls(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    gateway = PanelScenarioGateway()
    panel = PortabilityPanelWidget(gateway=cast(PortabilityGateway, gateway))
    qtbot.addWidget(panel)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args, **_kwargs: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: ("", ""))

    panel.criar_backup()
    panel.importar_projeto()
    panel.restaurar_backup()

    for operation in (
        "portability.backup.selection",
        "portability.import.selection",
        "portability.restore.selection",
    ):
        records = [
            record
            for record in app_log_capture.records
            if getattr(record, "operation", None) == operation
        ]
        assert [getattr(record, "status", None) for record in records] == [
            "started",
            "cancelled",
        ]
        assert len({getattr(record, "correlation_id", None) for record in records}) == 1
    assert gateway.backup_jobs == []
    assert gateway.restore_preflights == 0


def test_restore_stops_after_remote_preflight_when_viewer_cannot_release_pdf(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = PanelScenarioGateway()
    backup = tmp_path / "selected.zphbackup"
    backup.write_bytes(b"backup")
    prepared: list[bool] = []

    def refuse_restore_preparation() -> bool:
        prepared.append(True)
        return False

    panel = PortabilityPanelWidget(
        gateway=cast(PortabilityGateway, gateway),
        preparar_restauracao=refuse_restore_preparation,
    )
    qtbot.addWidget(panel)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(backup), "Backup Zeny (*.zphbackup)"),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    panel.restaurar_backup()
    qtbot.waitUntil(lambda: not panel.processando)

    assert gateway.restore_preflights == 1
    assert prepared == [True]
    assert gateway.restore_jobs == []
    assert warnings and "PDF ainda está em uso" in warnings[0]
