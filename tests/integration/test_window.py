from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDockWidget, QFileDialog, QLabel, QMessageBox, QPushButton, QSpinBox
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.bootstrap import create_application, run
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import InspecaoPdf
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
    assert window.findChild(QDockWidget, "humanReviewDock") is not None
    assert window.findChild(QDockWidget, "projectWorkflowDock") is not None
    assert window.findChild(QDockWidget, "projectGraphDock") is not None
    assert window.findChild(QDockWidget, "projectPortabilityDock") is not None
    assert window.review_panel is not None
    assert window.project_panel is not None
    assert window.graph_panel is not None
    assert window.portability_panel is not None
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


@pytest.mark.integration
def test_pdf_viewer_joins_selected_files_as_one_ordered_project(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = create_feature_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.show()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(first), str(second)], "Documentos PDF (*.pdf)"),
    )

    viewer.selecionar_pdf()

    merge_button = viewer.findChild(QPushButton, "mergePdfsIntoProjectButton")
    assert merge_button is not None
    assert merge_button.isEnabled()
    assert viewer.inspecoes == ()

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        merge_button,
        pytest.importorskip("PySide6.QtCore").Qt.MouseButton.LeftButton,
    )

    inspections: tuple[InspecaoPdf, ...] = viewer.inspecoes
    assert [item.documento.nome_arquivo for item in inspections] == [
        "folha-01.pdf",
        "folha-02.pdf",
    ]
    assert not merge_button.isEnabled()
    page_selector = viewer.findChild(QSpinBox, "pdfPageSpinBox")
    assert page_selector is not None
    assert page_selector.maximum() == sum(len(item.paginas) for item in inspections)
    page_selector.setValue(page_selector.maximum())
    assert viewer.inspecao is not None
    assert viewer.inspecao.documento.nome_arquivo == "folha-02.pdf"
    metadata = viewer.findChild(QLabel, "pdfMetadataLabel")
    assert metadata is not None
    assert "Projeto unido: 2 arquivos" in metadata.text()


@pytest.mark.integration
def test_pdf_viewer_keeps_current_project_when_one_selected_file_is_invalid(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = create_feature_pdf(tmp_path / "atual.pdf")
    another = create_golden_pdf(tmp_path / "outra.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.carregar_pdf(current)
    original_inspections = viewer.inspecoes
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    duplicated = viewer.carregar_projeto((another, another))

    loaded = viewer.carregar_projeto((another, tmp_path / "ausente.pdf"))

    assert not duplicated
    assert not loaded
    assert any("duplicado" in message for message in warnings)
    assert viewer.inspecoes == original_inspections
    assert viewer.inspecao == original_inspections[0]
