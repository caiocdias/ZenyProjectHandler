"""E14 Qt transport-only review, navigation and explicit uncertainty regression."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem
from pytestqt.qtbot import QtBot
from tests.e14_symbol_review_fixtures import SymbolReviewFixture, seed_symbol_review
from tests.pdf_fixtures import TEST_RENDER_BUDGET
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_client.ui.review_panel import ReviewPanelWidget
from zeny_project_handler_server.review_api import ReviewApiService

pytestmark = pytest.mark.integration


@pytest.fixture
def e14_panel(
    qtbot: QtBot,
    tmp_path: Path,
) -> Iterator[tuple[SymbolReviewFixture, ReviewPanelWidget, PdfViewerWidget]]:
    fixture = seed_symbol_review(tmp_path / "symbol-ui")
    gateway = LocalTestPdfViewerGateway(budget=TEST_RENDER_BUDGET)
    gateway.register_project(
        fixture.project.id,
        (fixture.source,),
        document_page_ids=tuple(
            (doc.id, tuple(page.id for page in doc.paginas)) for doc in fixture.project.documentos
        ),
    )
    viewer = PdfViewerWidget(gateway=gateway, dpi=72, limite_pixels_tile=1_000_000)
    panel = ReviewPanelWidget(gateway=ReviewApiService(fixture.runtime.core.engine), viewer=viewer)
    qtbot.addWidget(viewer)
    qtbot.addWidget(panel)
    viewer.show()
    panel.show()
    panel._project.setCurrentIndex(1)
    assert panel._session is not None
    try:
        yield fixture, panel, viewer
    finally:
        gateway.close()
        fixture.runtime.close()


def _tree_nodes(root: QTreeWidgetItem) -> Iterator[QTreeWidgetItem]:
    for index in range(root.childCount()):
        node = root.child(index)
        yield node
        yield from _tree_nodes(node)


def test_orphan_symbols_are_visible_once_with_separate_unsupported_group(
    e14_panel: tuple[SymbolReviewFixture, ReviewPanelWidget, PdfViewerWidget],
) -> None:
    _fixture, panel, _viewer = e14_panel
    assert panel._session is not None
    nodes = tuple(_tree_nodes(panel._tree.invisibleRootItem()))
    text = "\n".join(node.text(col) for node in nodes for col in range(6))
    assert "Famílias não suportadas" in text
    assert "Nenhuma identificação neste filtro" not in text
    assert "Pendente" in text
    assert panel._table.rowCount() == 6
    assert len(panel._session.confirmed_elements) == len(_fixture.project.elementos)
    ids = [node.data(0, Qt.ItemDataRole.UserRole) for node in nodes]
    assert all(ids.count(str(item.proposal_id.root)) == 1 for item in panel._session.proposals)


@pytest.mark.parametrize(
    "status", ["exclusive", "conflicting", "unknown", "informative", "unsupported"]
)
def test_symbol_filters_and_selection_keep_details_and_correct_page(
    e14_panel: tuple[SymbolReviewFixture, ReviewPanelWidget, PdfViewerWidget],
    status: str,
) -> None:
    fixture, panel, viewer = e14_panel
    assert panel._session is not None
    combo = panel._symbol_filter
    combo.setCurrentIndex(combo.findData(status))
    matching = [
        item
        for item in panel._session.proposals
        if item.symbol is not None
        and (
            item.symbol.unsupported_family
            if status == "unsupported"
            else item.symbol.exclusive
            if status == "exclusive"
            else item.symbol.status == status
        )
    ]
    assert matching
    assert panel._table.rowCount() == len(matching)
    for item in matching:
        panel._select_proposal_id(str(item.proposal_id.root))
        assert panel._selected_proposal_id == item.proposal_id.root
        page_number = (
            fixture.project.ordem_leitura_paginas.index(item.overlay.geometry.page_id.root) + 1
        )
        assert viewer.folha_atual == page_number
        assert not panel._symbol_details.isHidden()
        assert panel._symbol_details.isVisible()
        details = panel._symbol_details.text()
        assert "Uma ocorrência" in details
        assert "Sem ID exato" in details
        assert "situação: Pendente" in details
        assert panel._situation.currentIndex() == -1
        assert panel._reject.isVisible() and panel._reject.isEnabled()
        assert item.symbol is not None
        if item.symbol.role in {"informativo", "suporte"}:
            assert not panel._accept.isEnabled()
        if item.symbol.status == "conflicting":
            assert "TRANSFORMADOR" in details and "PARA_RAIOS" in details


def test_rejecting_selected_occurrence_does_not_transfer_decision_to_similar_symbols(
    e14_panel: tuple[SymbolReviewFixture, ReviewPanelWidget, PdfViewerWidget],
) -> None:
    _fixture, panel, _viewer = e14_panel
    assert panel._session is not None
    initial = panel._session
    selected = next(
        item for item in initial.proposals if item.symbol and item.symbol.status == "conflicting"
    )
    panel._select_proposal_id(str(selected.proposal_id.root))
    panel._reviewer.setText("Revisor Qt E14")
    panel._reason.setText("Somente a ocorrência selecionada é FP")
    panel.rejeitar_selecionada()
    assert panel._session is not None
    assert len(panel._session.confirmed_elements) == len(initial.confirmed_elements)
    for before in initial.proposals:
        after = next(
            item for item in panel._session.proposals if item.proposal_id == before.proposal_id
        )
        if before.proposal_id == selected.proposal_id:
            assert after.review_state.value == "REJECTED"
            assert after.symbol == before.symbol
        else:
            assert after == before
