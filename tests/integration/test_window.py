from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import create_feature_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.bootstrap import create_application, run
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget


@pytest.mark.integration
def test_main_window_smoke(qtbot: QtBot, tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    application, window = create_application([], settings=settings)
    qtbot.addWidget(window)
    window.show()

    assert application.applicationName() == "Zeny Project Handler"
    assert window.windowTitle() == "Zeny Project Handler"
    assert window.centralWidget().objectName() == "pdfViewerWidget"
    assert window.statusBar().currentMessage() == "Pronto para abrir um PDF"
    assert settings.database_path.is_file()


@pytest.mark.integration
def test_application_smoke_mode_opens_and_closes(tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    exit_code = run(["zeny-project-handler", "--smoke-test"], settings=settings)

    assert exit_code == 0


@pytest.mark.integration
def test_pdf_viewer_navigation_zoom_rotation_and_overlays(qtbot: QtBot, tmp_path: Path) -> None:
    source = create_feature_pdf(tmp_path / "interface.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.resize(800, 600)
    viewer.show()

    viewer.carregar_pdf(source)

    assert viewer.inspecao is not None
    assert viewer.view.scene() is not None
    assert viewer.view.scene().items()
    viewer.definir_sobreposicoes(
        (
            (
                PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
                PontoNormalizado(Decimal("0.5"), Decimal("0.5")),
            ),
        )
    )
    assert len(viewer.view.scene().items()) >= 2

    zoom_before = viewer.view.zoom
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        viewer.findChild(QPushButton, "pdfZoomInButton"),
        pytest.importorskip("PySide6.QtCore").Qt.MouseButton.LeftButton,
    )
    assert viewer.view.zoom > zoom_before
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        viewer.findChild(QPushButton, "pdfRotateButton"),
        pytest.importorskip("PySide6.QtCore").Qt.MouseButton.LeftButton,
    )
    assert viewer.view.scene().items()


@pytest.mark.integration
def test_pdf_viewer_reports_controlled_open_failure(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(str(message)),
    )

    viewer.carregar_pdf(tmp_path / "ausente.pdf")

    assert messages
    assert viewer.inspecao is None
