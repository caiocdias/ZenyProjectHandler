from __future__ import annotations

from collections.abc import Iterator
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
    QTreeWidget,
)
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
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
        conteudo_bruto="POSTE",
        criada_em=datetime(2026, 7, 21, 17, tzinfo=UTC),
    )
    pole_item = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0]
    equipment_item = catalogo_inicial.itens_ativos(CategoriaElemento.EQUIPAMENTO)[0]
    pole_proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence.id,),
        geometria=geometry,
        tipo_catalogo_sugerido_id=pole_item.id,
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
            PontoNormalizado(Decimal("0.70"), Decimal("0.70")),
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
    pole_item = tree.topLevelItem(0)
    assert pole_item is not None
    assert pole_item.text(0).startswith("Poste")
    assert pole_item.childCount() == 1
    equipment_item = pole_item.child(0)
    assert "Equipamento" in equipment_item.text(0)
    assert "instalado em" in equipment_item.text(0)
    assert equipment_item.text(1) == "A instalar"

    state_filter = panel.findChild(QComboBox, "reviewStateFilter")
    assert state_filter is not None
    state_filter.setCurrentIndex(state_filter.findData(EstadoRevisao.CONFLITANTE.value))
    assert tree.topLevelItemCount() == 1
    filtered_pole = tree.topLevelItem(0)
    assert filtered_pole is not None and filtered_pole.childCount() == 1
    state_filter.setCurrentIndex(0)

    pole_item = tree.topLevelItem(0)
    assert pole_item is not None
    tree.setCurrentItem(pole_item)
    assert str(proposal.id) in panel._viewer.view._review_items
    marker = panel._viewer.view._review_items[str(proposal.id)]
    assert marker.path().boundingRect().height() <= 4
    tree.clearSelection()
    marker.setSelected(False)
    marker_position = panel._viewer.view.mapFromScene(marker.sceneBoundingRect().center())
    qtbot.mouseClick(
        panel._viewer.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=marker_position,
    )  # type: ignore[no-untyped-call]
    assert tree.selectedItems()
    assert tree.selectedItems()[0].data(0, Qt.ItemDataRole.UserRole) == str(proposal.id)

    guidance = panel.findChild(QLabel, "analysisResultsGuidance")
    editor = panel.findChild(QGroupBox, "reviewDecisionEditor")
    accept = panel.findChild(QPushButton, "reviewAcceptButton")
    assert guidance is not None and "automaticamente" in guidance.text()
    assert editor is not None and not editor.isVisible()
    assert accept is not None and not accept.isVisible()
