from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
)
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine
from tests.factories import complete_project
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
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
from zeny_project_handler.ui.review_panel import ReviewPanelWidget

pytestmark = pytest.mark.integration


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
    viewer = PdfViewerWidget(leitor=reader, dpi=72)
    panel = ReviewPanelWidget(service=service, viewer=viewer)
    qtbot.addWidget(viewer)
    qtbot.addWidget(panel)
    viewer.show()
    panel.show()
    try:
        yield engine, panel, pole_proposal
    finally:
        engine.dispose()


def test_results_panel_groups_relationships_and_links_elements_to_pdf(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
    tree = panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert tree is not None
    assert tree.topLevelItemCount() == 1
    region_item = tree.topLevelItem(0)
    assert region_item is not None
    assert region_item.text(0) == "P4"
    assert region_item.text(1) == "1 remover · 1 instalar"
    assert region_item.text(2) == "E 280653 · N 7683008"
    assert "Remover: Poste 11-300" in region_item.toolTip(1)
    assert "Instalar: Equipamento" in region_item.toolTip(1)
    assert region_item.childCount() == 2
    pole_item = region_item.child(0)
    equipment_item = region_item.child(1)
    assert pole_item.text(0) == "Poste 11-300"
    assert pole_item.text(1) == "A remover"
    assert "Equipamento" in equipment_item.text(0)
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


def test_results_panel_has_span_tab_with_length_source(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
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
    panel._session = replace(
        panel._session,
        projeto=complete_project(panel._session.catalogo),
    )

    panel._refresh_spans()

    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Elementos", "Vãos"]
    assert table.rowCount() == 1
    length_item = table.item(0, 4)
    source_item = table.item(0, 5)
    assert length_item is not None and length_item.text() == "31,50 m"
    assert source_item is not None and source_item.text() == "Comprimento informado"
    visibility = table.cellWidget(0, 7)
    assert isinstance(visibility, QToolButton)
    assert visibility.property("spanId")
    assert visibility.isChecked()

    visibility.click()

    assert not visibility.isChecked()
    assert visibility.property("spanId") in {str(item) for item in panel._hidden_span_ids}


def test_span_visibility_button_hides_matching_cable_overlay(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    table = panel.findChild(QTableWidget, "analysisSpanTable")
    assert project_combo is not None
    assert table is not None
    project_combo.setCurrentIndex(1)
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

    visibility = table.cellWidget(0, 7)
    assert isinstance(visibility, QToolButton)
    assert str(cable_proposal.id) in panel._viewer.view._review_items

    visibility.click()

    assert str(cable_proposal.id) not in panel._viewer.view._review_items

    visibility.click()

    assert str(cable_proposal.id) in panel._viewer.view._review_items


def test_cable_link_uses_the_rotated_label_instead_of_the_span_path(
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    _engine, panel, _proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
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
) -> None:
    _engine, review_panel, _proposal = review_panel_context
    panel = DocumentationPanelWidget(
        service=review_panel._service,
        registry=carregar_registro_conformidade_inicial(),
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
    assert findings.topLevelItemCount() >= 3
