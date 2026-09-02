from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
)
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine
from tests.market_fakes import FakeClassificadorMercado
from tests.pdf_fixtures import TEST_RENDER_BUDGET, create_golden_pdf
from tests.remote_gateways import SynchronousDocumentationGateway
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_client.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_client.ui.review_panel import ReviewPanelWidget
from zeny_project_handler_contracts.base import ElementId, ProposalId, RegionId
from zeny_project_handler_contracts.common import NormalizedPointDto as DtoPoint
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewState,
    SpanLengthSource,
    SpanType,
)
from zeny_project_handler_contracts.review import AnalysisRegionDto, DetectedSpanDto
from zeny_project_handler_server.review_api import ReviewApiService, _proposal_label

pytestmark = pytest.mark.integration

_LONG_CELL_TEXT = (
    "Texto longo de resultado que deve permanecer totalmente visível quando a coluna fica "
    "estreita e precisa ocupar várias linhas sem reticências"
)


def _span_dto(
    panel: ReviewPanelWidget,
    *,
    situation: ElementSituation = ElementSituation.INSTALL,
    situation_label: str = "A instalar",
    proposal_id: ProposalId | None = None,
) -> DetectedSpanDto:
    assert panel._session is not None
    proposal = panel._session.proposals[0]
    return DetectedSpanDto(
        span_id=uuid4(),
        proposal_id=proposal_id,
        start_point_id=uuid4(),
        end_point_id=uuid4(),
        cable_element_id=ElementId(uuid4()),
        label="V1-2",
        span_type=SpanType.CONNECTION_BRANCH,
        span_type_label="Ramal de conexão",
        situation=situation,
        situation_label=situation_label,
        start_label="Poste P1",
        end_label="Poste P2",
        cable_label="B-2-CAA — Cabo protegido",
        length="31.5",
        length_label="31,50 m",
        length_source=SpanLengthSource.DRAWING_LABEL,
        length_source_label="Comprimento informado",
        page_label="Folha 1",
        geometry=proposal.overlay.geometry,
        evidence=(),
    )


def _assert_word_wrap_control(button: QToolButton) -> None:
    assert button.text() == "Quebrar linhas"
    assert button.isCheckable()
    assert button.toolTip()
    assert button.accessibleName() == "Quebrar linhas"
    assert button.focusPolicy() is not Qt.FocusPolicy.NoFocus


def _has_valid_size_hint(item: QTreeWidgetItem) -> bool:
    return item.sizeHint(0).isValid()


def _exercise_tree_word_wrap(
    qtbot: QtBot,
    *,
    tree: QTreeWidget,
    toggle: QToolButton,
    item: QTreeWidgetItem,
    column: int,
    embedded_column: int | None = None,
) -> int:
    tree.header().resizeSection(column, 180)
    item.setText(column, _LONG_CELL_TEXT)
    tree.setCurrentItem(item)
    qtbot.waitUntil(lambda: tree.visualItemRect(item).height() > 0)
    compact_height = tree.visualItemRect(item).height()
    embedded = tree.itemWidget(item, embedded_column) if embedded_column is not None else None

    toggle.click()

    qtbot.waitUntil(lambda: item.sizeHint(0).height() > compact_height)
    wrapped_height = item.sizeHint(0).height()
    assert tree.wordWrap()
    assert tree.textElideMode() is Qt.TextElideMode.ElideNone
    assert not tree.uniformRowHeights()
    assert tree.currentItem() is item
    if embedded_column is not None:
        assert tree.itemWidget(item, embedded_column) is embedded

    tree.header().resizeSection(column, 80)
    qtbot.waitUntil(lambda: item.sizeHint(0).height() > wrapped_height)
    toggle.click()

    qtbot.waitUntil(lambda: not item.sizeHint(0).isValid())
    qtbot.waitUntil(lambda: tree.visualItemRect(item).height() <= compact_height)
    assert tree.uniformRowHeights()
    assert tree.textElideMode() is not Qt.TextElideMode.ElideNone
    assert tree.currentItem() is item
    if embedded_column is not None:
        assert tree.itemWidget(item, embedded_column) is embedded
    return compact_height


@pytest.fixture
def review_panel_context(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> Iterator[tuple[Engine, ReviewPanelWidget, PropostaElemento]]:
    source = create_golden_pdf(tmp_path / "revisao.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)
    project = Projeto(
        id=uuid4(),
        nome="Projeto para revisão",
        catalogo_versao_id=catalogo_inicial.id,
        criado_em=datetime(2026, 7, 21, 17, tzinfo=UTC),
        documentos=(inspection.documento,),
    )
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="interpretador-teste",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 21, 17, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 17, 1, tzinfo=UTC),
    )
    page_id = inspection.documento.paginas[0].id
    geometry = GeometriaDocumento.caixa(
        page_id,
        PontoNormalizado(Decimal("0.10"), Decimal("0.10")),
        PontoNormalizado(Decimal("0.20"), Decimal("0.20")),
    )
    evidence = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=execution.id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=geometry,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="P4",
        criada_em=datetime(2026, 7, 21, 17, tzinfo=UTC),
    )
    pole_item = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0]
    equipment_item = catalogo_inicial.itens_ativos(CategoriaElemento.EQUIPAMENTO)[0]
    pole_proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.REMOVER,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence.id,),
        geometria=geometry,
        tipo_catalogo_sugerido_id=pole_item.id,
        codigo_observado="11-300",
        atributos_sugeridos=(
            ("coordenada_leste", 280653),
            ("coordenada_norte", 7683008),
        ),
        confianca=Decimal("0.90"),
    )
    conflict = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.EQUIPAMENTO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        evidencia_ids=(evidence.id,),
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.22"), Decimal("0.28")),
        ),
        tipo_catalogo_sugerido_id=equipment_item.id,
        confianca=Decimal("0.70"),
    )
    relation = PropostaRelacao(
        id=uuid4(),
        execucao_id=execution.id,
        origem_referencia_id=conflict.id,
        destino_referencia_id=pole_proposal.id,
        tipo_relacao="INSTALADO_EM",
        evidencia_ids=(evidence.id,),
        confianca=Decimal("0.70"),
    )
    engine = create_sqlite_engine(tmp_path / "review-panel.sqlite3")
    upgrade_database(engine)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(
            ReferenciaFontePdf(
                documento_id=inspection.documento.id,
                projeto_id=project.id,
                caminho_canonico=inspection.caminho_origem,
                sha256=inspection.documento.sha256,
                tamanho_bytes=inspection.tamanho_bytes,
                modificado_em_ns=inspection.modificado_em_ns,
            )
        )
        work.execucoes_analise.salvar(execution)
        work.evidencias.salvar(evidence)
        work.propostas.salvar(pole_proposal)
        work.propostas.salvar(conflict)
        work.propostas.salvar(relation)
        work.commit()
    gateway = LocalTestPdfViewerGateway(budget=TEST_RENDER_BUDGET)
    gateway.register_project(
        project.id,
        (source,),
        document_page_ids=tuple(
            (document.id, tuple(page.id for page in document.paginas))
            for document in project.documentos
        ),
    )
    viewer = PdfViewerWidget(
        gateway=gateway,
        dpi=72,
        limite_pixels_tile=min(
            TEST_RENDER_BUDGET.limite_pixels,
            TEST_RENDER_BUDGET.limite_bytes // 7,
        ),
    )
    panel = ReviewPanelWidget(gateway=ReviewApiService(engine), viewer=viewer)
    qtbot.addWidget(viewer)
    qtbot.addWidget(panel)
    viewer.show()
    panel.show()
    try:
        yield engine, panel, pole_proposal
    finally:
        gateway.close()
        engine.dispose()


def test_results_panel_groups_relationships_and_links_elements_to_pdf(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel._viewer._current_transformer is not None)
    tree = panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert tree is not None
    assert tree.topLevelItemCount() == 1
    region_item = tree.topLevelItem(0)
    assert region_item is not None
    assert region_item.text(0) == "P4"
    assert region_item.text(1) == "1 remover · 1 instalar"
    assert region_item.text(2) == "E 280653 · N 7683008"
    assert "Remover: Poste 11-300" in region_item.toolTip(1)
    assert "Instalar: Transformador" in region_item.toolTip(1)
    assert region_item.childCount() == 2
    pole_item = region_item.child(0)
    equipment_item = region_item.child(1)
    assert pole_item.text(0) == "Poste 11-300"
    assert pole_item.text(1) == "A remover"
    assert equipment_item.text(0) == "Transformador"
    assert "instalado em" in equipment_item.text(4)
    assert equipment_item.text(1) == "A instalar"
    tree.setCurrentItem(region_item)
    assert panel._viewer._overlays

    state_filter = panel.findChild(QComboBox, "reviewStateFilter")
    assert state_filter is not None
    state_filter.setCurrentIndex(state_filter.findData(ReviewState.CONFLICTING.value))
    assert tree.topLevelItemCount() == 1
    filtered_region = tree.topLevelItem(0)
    assert filtered_region is not None and filtered_region.childCount() == 1
    state_filter.setCurrentIndex(0)

    situation_filter = panel.findChild(QComboBox, "reviewSituationFilter")
    assert situation_filter is not None
    situation_filter.setCurrentIndex(situation_filter.findData(ElementSituation.REMOVE.value))
    filtered_region = tree.topLevelItem(0)
    assert filtered_region is not None and filtered_region.childCount() == 1
    assert all(
        item.situation is ElementSituation.REMOVE for item in panel._viewer._review_proposals
    )
    situation_filter.setCurrentIndex(0)

    region_item = tree.topLevelItem(0)
    assert region_item is not None
    pole_item = region_item.child(0)
    tree.setCurrentItem(pole_item)
    assert str(proposal.id) in panel._viewer.view._review_items
    marker = panel._viewer.view._review_items[str(proposal.id)]
    assert marker.path().boundingRect().height() <= 4
    tree.clearSelection()
    marker.setSelected(False)
    marker.setSelected(True)
    assert tree.selectedItems()
    assert tree.selectedItems()[0].data(0, Qt.ItemDataRole.UserRole) == str(proposal.id)

    guidance = panel.findChild(QLabel, "analysisResultsGuidance")
    editor = panel.findChild(QGroupBox, "reviewDecisionEditor")
    accept = panel.findChild(QPushButton, "reviewAcceptButton")
    assert guidance is not None and "automaticamente" in guidance.text()
    assert editor is not None and not editor.isVisible()
    assert accept is not None and not accept.isVisible()


@pytest.mark.parametrize(
    ("equipment_class", "expected_label"),
    (
        ("ATERRAMENTO", "Aterramento"),
        ("PARA_RAIOS_MT", "Para-raios MT"),
        ("PARA_RAIOS_BT", "Para-raios BT"),
    ),
)
def test_symbolic_equipment_uses_identified_type_as_label(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
    catalogo_inicial: CatalogoTecnico,
    equipment_class: str,
    expected_label: str,
) -> None:
    _engine, _panel, proposal = review_panel_context
    symbolic = replace(
        proposal,
        categoria=CategoriaElemento.EQUIPAMENTO,
        tipo_catalogo_sugerido_id=None,
        codigo_observado=expected_label.upper(),
        atributos_sugeridos=(
            ("classe_equipamento", equipment_class),
            ("reconhecido_por_simbologia", True),
        ),
    )

    assert _proposal_label(symbolic, catalogo_inicial) == expected_label


def test_results_panel_keeps_recognized_point_without_elements(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    tree = panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert project_combo is not None
    assert tree is not None
    project_combo.setCurrentIndex(1)
    assert panel._session is not None
    original = panel._session.regions[0]
    standalone = AnalysisRegionDto(
        region_id=RegionId(uuid4()),
        page_id=original.page_id,
        label="P11",
        location_label="P11 · revisão.pdf · página 1",
        coordinate_label="Sem coordenada identificada",
        action_summary="Ponto identificado",
        detail_summary="Identificador de ponto reconhecido no PDF",
        geometry=original.geometry,
        proposal_ids=(),
        relation_proposal_ids=(),
    )
    panel._session = panel._session.model_copy(update={"regions": (standalone,)})

    panel._refresh_proposals()

    assert tree.topLevelItemCount() == 1
    point_item = tree.topLevelItem(0)
    assert point_item is not None
    assert point_item.text(0) == "P11"
    assert point_item.text(1) == "Ponto identificado"
    assert point_item.text(3) == "0 elemento(s)"
    assert point_item.childCount() == 0


@pytest.mark.parametrize(
    ("cable_situation", "expected_situation"),
    (
        (SituacaoProjeto.INSTALAR, "A instalar"),
        (SituacaoProjeto.REMOVER, "A remover"),
        (SituacaoProjeto.EXISTENTE, "Existente"),
        (SituacaoProjeto.ALTERAR, "A alterar"),
    ),
)
def test_results_panel_has_span_tab_with_situation_cable_and_length_source(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
    cable_situation: SituacaoProjeto,
    expected_situation: str,
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    tabs = panel.findChild(QTabWidget, "analysisResultTabs")
    table = panel.findChild(QTableWidget, "analysisSpanTable")
    assert project_combo is not None
    assert tabs is not None
    assert table is not None
    project_combo.setCurrentIndex(1)
    assert panel._session is not None
    situation = {
        SituacaoProjeto.INSTALAR: ElementSituation.INSTALL,
        SituacaoProjeto.REMOVER: ElementSituation.REMOVE,
        SituacaoProjeto.EXISTENTE: ElementSituation.EXISTING,
        SituacaoProjeto.ALTERAR: ElementSituation.CHANGE,
    }[cable_situation]
    panel._session = panel._session.model_copy(
        update={
            "spans": (
                _span_dto(
                    panel,
                    situation=situation,
                    situation_label=expected_situation,
                ),
            )
        }
    )

    panel._refresh_spans()

    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Elementos", "Vãos"]
    assert table.rowCount() == 1
    headers: list[str] = []
    for index in range(table.columnCount()):
        header = table.horizontalHeaderItem(index)
        assert header is not None
        headers.append(header.text())
    assert headers == [
        "Vão",
        "Tipo",
        "Situação",
        "Ponto de origem",
        "Ponto de destino",
        "Cabo",
        "Comprimento",
        "Fonte",
        "Folha",
        "Exibir",
    ]
    identifier_item = table.item(0, 0)
    type_item = table.item(0, 1)
    situation_item = table.item(0, 2)
    cable_item = table.item(0, 5)
    length_item = table.item(0, 6)
    source_item = table.item(0, 7)
    assert identifier_item is not None and identifier_item.text() == "V1-2"
    assert type_item is not None and type_item.text() == "Ramal de conexão"
    assert situation_item is not None and situation_item.text() == expected_situation
    assert cable_item is not None
    assert cable_item.text() == "B-2-CAA — Cabo protegido"
    assert length_item is not None and length_item.text() == "31,50 m"
    assert source_item is not None and source_item.text() == "Comprimento informado"
    visibility = table.cellWidget(0, 9)
    assert isinstance(visibility, QToolButton)
    assert visibility.property("spanId")
    assert visibility.isChecked()

    visibility.click()

    assert not visibility.isChecked()
    assert visibility.property("spanId") in {str(item) for item in panel._hidden_span_ids}


def test_review_tables_toggle_word_wrap_and_keep_interactions_after_reload(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    tabs = panel.findChild(QTabWidget, "analysisResultTabs")
    tree = panel.findChild(QTreeWidget, "analysisRelationshipTree")
    spans = panel.findChild(QTableWidget, "analysisSpanTable")
    elements_toggle = panel.findChild(QToolButton, "analysisElementsWordWrapButton")
    spans_toggle = panel.findChild(QToolButton, "analysisSpansWordWrapButton")
    assert project_combo is not None and tabs is not None
    assert tree is not None and spans is not None
    assert elements_toggle is not None and spans_toggle is not None
    _assert_word_wrap_control(elements_toggle)
    _assert_word_wrap_control(spans_toggle)

    project_combo.setCurrentIndex(1)
    region = tree.topLevelItem(0)
    assert region is not None
    item = next(
        region.child(index)
        for index in range(region.childCount())
        if region.child(index).data(0, Qt.ItemDataRole.UserRole) == str(proposal.id)
    )
    item.setText(4, _LONG_CELL_TEXT)
    tree.header().resizeSection(4, 180)
    tree.setCurrentItem(item)
    visibility = tree.itemWidget(item, 5)
    compact_tree_height = tree.visualItemRect(item).height()

    elements_toggle.click()

    qtbot.waitUntil(lambda: item.sizeHint(0).height() > compact_tree_height)
    first_wrapped_height = item.sizeHint(0).height()
    assert tree.wordWrap()
    assert tree.textElideMode() is Qt.TextElideMode.ElideNone
    assert not tree.uniformRowHeights()
    assert tree.currentItem() is item
    assert tree.itemWidget(item, 5) is visibility

    tree.header().resizeSection(4, 80)
    qtbot.waitUntil(lambda: item.sizeHint(0).height() > first_wrapped_height)
    panel._refresh_proposals()
    reloaded_region = tree.topLevelItem(0)
    assert reloaded_region is not None
    reloaded_item = next(
        reloaded_region.child(index)
        for index in range(reloaded_region.childCount())
        if reloaded_region.child(index).data(0, Qt.ItemDataRole.UserRole) == str(proposal.id)
    )
    qtbot.waitUntil(lambda: reloaded_item.sizeHint(0).height() > compact_tree_height)
    assert elements_toggle.isChecked()
    tree.setCurrentItem(reloaded_item)

    elements_toggle.click()

    qtbot.waitUntil(lambda: not reloaded_item.sizeHint(0).isValid())
    assert tree.uniformRowHeights()
    assert tree.textElideMode() is not Qt.TextElideMode.ElideNone
    assert tree.currentItem() is reloaded_item

    assert panel._session is not None
    panel._session = panel._session.model_copy(update={"spans": (_span_dto(panel),)})
    panel._refresh_spans()
    tabs.setCurrentIndex(1)
    assert spans.rowCount() == 1
    spans.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
    spans.setColumnWidth(5, 90)
    cable_cell = spans.item(0, 5)
    assert isinstance(cable_cell, QTableWidgetItem)
    cable_cell.setText(_LONG_CELL_TEXT)
    spans.selectRow(0)
    span_visibility = spans.cellWidget(0, 9)
    compact_span_height = spans.rowHeight(0)

    spans_toggle.click()

    qtbot.waitUntil(lambda: spans.rowHeight(0) > compact_span_height)
    assert spans.wordWrap()
    assert spans.textElideMode() is Qt.TextElideMode.ElideNone
    assert spans.currentRow() == 0
    assert spans.cellWidget(0, 9) is span_visibility

    panel._refresh_spans()
    qtbot.waitUntil(lambda: spans.rowHeight(0) > compact_span_height)
    assert spans_toggle.isChecked()
    assert isinstance(spans.cellWidget(0, 9), QToolButton)

    spans.selectRow(0)
    spans_toggle.click()

    qtbot.waitUntil(lambda: spans.rowHeight(0) <= compact_span_height)
    assert spans.textElideMode() is not Qt.TextElideMode.ElideNone
    assert spans.currentRow() == 0


def test_span_visibility_button_hides_matching_cable_overlay(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    table = panel.findChild(QTableWidget, "analysisSpanTable")
    assert project_combo is not None
    assert table is not None
    project_combo.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel._viewer._current_transformer is not None)
    assert panel._session is not None
    proposal = panel._session.proposals[0]
    panel._session = panel._session.model_copy(
        update={"spans": (_span_dto(panel, proposal_id=proposal.proposal_id),)}
    )
    panel._page_id = proposal.overlay.geometry.page_id.root

    panel._refresh_spans()
    panel._refresh_proposals()

    visibility = table.cellWidget(0, 9)
    assert isinstance(visibility, QToolButton)
    proposal_id = str(proposal.proposal_id.root)
    assert proposal_id in panel._viewer.view._review_items

    visibility.click()

    assert proposal_id not in panel._viewer.view._review_items

    visibility.click()

    assert proposal_id in panel._viewer.view._review_items


def test_cable_link_uses_the_rotated_label_instead_of_the_span_path(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel._viewer._current_transformer is not None)
    assert panel._session is not None
    original = panel._session.proposals[0]
    page_id = original.overlay.geometry.page_id
    label_geometry = original.overlay.geometry.model_copy(
        update={
            "kind": ReviewGeometryKind.POLYGON,
            "points": (
                DtoPoint(x="0.40", y="0.30"),
                DtoPoint(x="0.60", y="0.40"),
                DtoPoint(x="0.58", y="0.44"),
                DtoPoint(x="0.38", y="0.34"),
            ),
        }
    )
    span_geometry = original.overlay.geometry.model_copy(
        update={
            "kind": ReviewGeometryKind.POLYLINE,
            "points": (
                DtoPoint(x="0.05", y="0.05"),
                DtoPoint(x="0.95", y="0.95"),
            ),
        }
    )
    cable_proposal = original.model_copy(
        update={
            "category": ElementCategory.CABLE,
            "label": "B-2-CAA",
            "overlay": original.overlay.model_copy(
                update={"geometry": span_geometry, "link_geometry": label_geometry}
            ),
        }
    )
    panel._session = panel._session.model_copy(update={"proposals": (cable_proposal,)})
    panel._page_id = page_id.root

    panel._update_review_overlays((cable_proposal,))

    proposal_id = str(cable_proposal.proposal_id.root)
    marker = panel._viewer.view._review_items[proposal_id]
    first = marker.path().elementAt(0)
    second = marker.path().elementAt(1)
    assert marker.path().boundingRect().width() < 30
    assert abs(first.y - second.y) > 1
    editable_geometry = panel._viewer.geometria_proposta(proposal_id)
    assert editable_geometry is not None
    assert editable_geometry.kind is ReviewGeometryKind.POLYLINE
    assert float(editable_geometry.points[0].x) == pytest.approx(0.05)
    assert float(editable_geometry.points[0].y) == pytest.approx(0.05)
    assert float(editable_geometry.points[1].x) == pytest.approx(0.95)
    assert float(editable_geometry.points[1].y) == pytest.approx(0.95)


def test_result_visibility_can_hide_a_whole_point_or_one_element(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, pole = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel._viewer._current_transformer is not None)

    tree = panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert tree is not None
    region_item = tree.topLevelItem(0)
    assert region_item is not None
    region_button = tree.itemWidget(region_item, 5)
    assert isinstance(region_button, QToolButton)
    pole_item = next(
        region_item.child(index)
        for index in range(region_item.childCount())
        if region_item.child(index).data(0, Qt.ItemDataRole.UserRole) == str(pole.id)
    )
    pole_button = tree.itemWidget(pole_item, 5)
    assert isinstance(pole_button, QToolButton)
    other_ids = set(panel._viewer.view._review_items) - {str(pole.id)}
    assert other_ids
    assert str(pole.id) in panel._viewer.view._review_items

    pole_button.click()

    assert str(pole.id) not in panel._viewer.view._review_items
    assert other_ids <= set(panel._viewer.view._review_items)

    region_button.click()

    assert not panel._viewer.view._review_items
    assert not pole_button.isEnabled()

    region_button.click()

    assert pole_button.isEnabled()
    assert str(pole.id) not in panel._viewer.view._review_items
    assert other_ids <= set(panel._viewer.view._review_items)

    pole_button.click()

    assert str(pole.id) in panel._viewer.view._review_items


def test_documentation_panel_has_own_document_and_compliance_views(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
    tmp_path: Path,
) -> None:
    engine, review_panel, _proposal = review_panel_context

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    registry_service = ServicoRegistroRegrasConformidade(
        unit_of_work,
        diretorio_dados=tmp_path / "compliance-data",
    )
    registry_service.inicializar(carregar_registro_conformidade_inicial())
    review_service = ServicoRevisaoHumana(unit_of_work)
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_service.carregar_sessao_semantica,
        classificador_mercado=FakeClassificadorMercado(),
    )
    project_id = review_service.listar_projetos()[0].projeto_id
    execution = analysis_service.executar(project_id)
    assert execution.itens_documentais
    gateway = SynchronousDocumentationGateway(
        engine=engine,
        data_directory=tmp_path / "compliance-data",
        review_service=review_service,
        analysis_service=analysis_service,
        registry_service=registry_service,
    )
    assert gateway.get_documentation(project_id).sections
    assert gateway.get_latest_compliance(project_id) is not None
    panel = DocumentationPanelWidget(
        gateway=gateway,
        viewer=review_panel._viewer,
    )
    qtbot.addWidget(panel)
    panel.show()
    project = panel.findChild(QComboBox, "documentationProjectCombo")
    documents = panel.findChild(QTreeWidget, "documentationTree")
    findings = panel.findChild(QTreeWidget, "complianceFindingsTree")
    assert project is not None
    assert documents is not None
    assert findings is not None

    panel.abrir_projeto(project_id)

    assert panel._documentation is not None and panel._documentation.sections
    assert documents is panel._documents
    assert documents.topLevelItemCount() == 1
    document_root = documents.topLevelItem(0)
    assert document_root is not None
    assert document_root.childCount() >= 3
    assert findings.topLevelItemCount() >= 2


def test_documentation_tables_toggle_word_wrap_and_recalculate_after_reload(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
    tmp_path: Path,
) -> None:
    engine, review_panel, _proposal = review_panel_context

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    registry_service = ServicoRegistroRegrasConformidade(
        unit_of_work,
        diretorio_dados=tmp_path / "wrap-compliance-data",
    )
    registry_service.inicializar(carregar_registro_conformidade_inicial())
    review_service = ServicoRevisaoHumana(unit_of_work)
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_service.carregar_sessao_semantica,
        classificador_mercado=FakeClassificadorMercado(),
    )
    project_id = review_service.listar_projetos()[0].projeto_id
    execution = analysis_service.executar(project_id)
    assert execution.itens_documentais
    gateway = SynchronousDocumentationGateway(
        engine=engine,
        data_directory=tmp_path / "wrap-compliance-data",
        review_service=review_service,
        analysis_service=analysis_service,
        registry_service=registry_service,
    )
    assert gateway.get_documentation(project_id).sections
    assert gateway.get_latest_compliance(project_id) is not None
    panel = DocumentationPanelWidget(
        gateway=gateway,
        viewer=review_panel._viewer,
    )
    qtbot.addWidget(panel)
    panel.show()

    project = panel.findChild(QComboBox, "documentationProjectCombo")
    tabs = panel.findChild(QTabWidget, "documentationTabs")
    documents = panel.findChild(QTreeWidget, "documentationTree")
    findings = panel.findChild(QTreeWidget, "complianceFindingsTree")
    rules = panel.findChild(QTreeWidget, "complianceRulesTree")
    documents_toggle = panel.findChild(QToolButton, "documentationWordWrapButton")
    findings_toggle = panel.findChild(QToolButton, "complianceFindingsWordWrapButton")
    rules_toggle = panel.findChild(QToolButton, "complianceRulesWordWrapButton")
    assert project is not None and tabs is not None
    assert documents is not None and findings is not None and rules is not None
    assert documents_toggle is not None
    assert findings_toggle is not None
    assert rules_toggle is not None
    for toggle in (documents_toggle, findings_toggle, rules_toggle):
        _assert_word_wrap_control(toggle)

    panel.abrir_projeto(project_id)
    assert panel._documentation is not None and panel._documentation.sections
    assert documents is panel._documents
    document_root = documents.topLevelItem(0)
    finding = findings.topLevelItem(0)
    rule = rules.topLevelItem(0)
    assert document_root is not None and document_root.childCount()
    document_group = document_root.child(0)
    assert document_group is not None and document_group.childCount()
    document_item = document_group.child(0)
    assert document_item is not None and finding is not None and rule is not None

    tabs.setCurrentIndex(0)
    _exercise_tree_word_wrap(
        qtbot,
        tree=documents,
        toggle=documents_toggle,
        item=document_item,
        column=2,
    )
    tabs.setCurrentIndex(1)
    _exercise_tree_word_wrap(
        qtbot,
        tree=findings,
        toggle=findings_toggle,
        item=finding,
        column=2,
        embedded_column=9,
    )
    tabs.setCurrentIndex(2)
    _exercise_tree_word_wrap(
        qtbot,
        tree=rules,
        toggle=rules_toggle,
        item=rule,
        column=2,
    )

    for tree, toggle in (
        (documents, documents_toggle),
        (findings, findings_toggle),
        (rules, rules_toggle),
    ):
        tree.header().resizeSection(2, 80)
        toggle.click()
    panel._load_persisted_result()
    panel._populate_rules()

    for index, (tree, toggle) in enumerate(
        (
            (documents, documents_toggle),
            (findings, findings_toggle),
            (rules, rules_toggle),
        )
    ):
        tabs.setCurrentIndex(index)
        item = tree.topLevelItem(0)
        assert item is not None
        qtbot.waitUntil(partial(_has_valid_size_hint, item))
        assert toggle.isChecked()
        assert tree.textElideMode() is Qt.TextElideMode.ElideNone
        assert not tree.uniformRowHeights()
    reloaded_finding = findings.topLevelItem(0)
    assert reloaded_finding is not None
    assert isinstance(findings.itemWidget(reloaded_finding, 9), QToolButton)
