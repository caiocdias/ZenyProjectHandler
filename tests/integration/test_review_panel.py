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
from tests.factories import complete_project
from tests.pdf_fixtures import TEST_RENDER_BUDGET, create_golden_pdf
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
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
    TipoDecisaoRevisao,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Cabo, Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler.ui.review_panel import ReviewPanelWidget, _proposal_label

pytestmark = pytest.mark.integration

_LONG_CELL_TEXT = (
    "Texto longo de resultado que deve permanecer totalmente visível quando a coluna fica "
    "estreita e precisa ocupar várias linhas sem reticências"
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
    service = ServicoRevisaoHumana(
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 18, tzinfo=UTC),
    )
    gateway = LocalTestPdfViewerGateway(budget=TEST_RENDER_BUDGET)
    viewer = PdfViewerWidget(
        gateway=gateway,
        dpi=72,
        limite_pixels_tile=min(
            TEST_RENDER_BUDGET.limite_pixels,
            TEST_RENDER_BUDGET.limite_bytes // 7,
        ),
    )
    panel = ReviewPanelWidget(service=service, viewer=viewer)
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
    state_filter.setCurrentIndex(state_filter.findData(EstadoRevisao.CONFLITANTE.value))
    assert tree.topLevelItemCount() == 1
    filtered_region = tree.topLevelItem(0)
    assert filtered_region is not None and filtered_region.childCount() == 1
    state_filter.setCurrentIndex(0)

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

    assert _proposal_label(symbolic) == expected_label


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
    evidence = panel._session.evidencias[0]
    standalone = RegiaoAnalise(
        id=uuid4(),
        pagina_id=evidence.pagina_id,
        geometria=evidence.geometria,
        elemento_ids=(),
        rotulo_ponto="P11",
    )
    panel._session = replace(panel._session, regioes=(standalone,))

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
    project = complete_project(panel._session.catalogo)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    panel._session = replace(
        panel._session,
        projeto=replace(
            project,
            elementos=tuple(
                replace(
                    item,
                    identificador_operacional="V1-2",
                    situacao=cable_situation,
                )
                if item.id == cable.id
                else item
                for item in project.elementos
            ),
        ),
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
        "Situação",
        "Poste de origem",
        "Poste de destino",
        "Cabo",
        "Comprimento",
        "Fonte",
        "Folha",
        "Exibir",
    ]
    identifier_item = table.item(0, 0)
    situation_item = table.item(0, 1)
    cable_item = table.item(0, 4)
    length_item = table.item(0, 5)
    source_item = table.item(0, 6)
    catalog_cable = panel._session.catalogo.item_por_id(cable.tipo_catalogo_id)
    assert identifier_item is not None and identifier_item.text() == "V1-2"
    assert situation_item is not None and situation_item.text() == expected_situation
    assert catalog_cable is not None
    assert cable_item is not None
    assert cable_item.text() == f"{catalog_cable.codigo} — {catalog_cable.descricao}"
    assert length_item is not None and length_item.text() == "31,50 m"
    assert source_item is not None and source_item.text() == "Comprimento informado"
    visibility = table.cellWidget(0, 8)
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
    panel._session = replace(panel._session, projeto=complete_project(panel._session.catalogo))
    panel._refresh_spans()
    tabs.setCurrentIndex(1)
    assert spans.rowCount() == 1
    spans.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
    spans.setColumnWidth(4, 90)
    cable_cell = spans.item(0, 4)
    assert isinstance(cable_cell, QTableWidgetItem)
    cable_cell.setText(_LONG_CELL_TEXT)
    spans.selectRow(0)
    span_visibility = spans.cellWidget(0, 8)
    compact_span_height = spans.rowHeight(0)

    spans_toggle.click()

    qtbot.waitUntil(lambda: spans.rowHeight(0) > compact_span_height)
    assert spans.wordWrap()
    assert spans.textElideMode() is Qt.TextElideMode.ElideNone
    assert spans.currentRow() == 0
    assert spans.cellWidget(0, 8) is span_visibility

    panel._refresh_spans()
    qtbot.waitUntil(lambda: spans.rowHeight(0) > compact_span_height)
    assert spans_toggle.isChecked()
    assert isinstance(spans.cellWidget(0, 8), QToolButton)

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
    project = complete_project(panel._session.catalogo)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    assert cable.geometria is not None
    cable_proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=panel._session.execucao.id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=cable.situacao,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(panel._session.evidencias[0].id,),
        geometria=cable.geometria,
        tipo_catalogo_sugerido_id=cable.tipo_catalogo_id,
        confianca=Decimal("0.95"),
    )
    decision = DecisaoRevisao(
        id=uuid4(),
        proposta_id=cable_proposal.id,
        decisao=TipoDecisaoRevisao.ACEITAR,
        revisor="Caio",
        decidida_em=datetime(2026, 7, 21, 18, tzinfo=UTC),
        elemento_confirmado_id=cable.id,
    )
    region = RegiaoAnalise(
        id=uuid4(),
        pagina_id=cable.geometria.pagina_id,
        geometria=cable.geometria,
        elemento_ids=(cable_proposal.id,),
    )
    panel._session = replace(
        panel._session,
        projeto=project,
        propostas=(cable_proposal,),
        regioes=(region,),
        decisoes=(decision,),
    )
    panel._page_id = cable.geometria.pagina_id

    panel._refresh_spans()
    panel._refresh_proposals()

    visibility = table.cellWidget(0, 8)
    assert isinstance(visibility, QToolButton)
    assert str(cable_proposal.id) in panel._viewer.view._review_items

    visibility.click()

    assert str(cable_proposal.id) not in panel._viewer.view._review_items

    visibility.click()

    assert str(cable_proposal.id) in panel._viewer.view._review_items


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
    page_id = panel._session.projeto.documentos[0].paginas[0].id
    label_geometry = GeometriaDocumento.poligono(
        page_id,
        (
            PontoNormalizado(Decimal("0.40"), Decimal("0.30")),
            PontoNormalizado(Decimal("0.60"), Decimal("0.40")),
            PontoNormalizado(Decimal("0.58"), Decimal("0.44")),
            PontoNormalizado(Decimal("0.38"), Decimal("0.34")),
        ),
    )
    label = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=panel._session.execucao.id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=label_geometry,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="B-2-CAA",
        criada_em=datetime(2026, 7, 21, 17, tzinfo=UTC),
    )
    span_geometry = GeometriaDocumento.polilinha(
        page_id,
        (
            PontoNormalizado(Decimal("0.05"), Decimal("0.05")),
            PontoNormalizado(Decimal("0.95"), Decimal("0.95")),
        ),
    )
    cable_proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=panel._session.execucao.id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(label.id,),
        geometria=span_geometry,
        codigo_observado="B-2-CAA",
        atributos_sugeridos=(("evidencia_rotulo_id", str(label.id)),),
        confianca=Decimal("0.95"),
    )
    panel._session = replace(
        panel._session,
        propostas=(cable_proposal,),
        evidencias=(label,),
    )
    panel._page_id = page_id

    panel._update_review_overlays((cable_proposal,))

    proposal_id = str(cable_proposal.id)
    marker = panel._viewer.view._review_items[proposal_id]
    first = marker.path().elementAt(0)
    second = marker.path().elementAt(1)
    assert marker.path().boundingRect().width() < 30
    assert abs(first.y - second.y) > 1
    assert panel._viewer.view._review_geometries[proposal_id] == span_geometry
    editable_geometry = panel._viewer.geometria_proposta(proposal_id)
    assert editable_geometry is not None
    assert editable_geometry.tipo is span_geometry.tipo
    assert float(editable_geometry.pontos[0].x) == pytest.approx(0.05)
    assert float(editable_geometry.pontos[0].y) == pytest.approx(0.05)
    assert float(editable_geometry.pontos[1].x) == pytest.approx(0.95)
    assert float(editable_geometry.pontos[1].y) == pytest.approx(0.95)

    legacy_proposal = replace(cable_proposal, atributos_sugeridos=())
    panel._session = replace(panel._session, propostas=(legacy_proposal,))
    panel._update_review_overlays((legacy_proposal,))

    legacy_marker = panel._viewer.view._review_items[proposal_id]
    assert legacy_marker.path().boundingRect().width() < 30


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
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_panel._service.carregar_sessao_semantica,
    )
    project_id = review_panel._service.listar_projetos()[0].projeto_id
    analysis_service.executar(project_id)
    panel = DocumentationPanelWidget(
        service=review_panel._service,
        registry_service=registry_service,
        analysis_service=analysis_service,
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

    project.setCurrentIndex(1)

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
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_panel._service.carregar_sessao_semantica,
    )
    project_id = review_panel._service.listar_projetos()[0].projeto_id
    analysis_service.executar(project_id)
    panel = DocumentationPanelWidget(
        service=review_panel._service,
        registry_service=registry_service,
        analysis_service=analysis_service,
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

    project.setCurrentIndex(1)
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
