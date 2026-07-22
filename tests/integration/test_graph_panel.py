from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QTableWidget
from pytestqt.qtbot import QtBot
from tests.factories import complete_project
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.graph import NetworkxProjectGraphBuilder
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.project_graph import ServicoGrafoProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Equipamento
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ui.graph_panel import GraphPanelWidget
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget

pytestmark = pytest.mark.integration


def test_graph_panel_rebuilds_filters_views_and_navigates_to_pdf(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    source = create_golden_pdf(tmp_path / "grafo.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)
    page_id = inspection.documento.paginas[0].id
    project = complete_project(catalogo_inicial)
    elements = []
    for element in project.elementos:
        geometry = element.geometria
        if geometry is not None:
            geometry = replace(geometry, pagina_id=page_id)
        if isinstance(element, Equipamento):
            geometry = GeometriaDocumento.ponto(
                page_id,
                PontoNormalizado(Decimal("0.50"), Decimal("0.50")),
            )
        elements.append(replace(element, geometria=geometry))
    project = replace(
        project,
        documentos=(inspection.documento,),
        elementos=tuple(elements),
        terminais=(),
        conexoes_internas=(),
    )
    source_reference = ReferenciaFontePdf(
        documento_id=inspection.documento.id,
        projeto_id=project.id,
        caminho_canonico=source.resolve(),
        sha256=inspection.documento.sha256,
        tamanho_bytes=inspection.tamanho_bytes,
        modificado_em_ns=inspection.modificado_em_ns,
    )
    engine = create_sqlite_engine(tmp_path / "graph-panel.sqlite3")
    upgrade_database(engine)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(source_reference)
        work.commit()

    viewer = PdfViewerWidget(leitor=reader, dpi=72)
    panel = GraphPanelWidget(
        service=ServicoGrafoProjeto(
            lambda: SqlAlchemyUnitOfWork(engine), NetworkxProjectGraphBuilder()
        ),
        viewer=viewer,
    )
    qtbot.addWidget(viewer)
    qtbot.addWidget(panel)
    viewer.show()
    panel.show()

    project_combo = panel.findChild(QComboBox, "graphProjectCombo")
    rebuild = panel.findChild(QPushButton, "graphRebuildButton")
    assert project_combo is not None
    assert rebuild is not None
    project_combo.setCurrentIndex(project_combo.findData(str(project.id)))
    qtbot.mouseClick(rebuild, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    assert panel.canvas.scene().items()
    summary = panel.findChild(QLabel, "graphSummaryLabel")
    assert summary is not None
    assert "Físico:" in summary.text()
    view_combo = panel.findChild(QComboBox, "graphViewCombo")
    assert view_combo is not None
    view_combo.setCurrentIndex(1)
    assert panel.canvas.scene().items()

    table = panel.findChild(QTableWidget, "graphDiagnosticsTable")
    severity = panel.findChild(QComboBox, "graphSeverityFilter")
    assert table is not None
    assert severity is not None
    severity.setCurrentIndex(severity.findText("Erro"))
    assert table.rowCount() >= 1
    severity.setCurrentIndex(0)
    equipment_row = -1
    for row in range(table.rowCount()):
        code_cell = table.item(row, 1)
        if code_cell is not None and code_cell.text() == "EQUIPAMENTO_SEM_TERMINAIS":
            equipment_row = row
            break
    assert equipment_row >= 0
    table.selectRow(equipment_row)
    navigate = panel.findChild(QPushButton, "graphNavigateButton")
    assert navigate is not None
    qtbot.mouseClick(navigate, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    assert viewer.folha_atual == 1
    assert viewer.inspecoes
    assert viewer.view.scene().items()
    engine.dispose()
