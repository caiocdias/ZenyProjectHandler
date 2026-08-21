from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QPushButton
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui.portability_gateway import (
    CancelCallback,
    PortabilityGateway,
    ProgressCallback,
)
from zeny_project_handler_client.ui.portability_panel import PortabilityPanelWidget
from zeny_project_handler_contracts.base import CalloutId, DownloadId, ProjectId
from zeny_project_handler_contracts.common import (
    DownloadMetadataDto,
    NormalizedBoxDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.enums import ProjectState
from zeny_project_handler_contracts.exports import (
    CalloutPositionOverrideDto,
    CreateDeliverableExportRequest,
    DeliverableExportKind,
)
from zeny_project_handler_contracts.projects import (
    ProjectAnalysisSummaryDto,
    ProjectSummaryDto,
    ProjectSummaryListResponse,
)

pytestmark = pytest.mark.integration


class ExportScenarioGateway:
    def __init__(self) -> None:
        self.project_id = uuid4()
        self.download_id = uuid4()
        self.payload = b"arquivo compilado no servidor"
        self.requests: list[CreateDeliverableExportRequest] = []

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> ProjectSummaryListResponse:
        now = datetime.now(UTC)
        return ProjectSummaryListResponse(
            items=(
                ProjectSummaryDto(
                    project_id=ProjectId(self.project_id),
                    service_note="0001234567",
                    state=ProjectState.READY,
                    project_version=7,
                    document_count=1,
                    page_count=2,
                    analysis=ProjectAnalysisSummaryDto(
                        pending_proposals=0,
                        completed_decisions=0,
                    ),
                    created_at=now,
                    updated_at=now,
                ),
            ),
            page=PageMetadataDto(limit=limit, offset=offset, total=1),
        )

    def create_deliverable_export(
        self,
        project_id: UUID,
        request: CreateDeliverableExportRequest,
    ) -> DownloadMetadataDto:
        assert project_id == self.project_id
        self.requests.append(request)
        suffix = ".pdf" if request.kind is DeliverableExportKind.ANNOTATED_PDF else ".xlsx"
        return DownloadMetadataDto(
            download_id=DownloadId(self.download_id),
            file_name=f"0001234567{suffix}",
            mime_type="application/octet-stream",
            size_bytes=len(self.payload),
            sha256=sha256(self.payload).hexdigest(),
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
        assert download_id == self.download_id
        assert not cancelled()
        destination.write_bytes(self.payload)
        progress(len(self.payload), len(self.payload), "Baixando arquivo")
        return DownloadMetadataDto(
            download_id=DownloadId(download_id),
            file_name=destination.name,
            mime_type="application/octet-stream",
            size_bytes=len(self.payload),
            sha256=sha256(self.payload).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )


def _panel(qtbot: QtBot, gateway: ExportScenarioGateway) -> PortabilityPanelWidget:
    panel = PortabilityPanelWidget(gateway=cast(PortabilityGateway, gateway))
    qtbot.addWidget(panel)
    panel.show()
    combo = panel.findChild(QComboBox, "exportProjectCombo")
    assert combo is not None
    combo.setCurrentIndex(combo.findData(str(gateway.project_id)))
    return panel


def _button(panel: PortabilityPanelWidget, name: str) -> QPushButton:
    button = panel.findChild(QPushButton, name)
    assert button is not None
    return button


def test_panel_exposes_only_user_deliverables(qtbot: QtBot) -> None:
    panel = _panel(qtbot, ExportScenarioGateway())
    for name in (
        "exportAnnotatedPdfButton",
        "exportResultsButton",
        "exportDocumentationButton",
        "exportComplianceButton",
    ):
        assert _button(panel, name).isEnabled()
    for obsolete in (
        "portabilityExportButton",
        "portabilityImportButton",
        "portabilityBackupButton",
        "portabilityRestoreButton",
    ):
        assert panel.findChild(QPushButton, obsolete) is None


@pytest.mark.parametrize(
    ("button_name", "kind", "suffix"),
    (
        ("exportAnnotatedPdfButton", DeliverableExportKind.ANNOTATED_PDF, ".pdf"),
        ("exportResultsButton", DeliverableExportKind.RESULTS_XLSX, ".xlsx"),
        ("exportDocumentationButton", DeliverableExportKind.DOCUMENTATION_XLSX, ".xlsx"),
        ("exportComplianceButton", DeliverableExportKind.COMPLIANCE_XLSX, ".xlsx"),
    ),
)
def test_each_action_downloads_the_server_compiled_file(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    button_name: str,
    kind: DeliverableExportKind,
    suffix: str,
) -> None:
    gateway = ExportScenarioGateway()
    panel = _panel(qtbot, gateway)
    selected = tmp_path / f"selecionado-{kind.value.lower()}"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(selected), ""),
    )

    qtbot.mouseClick(_button(panel, button_name), Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    qtbot.waitUntil(lambda: not panel.processando)

    destination = selected.with_suffix(suffix)
    assert destination.read_bytes() == gateway.payload
    assert [item.kind for item in gateway.requests] == [kind]
    assert gateway.requests[0].expected_project_version == 7


def test_pdf_export_forwards_current_callout_positions(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = ExportScenarioGateway()
    override = CalloutPositionOverrideDto(
        callout_id=CalloutId(uuid4()),
        box=NormalizedBoxDto(x="0.1", y="0.2", width="0.3", height="0.4"),
    )
    panel = PortabilityPanelWidget(
        gateway=cast(PortabilityGateway, gateway),
        callout_positions=lambda: (override,),
    )
    qtbot.addWidget(panel)
    combo = panel.findChild(QComboBox, "exportProjectCombo")
    assert combo is not None
    combo.setCurrentIndex(combo.findData(str(gateway.project_id)))
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(tmp_path / "anotado.pdf"), ""),
    )

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "exportAnnotatedPdfButton"),
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(lambda: not panel.processando)

    assert gateway.requests[0].callout_positions == (override,)
