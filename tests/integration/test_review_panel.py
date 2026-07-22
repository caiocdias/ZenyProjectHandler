from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit, QPushButton, QTableWidget
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


def test_review_panel_filters_overlays_and_saves_geometry_adjustment(
    qtbot: QtBot,
    review_panel_context: tuple[Engine, ReviewPanelWidget, PropostaElemento],
) -> None:
    engine, panel, proposal = review_panel_context
    project_combo = panel.findChild(QComboBox, "reviewProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(1)
    table = panel.findChild(QTableWidget, "reviewProposalTable")
    assert table is not None
    assert table.rowCount() == 2

    state_filter = panel.findChild(QComboBox, "reviewStateFilter")
    assert state_filter is not None
    state_filter.setCurrentIndex(state_filter.findData(EstadoRevisao.CONFLITANTE.value))
    assert table.rowCount() == 1
    state_filter.setCurrentIndex(0)

    pole_row = -1
    for row in range(table.rowCount()):
        category_item = table.item(row, 1)
        if category_item is not None and category_item.text() == "POSTE":
            pole_row = row
            break
    assert pole_row >= 0
    table.selectRow(pole_row)
    author = panel.findChild(QLineEdit, "reviewAuthorEdit")
    x_spin = panel.findChild(QDoubleSpinBox, "reviewXSpin")
    accept = panel.findChild(QPushButton, "reviewAcceptButton")
    assert author is not None and x_spin is not None and accept is not None
    author.setText("Caio")
    x_spin.setValue(0.15)
    qtbot.mouseClick(accept, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.obter(proposal.id)
        decision = work.decisoes_revisao.obter_da_proposta(proposal.id)
    assert isinstance(stored, PropostaElemento)
    assert stored.estado_revisao is EstadoRevisao.CONFIRMADA
    assert stored.geometria.pontos[0].x == Decimal("0.15")
    assert decision is not None
    assert decision.decisao is TipoDecisaoRevisao.AJUSTAR
