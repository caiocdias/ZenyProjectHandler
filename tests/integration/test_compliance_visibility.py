# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QPushButton, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem
from pytestqt.qtbot import QtBot

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_callouts import CalloutConformidade
from zeny_project_handler.application.human_review import (
    ResumoProjetoRevisao,
    ServicoRevisaoHumana,
    SessaoRevisao,
)
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    ExecucaoConformidade,
    FatoConformidade,
    FonteNormativa,
    ResultadoConformidade,
    SeveridadeConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import CaixaPagina, GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 12, 18, tzinfo=UTC)


class _ViewerStub(QObject):
    compliance_callout_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.callouts: tuple[CalloutConformidade, ...] = ()
        self.page_visits: list[int] = []
        self.selected_callouts: list[str] = []
        self.overlays: list[tuple[tuple[PontoNormalizado, ...], ...]] = []

    def definir_callouts_conformidade(
        self,
        callouts: tuple[CalloutConformidade, ...],
    ) -> None:
        self.callouts = callouts

    def ir_para_folha(self, number: int) -> None:
        self.page_visits.append(number)

    def selecionar_callout(self, callout_id: str) -> None:
        self.selected_callouts.append(callout_id)

    def definir_sobreposicoes(
        self,
        geometries: tuple[tuple[PontoNormalizado, ...], ...],
    ) -> None:
        self.overlays.append(geometries)


class _ReviewServiceStub:
    def __init__(self, sessions: tuple[SessaoRevisao, ...]) -> None:
        self._sessions = {item.projeto.id: item for item in sessions}

    def listar_projetos_semanticos(self) -> tuple[ResumoProjetoRevisao, ...]:
        return tuple(
            ResumoProjetoRevisao(
                projeto_id=session.projeto.id,
                nome=session.projeto.nome,
                propostas_pendentes=0,
            )
            for session in self._sessions.values()
        )

    def carregar_sessao_semantica(self, project_id: UUID) -> SessaoRevisao:
        return self._sessions[project_id]


class _AnalysisServiceStub:
    def __init__(self, executions: tuple[ExecucaoConformidade, ...]) -> None:
        self.latest = {item.projeto_id: item for item in executions}

    def obter_ultima(self, project_id: UUID) -> ExecucaoConformidade | None:
        return self.latest.get(project_id)

    def executar(self, project_id: UUID) -> ExecucaoConformidade:
        return self.latest[project_id]


def test_finding_eyes_batch_actions_sorting_and_missing_geometry_are_independent(
    qtbot: QtBot,
) -> None:
    panel, viewer, first_session, _second_session, first_execution, _analysis = _panel(qtbot)
    panel.abrir_projeto(first_session.projeto.id)
    tree = panel.findChild(QTreeWidget, "complianceFindingsTree")
    show_all = panel.findChild(QPushButton, "complianceShowAllCalloutsButton")
    hide_all = panel.findChild(QPushButton, "complianceHideAllCalloutsButton")
    assert tree is not None and show_all is not None and hide_all is not None
    localized_ids = {item.id for item in panel._callouts}
    assert len(localized_ids) == 2
    assert {item.id for item in viewer.callouts} == localized_ids

    localized_rows = tuple(_finding_row(tree, item.id) for item in panel._callouts)
    localized_buttons = tuple(_visibility_button(tree, row) for row in localized_rows)
    assert all(button.isEnabled() and button.isChecked() for button in localized_buttons)
    assert all(button.toolTip() == "Ocultar este achado no PDF" for button in localized_buttons)
    assert all(button.accessibleName() == button.toolTip() for button in localized_buttons)

    unlocated = next(item for item in first_execution.achados if item.id not in localized_ids)
    unlocated_row = _finding_row(tree, unlocated.id)
    unlocated_button = _visibility_button(tree, unlocated_row)
    assert unlocated_row.text(8) == "Sem localização no PDF"
    assert not unlocated_button.isEnabled()
    assert not unlocated_button.isChecked()
    assert unlocated_button.toolTip().startswith("Sem localização no PDF:")
    assert unlocated_button.accessibleName() == unlocated_button.toolTip()

    first_id, second_id = (item.id for item in panel._callouts)
    localized_buttons[0].click()
    assert {item.id for item in viewer.callouts} == {second_id}
    assert not localized_buttons[0].isChecked()
    assert localized_buttons[1].isChecked()

    tree.setSortingEnabled(True)
    tree.sortItems(2, Qt.SortOrder.DescendingOrder)
    panel._populate_findings()
    hidden_button = _visibility_button(tree, _finding_row(tree, first_id))
    assert not hidden_button.isChecked()
    assert {item.id for item in viewer.callouts} == {second_id}

    overlay_state = tuple(viewer.overlays)
    hide_all.click()
    assert viewer.callouts == ()
    assert all(
        not _visibility_button(tree, _finding_row(tree, finding_id)).isChecked()
        for finding_id in localized_ids
    )
    assert tuple(viewer.overlays) == overlay_state

    show_all.click()
    visible_callouts: tuple[CalloutConformidade, ...] = viewer.callouts
    assert {item.id for item in visible_callouts} == localized_ids
    assert first_id != second_id
    assert tuple(viewer.overlays) == overlay_state


def test_hidden_state_survives_navigation_and_resets_for_project_or_execution(
    qtbot: QtBot,
) -> None:
    panel, viewer, first_session, second_session, first_execution, analysis = _panel(qtbot)
    panel.abrir_projeto(first_session.projeto.id)
    hidden_id = panel._callouts[0].id
    panel._set_finding_visible(hidden_id, False)

    viewer.ir_para_folha(2)
    panel._load_persisted_result()
    assert hidden_id in panel._hidden_finding_ids
    assert hidden_id not in {item.id for item in viewer.callouts}

    panel.abrir_projeto(second_session.projeto.id)
    assert panel._hidden_finding_ids == set()
    panel.abrir_projeto(first_session.projeto.id)
    assert hidden_id not in panel._hidden_finding_ids
    assert hidden_id in {item.id for item in viewer.callouts}

    panel._set_finding_visible(hidden_id, False)
    analysis.latest[first_session.projeto.id] = replace(
        first_execution,
        id=_id("execution-project-a-new"),
    )
    panel._load_persisted_result()
    assert panel._hidden_finding_ids == set()
    assert hidden_id in {item.id for item in viewer.callouts}


def test_list_and_callout_selection_sync_without_signal_cycles(qtbot: QtBot) -> None:
    panel, viewer, first_session, _second_session, _execution, _analysis = _panel(qtbot)
    panel.abrir_projeto(first_session.projeto.id)
    tree = panel.findChild(QTreeWidget, "complianceFindingsTree")
    tabs = panel.findChild(QTabWidget, "documentationTabs")
    assert tree is not None and tabs is not None
    first_id, second_id = (item.id for item in panel._callouts)

    tree.setCurrentItem(_finding_row(tree, first_id))
    assert viewer.page_visits == [1]
    assert viewer.selected_callouts == [str(first_id)]

    page_visits = tuple(viewer.page_visits)
    selections = tuple(viewer.selected_callouts)
    tabs.setCurrentIndex(2)
    viewer.compliance_callout_selected.emit(str(second_id))
    assert tree.currentItem() is _finding_row(tree, second_id)
    assert tabs.currentIndex() == 1
    assert tuple(viewer.page_visits) == page_visits
    assert tuple(viewer.selected_callouts) == selections

    panel._set_finding_visible(second_id, False)
    tree.setCurrentItem(_finding_row(tree, first_id))
    tree.setCurrentItem(_finding_row(tree, second_id))
    assert second_id in panel._hidden_finding_ids
    assert second_id not in {item.id for item in viewer.callouts}


def _panel(
    qtbot: QtBot,
) -> tuple[
    DocumentationPanelWidget,
    _ViewerStub,
    SessaoRevisao,
    SessaoRevisao,
    ExecucaoConformidade,
    _AnalysisServiceStub,
]:
    registry = carregar_registro_conformidade_inicial()
    first_session, first_execution = _session_and_execution("project-a", registry.assinatura())
    second_session, second_execution = _session_and_execution("project-b", registry.assinatura())
    review = _ReviewServiceStub((first_session, second_session))
    analysis = _AnalysisServiceStub((first_execution, second_execution))
    viewer = _ViewerStub()
    panel = DocumentationPanelWidget(
        service=cast(ServicoRevisaoHumana, review),
        analysis_service=cast(ExecutarAnaliseConformidade, analysis),
        registry=registry,
        viewer=cast(PdfViewerWidget, viewer),
    )
    qtbot.addWidget(panel)
    panel.show()
    return panel, viewer, first_session, second_session, first_execution, analysis


def _session_and_execution(
    key: str,
    registry_signature: str,
) -> tuple[SessaoRevisao, ExecucaoConformidade]:
    catalog = carregar_catalogo_inicial()
    page = _page(key)
    document = DocumentoProjeto(
        id=_id(f"document-{key}"),
        nome_arquivo=f"{key}.pdf",
        sha256=("a" if key == "project-a" else "b") * 64,
        paginas=(page,),
        tamanho_bytes=100,
    )
    project = Projeto(
        id=_id(key),
        nome=key,
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
    )
    targets: list[AlvoConformidade] = []
    facts: list[FatoConformidade] = []
    findings: list[AchadoConformidade] = []
    for index, point in enumerate(("0.25", "0.65", None)):
        target_id = _id(f"{key}-target-{index}")
        geometry = (
            GeometriaDocumento.ponto(
                page.id,
                PontoNormalizado(Decimal(point), Decimal("0.50")),
            )
            if point is not None
            else None
        )
        targets.append(
            AlvoConformidade(
                id=target_id,
                tipo=TipoEscopoConformidade.REGIAO,
                rotulo=f"Alvo {index}",
                pagina_id=page.id if geometry is not None else None,
                geometria=geometry,
            )
        )
        fact_id = _id(f"{key}-fact-{index}")
        facts.append(
            FatoConformidade(
                id=fact_id,
                alvo_id=target_id,
                chave="fixture.valor",
                valor=f"observado-{index}",
                origem="fixture sintética",
                geometria=geometry,
            )
        )
        findings.append(
            AchadoConformidade(
                id=_id(f"{key}-finding-{index}"),
                regra_id=f"fixture.regra-{index}",
                alvo_id=target_id,
                resultado=ResultadoConformidade.DIVERGENCIA,
                severidade=SeveridadeConformidade.ERRO,
                titulo=f"Divergência {index}",
                mensagem="Valor observado não atende ao requisito sintético.",
                fonte=FonteNormativa(
                    documento="Norma sintética",
                    revisao="1",
                    item="1.1",
                ),
                versao_regras="fixture-1",
                fato_ids=(fact_id,),
            )
        )
    execution = ExecucaoConformidade(
        id=_id(f"execution-{key}"),
        projeto_id=project.id,
        execucoes_semanticas_ids=(_id(f"semantic-{key}"),),
        revisao_regras_id=_id(f"revision-{key}"),
        registro_regras_id=_id(f"registry-{key}"),
        versao_regras="fixture-1",
        assinatura_regras=registry_signature,
        assinatura_sessao=("c" if key == "project-a" else "d") * 64,
        versao_metodo="1",
        executada_em=_NOW,
        alvos=tuple(targets),
        fatos=tuple(facts),
        achados=tuple(findings),
        itens_documentais=(),
    )
    session = SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(),
        propostas=(),
        regioes=(),
        evidencias=(),
        decisoes=(),
        fontes_pdf=(),
    )
    return session, execution


def _page(key: str) -> PaginaDocumento:
    width = Decimal("595")
    height = Decimal("842")
    box = CaixaPagina(Decimal(0), Decimal(0), width, height)
    return PaginaDocumento(
        id=_id(f"page-{key}"),
        numero=1,
        largura_pontos=width,
        altura_pontos=height,
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )


def _finding_row(tree: QTreeWidget, finding_id: UUID) -> QTreeWidgetItem:
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None and str(item.data(0, Qt.ItemDataRole.UserRole + 3)) == str(finding_id):
            return item
    raise AssertionError(f"Achado ausente da árvore: {finding_id}")


def _visibility_button(tree: QTreeWidget, row: QTreeWidgetItem) -> QToolButton:
    button = tree.itemWidget(row, 9)
    assert isinstance(button, QToolButton)
    assert button.objectName() == "complianceFindingVisibilityButton"
    assert button.property("findingId") == row.data(0, Qt.ItemDataRole.UserRole + 3)
    return button


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"compliance-visibility:{value}")
