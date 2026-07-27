"""Painel Qt para transformar propostas revisáveis em dados confirmados."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from functools import partial
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.application.human_review import (
    DadosElementoRevisao,
    ServicoRevisaoHumana,
    SessaoRevisao,
)
from zeny_project_handler.application.spans import VaoDetectado, detectar_vaos
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoEquipamento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.project import (
    Cabo,
    ElementoProjetoType,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    Poste,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .pdf_viewer import PdfViewerWidget

T = TypeVar("T")


class ReviewPanelWidget(QWidget):
    status_changed = Signal(str)
    session_changed = Signal(object)

    def __init__(
        self,
        *,
        service: ServicoRevisaoHumana,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("analysisResultsPanel")
        self._service = service
        self._viewer = viewer
        self._session: SessaoRevisao | None = None
        self._page_id: UUID | None = None
        self._selected_proposal_id: UUID | None = None
        self._spans: tuple[VaoDetectado, ...] = ()
        self._hidden_region_ids: set[UUID] = set()
        self._hidden_proposal_ids: set[UUID] = set()
        self._hidden_span_ids: set[UUID] = set()
        self._visibility_buttons: dict[tuple[str, UUID], QToolButton] = {}
        self._span_visibility_buttons: dict[UUID, QToolButton] = {}
        self._loaded_bounds: tuple[float, float, float, float] | None = None
        self._syncing_selection = False
        self._build_ui()
        self._connect_viewer()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        project_row = QHBoxLayout()
        self._project = QComboBox()
        self._project.setObjectName("reviewProjectCombo")
        project_row.addWidget(self._project, 1)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("reviewRefreshButton")
        refresh.clicked.connect(self.atualizar_projetos)
        project_row.addWidget(refresh)
        layout.addLayout(project_row)

        filter_widget = QWidget()
        filter_row = QHBoxLayout(filter_widget)
        filter_row.setContentsMargins(0, 0, 0, 0)
        self._category_filter = QComboBox()
        self._category_filter.setObjectName("reviewCategoryFilter")
        self._category_filter.addItem("Todas as classes", None)
        for category in CategoriaElemento:
            self._category_filter.addItem(category.value, category.value)
        filter_row.addWidget(self._category_filter)
        self._state_filter = QComboBox()
        self._state_filter.setObjectName("reviewStateFilter")
        self._state_filter.addItem("Todos os estados", None)
        for state in EstadoRevisao:
            self._state_filter.addItem(state.value, state.value)
        filter_row.addWidget(self._state_filter)

        self._results_tabs = QTabWidget()
        self._results_tabs.setObjectName("analysisResultTabs")
        elements_page = QWidget()
        elements_layout = QVBoxLayout(elements_page)
        elements_layout.setContentsMargins(0, 0, 0, 0)
        elements_layout.addWidget(filter_widget)

        guidance = QLabel(
            "As identificações são incorporadas automaticamente ao projeto. "
            "Expanda cada região para ver a coordenada e tudo o que acontece naquele ponto; "
            "clique em qualquer elemento para localizá-lo no PDF."
        )
        guidance.setObjectName("analysisResultsGuidance")
        guidance.setWordWrap(True)
        elements_layout.addWidget(guidance)

        self._tree = QTreeWidget()
        self._tree.setObjectName("analysisRelationshipTree")
        self._tree.setHeaderLabels(
            (
                "Ponto / elemento",
                "Ação",
                "Coordenada",
                "Catálogo",
                "Vínculos",
                "Exibir",
            )
        )
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = self._tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(80)
        for column, width in enumerate((190, 105, 185, 260, 260, 70)):
            header.resizeSection(column, width)
        header.setStretchLastSection(False)
        elements_layout.addWidget(self._tree, 1)

        self._table = QTableWidget(0, 4)
        self._table.setObjectName("reviewProposalTable")
        self._table.setHorizontalHeaderLabels(("Tipo", "Classe/relação", "Estado", "Confiança"))
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.hide()
        elements_layout.addWidget(self._table)
        self._results_tabs.addTab(elements_page, "Elementos")

        spans_page = QWidget()
        spans_layout = QVBoxLayout(spans_page)
        spans_layout.setContentsMargins(0, 0, 0, 0)
        spans_guidance = QLabel(
            "Um vão é exibido quando o desenho permite associar as duas extremidades "
            "de um cabo a postes distintos. O comprimento prioriza a anotação do desenho "
            "e, na ausência dela, a distância entre coordenadas."
        )
        spans_guidance.setObjectName("spanResultsGuidance")
        spans_guidance.setWordWrap(True)
        spans_layout.addWidget(spans_guidance)
        self._span_table = QTableWidget(0, 9)
        self._span_table.setObjectName("analysisSpanTable")
        self._span_table.setHorizontalHeaderLabels(
            (
                "Vão",
                "Situação",
                "Poste de origem",
                "Poste de destino",
                "Cabo",
                "Comprimento",
                "Fonte",
                "Folha",
                "Exibir",
            )
        )
        self._span_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._span_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._span_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._span_table.verticalHeader().setVisible(False)
        span_header = self._span_table.horizontalHeader()
        span_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        span_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        span_header.setStretchLastSection(False)
        spans_layout.addWidget(self._span_table, 1)
        self._results_tabs.addTab(spans_page, "Vãos")
        layout.addWidget(self._results_tabs, 1)

        editor = QGroupBox("Correção excepcional")
        editor.setObjectName("reviewDecisionEditor")
        self._editor_form = QFormLayout(editor)
        form = self._editor_form
        self._detected = QLabel("Selecione uma identificação na lista ou no PDF")
        self._detected.setObjectName("reviewDetectedSummary")
        self._detected.setWordWrap(True)
        form.addRow("Identificado", self._detected)
        self._reviewer = QLineEdit()
        self._reviewer.setObjectName("reviewAuthorEdit")
        self._reviewer.setPlaceholderText("Nome de quem está revisando")
        form.addRow("Responsável", self._reviewer)
        self._reason = QLineEdit()
        self._reason.setObjectName("reviewReasonEdit")
        self._reason.setPlaceholderText("Opcional")
        form.addRow("Observação", self._reason)
        self._classification_correction = QCheckBox("Corrigir classe ou item do catálogo")
        self._classification_correction.setObjectName("reviewCorrectClassificationCheck")
        form.addRow(self._classification_correction)
        self._category = QComboBox()
        self._category.setObjectName("reviewCategoryCombo")
        for category in CategoriaElemento:
            self._category.addItem(category.value, category.value)
        form.addRow("Classe corrigida", self._category)
        self._catalog_item = QComboBox()
        self._catalog_item.setObjectName("reviewCatalogItemCombo")
        form.addRow("Item corrigido", self._catalog_item)
        self._situation = QComboBox()
        self._situation.setObjectName("reviewSituationCombo")
        for situation in SituacaoProjeto:
            self._situation.addItem(situation.value, situation.value)
        form.addRow("Situação da obra", self._situation)
        self._pole = QComboBox()
        self._pole.setObjectName("reviewPoleCombo")
        form.addRow("Poste associado", self._pole)
        self._origin_point = QComboBox()
        self._origin_point.setObjectName("reviewOriginPointCombo")
        form.addRow("Origem do cabo", self._origin_point)
        self._destination_point = QComboBox()
        self._destination_point.setObjectName("reviewDestinationPointCombo")
        form.addRow("Destino do cabo", self._destination_point)
        self._adjust_geometry = QCheckBox("Ajustar posição numericamente")
        self._adjust_geometry.setObjectName("reviewAdjustGeometryCheck")
        form.addRow(self._adjust_geometry)
        self._geometry_widget = QWidget(editor)
        geometry_row = QHBoxLayout(self._geometry_widget)
        geometry_row.setContentsMargins(0, 0, 0, 0)
        self._x = _coordinate_spin("reviewXSpin")
        self._y = _coordinate_spin("reviewYSpin")
        self._width = _coordinate_spin("reviewWidthSpin")
        self._height = _coordinate_spin("reviewHeightSpin")
        for label, field in (
            ("X", self._x),
            ("Y", self._y),
            ("L", self._width),
            ("A", self._height),
        ):
            geometry_row.addWidget(QLabel(label))
            geometry_row.addWidget(field)
        form.addRow("Posição na folha (0 a 1)", self._geometry_widget)
        editor.hide()
        layout.addWidget(editor)

        decision_row = QHBoxLayout()
        self._accept = QPushButton("Confirmar identificação")
        self._accept.setObjectName("reviewAcceptButton")
        self._accept.clicked.connect(self.aceitar_selecionada)
        self._accept.hide()
        decision_row.addWidget(self._accept)
        self._reject = QPushButton("Não é este elemento")
        self._reject.setObjectName("reviewRejectButton")
        self._reject.clicked.connect(self.rejeitar_selecionada)
        self._reject.hide()
        decision_row.addWidget(self._reject)
        layout.addLayout(decision_row)

        manual_row = QHBoxLayout()
        manual_element = QPushButton("Criar elemento manual")
        manual_element.setObjectName("reviewCreateElementButton")
        manual_element.clicked.connect(self.criar_elemento_manual)
        manual_element.hide()
        manual_row.addWidget(manual_element)
        self._relation_type = QLineEdit("RELACIONADO_A")
        self._relation_type.setObjectName("reviewRelationTypeEdit")
        self._relation_type.hide()
        manual_row.addWidget(self._relation_type)
        manual_relation = QPushButton("Criar relação manual")
        manual_relation.setObjectName("reviewCreateRelationButton")
        manual_relation.clicked.connect(self.criar_relacao_manual)
        manual_relation.hide()
        manual_row.addWidget(manual_relation)
        layout.addLayout(manual_row)

        self._reference_origin = QComboBox()
        self._reference_origin.setObjectName("reviewRelationOriginCombo")
        self._reference_origin.hide()
        self._reference_destination = QComboBox()
        self._reference_destination.setObjectName("reviewRelationDestinationCombo")
        self._reference_destination.hide()
        reference_row = QHBoxLayout()
        reference_row.addWidget(self._reference_origin)
        reference_row.addWidget(self._reference_destination)
        layout.addLayout(reference_row)

        self._project.currentIndexChanged.connect(self._load_selected_project)
        self._category_filter.currentIndexChanged.connect(self._refresh_proposals)
        self._state_filter.currentIndexChanged.connect(self._refresh_proposals)
        self._tree.itemSelectionChanged.connect(self._select_tree_proposal)
        self._table.itemSelectionChanged.connect(self._select_table_proposal)
        self._span_table.itemSelectionChanged.connect(self._select_span)
        self._category.currentIndexChanged.connect(self._refresh_catalog_items)
        self._category.currentIndexChanged.connect(self._editor_mode_changed)
        self._classification_correction.toggled.connect(self._editor_mode_changed)
        self._adjust_geometry.toggled.connect(self._editor_mode_changed)
        self._update_editor_visibility(None)

    def _connect_viewer(self) -> None:
        self._viewer.page_changed.connect(self._page_changed)
        self._viewer.proposal_selected.connect(self._select_proposal_id)

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto analisado", None)
        for summary in self._service.listar_projetos():
            self._project.addItem(
                f"{summary.nome} (resultados disponíveis)",
                str(summary.projeto_id),
            )
        if selected is not None:
            index = self._project.findData(selected)
            self._project.setCurrentIndex(max(0, index))
        self._project.blockSignals(False)
        if self._project.currentData() is not None:
            self._load_selected_project()

    def limpar(self) -> None:
        self._session = None
        self._page_id = None
        self._selected_proposal_id = None
        self._spans = ()
        self._hidden_region_ids.clear()
        self._hidden_proposal_ids.clear()
        self._hidden_span_ids.clear()
        self._visibility_buttons.clear()
        self._span_visibility_buttons.clear()
        self._project.clear()
        self._project.addItem("Selecione um projeto analisado", None)
        self._tree.clear()
        self._table.setRowCount(0)
        self._span_table.setRowCount(0)
        self._viewer.definir_propostas_revisao(())
        self.session_changed.emit(None)

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is None:
            return
        project_id = UUID(value)
        self._run_action(lambda: self._activate_session(self._service.carregar_sessao(project_id)))

    def abrir_projeto(self, projeto_id: UUID) -> None:
        """Sincronize o painel com um projeto concluído pelo fluxo operacional."""
        self.atualizar_projetos()
        project_index = self._project.findData(str(projeto_id))
        if project_index < 0:
            self.status_changed.emit("Projeto ainda não possui resultados de análise")
            return
        self._project.blockSignals(True)
        self._project.setCurrentIndex(project_index)
        self._project.blockSignals(False)
        self._run_action(lambda: self._activate_session(self._service.carregar_sessao(projeto_id)))

    def _activate_session(self, session: SessaoRevisao) -> None:
        self._session = session
        self._hidden_region_ids.clear()
        self._hidden_proposal_ids.clear()
        self._hidden_span_ids.clear()
        self._visibility_buttons.clear()
        self._span_visibility_buttons.clear()
        source_paths = tuple(source.caminho_canonico for source in session.fontes_pdf)
        if source_paths and not self._viewer.carregar_projeto(
            source_paths,
            documentos=session.projeto.documentos,
            ordem_paginas=session.projeto.ordem_leitura_paginas,
        ):
            raise ApplicationError("Não foi possível abrir todos os PDFs do projeto")
        if not source_paths:
            self.status_changed.emit(
                "Projeto sem referências locais de PDF; resultados estruturados disponíveis"
            )
        self._refresh_references()
        self._refresh_catalog_items()
        self._refresh_proposals()
        self._refresh_spans()
        self.session_changed.emit(session)

    def _page_changed(self, page_id: str) -> None:
        self._page_id = UUID(page_id)
        self._refresh_proposals()

    def _refresh_proposals(self) -> None:
        session = self._session
        if session is None:
            return
        category = self._category_filter.currentData()
        state = self._state_filter.currentData()
        filtered = self._filtered_proposals(category=category, state=state)
        if self._selected_proposal_id is not None and all(
            item.id != self._selected_proposal_id for item in filtered
        ):
            self._selected_proposal_id = None
            self._detected.setText("Selecione uma identificação na lista ou no PDF")
            self._update_editor_visibility(None)
        self._populate_result_tree(filtered)
        self._table.setRowCount(0)
        for proposal in filtered:
            row = self._table.rowCount()
            self._table.insertRow(row)
            kind = "Elemento" if isinstance(proposal, PropostaElemento) else "Relação"
            values = (
                kind,
                _proposal_category(proposal),
                proposal.estado_revisao.value,
                str(proposal.confianca) if proposal.confianca is not None else "-",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(proposal.id))
                self._table.setItem(row, column, cell)
        self._update_review_overlays(filtered)

    def _refresh_spans(self) -> None:
        session = self._session
        self._spans = detectar_vaos(session.projeto) if session is not None else ()
        self._span_table.setRowCount(0)
        self._span_visibility_buttons.clear()
        if session is None:
            return
        elements = {item.id: item for item in session.projeto.elementos}
        for index, span in enumerate(self._spans, start=1):
            row = self._span_table.rowCount()
            self._span_table.insertRow(row)
            origin = (
                elements.get(span.poste_origem_id) if span.poste_origem_id is not None else None
            )
            destination = (
                elements.get(span.poste_destino_id) if span.poste_destino_id is not None else None
            )
            cable = elements.get(span.cabo_id)
            page_number = (
                self._project_page_number(span.geometria.pagina_id)
                if span.geometria is not None
                else None
            )
            span_label = (
                cable.identificador_operacional
                if isinstance(cable, Cabo) and cable.identificador_operacional
                else f"Vão {index}"
            )
            values = (
                span_label,
                _situation_label(span.situacao),
                _project_element_label(origin),
                _project_element_label(destination),
                _project_element_label(cable, catalog=session.catalogo),
                _span_length_label(span.comprimento_m),
                _span_length_source_label(span.origem_comprimento),
                f"Folha {page_number}" if page_number is not None else "-",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(span.id))
                self._span_table.setItem(row, column, cell)
            visible, enabled = self._span_visibility_state(span)
            span_button = self._visibility_button(
                visible=visible,
                object_name="analysisSpanVisibilityButton",
                tooltip=("Ocultar este vão no PDF" if visible else "Exibir este vão no PDF"),
                toggled=partial(self._set_span_visible, span.id),
                parent=self._span_table,
            )
            span_button.setEnabled(enabled)
            span_button.setProperty("spanId", str(span.id))
            span_button.setProperty("cableId", str(span.cabo_id))
            if (proposal_id := self._span_proposal_id(span)) is not None:
                span_button.setProperty("proposalId", str(proposal_id))
            self._span_visibility_buttons[span.id] = span_button
            self._span_table.setCellWidget(row, 8, span_button)

    def _select_span(self) -> None:
        selected = self._span_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        identity_cell = self._span_table.item(row, 0)
        if identity_cell is None:
            return
        span_id = identity_cell.data(Qt.ItemDataRole.UserRole)
        span = next((item for item in self._spans if str(item.id) == span_id), None)
        session = self._session
        if span is None or session is None:
            return
        if span.geometria is not None:
            page_number = self._project_page_number(span.geometria.pagina_id)
            if page_number is not None:
                self._viewer.ir_para_folha(page_number)
        decision = next(
            (item for item in session.decisoes if item.elemento_confirmado_id == span.cabo_id),
            None,
        )
        if decision is not None:
            self._select_proposal_id(str(decision.proposta_id))

    def _filtered_proposals(
        self,
        *,
        category: object,
        state: object,
    ) -> tuple[PropostaElemento | PropostaRelacao, ...]:
        session = self._session
        if session is None:
            return ()
        return tuple(
            item
            for item in session.propostas
            if (category is None or _proposal_category(item) == category)
            and (state is None or item.estado_revisao.value == state)
        )

    def _update_review_overlays(
        self,
        filtered: tuple[PropostaElemento | PropostaRelacao, ...] | None = None,
    ) -> None:
        session = self._session
        if session is None:
            self._viewer.definir_propostas_revisao(())
            return
        proposals = filtered or self._filtered_proposals(
            category=self._category_filter.currentData(),
            state=self._state_filter.currentData(),
        )
        hidden_by_region = {
            element_id
            for region in session.regioes
            if region.id in self._hidden_region_ids
            for element_id in region.elemento_ids
        }
        overlays = tuple(
            item
            for item in proposals
            if isinstance(item, PropostaElemento)
            and item.id not in self._hidden_proposal_ids
            and item.id not in hidden_by_region
            and (self._page_id is None or item.geometria.pagina_id == self._page_id)
        )
        self._viewer.definir_propostas_revisao(
            overlays,
            geometrias_links=_link_geometries(overlays, session.evidencias),
        )

    def _visibility_button(
        self,
        *,
        visible: bool,
        object_name: str,
        tooltip: str,
        toggled: Callable[[bool], None],
        parent: QWidget | None = None,
    ) -> QToolButton:
        button = QToolButton(parent or self._tree)
        button.setObjectName(object_name)
        button.setCheckable(True)
        button.setChecked(visible)
        button.setIcon(_visibility_icon(visible))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.toggled.connect(toggled)
        return button

    def _set_region_visible(self, region_id: UUID, visible: bool) -> None:
        if visible:
            self._hidden_region_ids.discard(region_id)
        else:
            self._hidden_region_ids.add(region_id)
            self._viewer.definir_sobreposicoes(())
        self._sync_visibility_buttons()
        self._update_review_overlays()

    def _set_element_visible(self, proposal_id: UUID, visible: bool) -> None:
        if visible:
            self._hidden_proposal_ids.discard(proposal_id)
        else:
            self._hidden_proposal_ids.add(proposal_id)
        self._sync_visibility_buttons()
        self._update_review_overlays()

    def _set_span_visible(self, span_id: UUID, visible: bool) -> None:
        span = next((item for item in self._spans if item.id == span_id), None)
        if span is None:
            return
        proposal_id = self._span_proposal_id(span)
        if proposal_id is None:
            if visible:
                self._hidden_span_ids.discard(span_id)
            else:
                self._hidden_span_ids.add(span_id)
        elif visible:
            self._hidden_proposal_ids.discard(proposal_id)
            self._hidden_span_ids.discard(span_id)
        else:
            self._hidden_proposal_ids.add(proposal_id)
        self._sync_visibility_buttons()
        self._update_review_overlays()

    def _sync_visibility_buttons(self) -> None:
        session = self._session
        if session is None:
            return
        region_by_element = {
            element_id: region for region in session.regioes for element_id in region.elemento_ids
        }
        for (kind, reference_id), button in self._visibility_buttons.items():
            if kind == "region":
                visible = reference_id not in self._hidden_region_ids
                enabled = True
                tooltip = (
                    "Ocultar o ponto inteiro no PDF" if visible else "Exibir o ponto inteiro no PDF"
                )
            else:
                region = region_by_element.get(reference_id)
                enabled = region is None or region.id not in self._hidden_region_ids
                visible = enabled and reference_id not in self._hidden_proposal_ids
                tooltip = (
                    "Ocultar somente este elemento no PDF"
                    if visible
                    else "Exibir somente este elemento no PDF"
                )
            button.blockSignals(True)
            button.setEnabled(enabled)
            button.setChecked(visible)
            button.setIcon(_visibility_icon(visible))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.blockSignals(False)
        self._sync_span_visibility_buttons()

    def _sync_span_visibility_buttons(self) -> None:
        for span_id, button in self._span_visibility_buttons.items():
            span = next((item for item in self._spans if item.id == span_id), None)
            if span is None:
                continue
            visible, enabled = self._span_visibility_state(span)
            tooltip = "Ocultar este vão no PDF" if visible else "Exibir este vão no PDF"
            button.blockSignals(True)
            button.setEnabled(enabled)
            button.setChecked(visible)
            button.setIcon(_visibility_icon(visible))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.blockSignals(False)

    def _span_visibility_state(self, span: VaoDetectado) -> tuple[bool, bool]:
        proposal_id = self._span_proposal_id(span)
        if proposal_id is None:
            return span.id not in self._hidden_span_ids, True
        session = self._session
        region = (
            next(
                (item for item in session.regioes if proposal_id in item.elemento_ids),
                None,
            )
            if session is not None
            else None
        )
        enabled = region is None or region.id not in self._hidden_region_ids
        visible = enabled and proposal_id not in self._hidden_proposal_ids
        return visible, enabled

    def _span_proposal_id(self, span: VaoDetectado) -> UUID | None:
        session = self._session
        if session is None:
            return None
        decision = next(
            (item for item in session.decisoes if item.elemento_confirmado_id == span.cabo_id),
            None,
        )
        return decision.proposta_id if decision is not None else None

    def _populate_result_tree(
        self,
        proposals: tuple[PropostaElemento | PropostaRelacao, ...],
    ) -> None:
        session = self._session
        if session is None:
            return
        self._tree.clear()
        self._visibility_buttons.clear()
        visible_elements = {
            item.id: item for item in proposals if isinstance(item, PropostaElemento)
        }
        all_elements = {
            item.id: item for item in session.propostas if isinstance(item, PropostaElemento)
        }
        all_relations = {
            item.id: item for item in session.propostas if isinstance(item, PropostaRelacao)
        }
        for region_number, region in enumerate(session.regioes, start=1):
            elements = tuple(
                visible_elements[element_id]
                for element_id in region.elemento_ids
                if element_id in visible_elements
            )
            if not elements and region.elemento_ids:
                continue
            action_summary = _region_action_counts(elements) or "Ponto identificado"
            detail_summary = _region_summary(elements, catalog=session.catalogo) or (
                "Identificador de ponto reconhecido no PDF"
            )
            root = QTreeWidgetItem(
                (
                    self._region_label(region, region_number),
                    action_summary,
                    _coordinate_label(region),
                    f"{len(elements)} elemento(s)",
                    f"{len(region.vinculo_ids)} vínculo(s)",
                    "",
                )
            )
            root.setData(0, Qt.ItemDataRole.UserRole + 1, str(region.id))
            root.setToolTip(0, self._region_location(region, region_number))
            root.setToolTip(1, detail_summary)
            self._tree.addTopLevelItem(root)
            region_visible = region.id not in self._hidden_region_ids
            region_button = self._visibility_button(
                visible=region_visible,
                object_name="analysisRegionVisibilityButton",
                tooltip=(
                    "Ocultar o ponto inteiro no PDF"
                    if region_visible
                    else "Exibir o ponto inteiro no PDF"
                ),
                toggled=partial(self._set_region_visible, region.id),
            )
            region_button.setProperty("regionId", str(region.id))
            self._visibility_buttons[("region", region.id)] = region_button
            self._tree.setItemWidget(root, 5, region_button)
            for element in elements:
                child = self._result_item(
                    element,
                    relationships=_relationship_labels(
                        element,
                        region,
                        all_elements,
                        all_relations,
                        catalog=session.catalogo,
                    ),
                )
                root.addChild(child)
                element_visible = region_visible and element.id not in self._hidden_proposal_ids
                element_button = self._visibility_button(
                    visible=element_visible,
                    object_name="analysisElementVisibilityButton",
                    tooltip=(
                        "Ocultar somente este elemento no PDF"
                        if element_visible
                        else "Exibir somente este elemento no PDF"
                    ),
                    toggled=partial(self._set_element_visible, element.id),
                )
                element_button.setEnabled(region_visible)
                element_button.setProperty("proposalId", str(element.id))
                self._visibility_buttons[("element", element.id)] = element_button
                self._tree.setItemWidget(child, 5, element_button)
        if not visible_elements:
            self._tree.addTopLevelItem(
                QTreeWidgetItem(("Nenhuma identificação neste filtro", "", "", "", "", ""))
            )
        self._tree.expandAll()

    def _result_item(
        self,
        proposal: PropostaElemento,
        *,
        relationships: tuple[str, ...] = (),
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            (
                _proposal_label(
                    proposal,
                    catalog=self._session.catalogo if self._session is not None else None,
                ),
                _situation_label(proposal.situacao_projeto),
                "",
                self._catalog_label(proposal),
                "; ".join(relationships) or "Agrupado por proximidade",
                "",
            )
        )
        item.setData(0, Qt.ItemDataRole.UserRole, str(proposal.id))
        return item

    def _region_label(self, region: RegiaoAnalise, number: int) -> str:
        return region.rotulo_ponto or f"Ponto {number}"

    def _region_location(self, region: RegiaoAnalise, number: int) -> str:
        session = self._session
        if session is None:
            return self._region_label(region, number)
        for document in session.projeto.documentos:
            for page in document.paginas:
                if page.id == region.pagina_id:
                    return (
                        f"{self._region_label(region, number)} · "
                        f"{document.nome_arquivo} · página {page.numero}"
                    )
        return self._region_label(region, number)

    def _catalog_label(self, proposal: PropostaElemento) -> str:
        session = self._session
        catalog_item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if session is not None and proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if catalog_item is None:
            return "Não catalogado"
        return f"{catalog_item.codigo} — {catalog_item.descricao}"

    def _select_tree_proposal(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        proposal_id = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if proposal_id:
            self._select_proposal_id(str(proposal_id))
            return
        region_id = selected[0].data(0, Qt.ItemDataRole.UserRole + 1)
        if region_id:
            self._select_region_id(str(region_id))

    def _select_region_id(self, region_id: str) -> None:
        session = self._session
        if session is None:
            return
        region = next((item for item in session.regioes if str(item.id) == region_id), None)
        if region is None:
            return
        page_number = self._project_page_number(region.pagina_id)
        if page_number is not None:
            self._viewer.ir_para_folha(page_number)
        self._viewer.definir_sobreposicoes(
            () if region.id in self._hidden_region_ids else (region.geometria.pontos,)
        )
        self._detected.setText(
            f"{self._region_location(region, session.regioes.index(region) + 1)} · "
            f"{_coordinate_label(region)}"
        )

    def _select_table_proposal(self) -> None:
        selected = self._table.selectedItems()
        if not selected:
            return
        proposal_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if proposal_id:
            self._select_proposal_id(str(proposal_id))

    def _select_proposal_id(self, proposal_id: str) -> None:
        session = self._session
        if session is None or self._syncing_selection:
            return
        proposal = next((item for item in session.propostas if str(item.id) == proposal_id), None)
        if proposal is None:
            return
        self._syncing_selection = True
        try:
            self._selected_proposal_id = proposal.id
            if isinstance(proposal, PropostaElemento):
                page_number = self._project_page_number(proposal.geometria.pagina_id)
                if page_number is not None:
                    self._viewer.ir_para_folha(page_number)
            self._select_tree_item(proposal_id)
            self._select_table_row(proposal_id)
            self._viewer.selecionar_proposta(proposal_id)
            self._classification_correction.blockSignals(True)
            self._classification_correction.setChecked(False)
            self._classification_correction.blockSignals(False)
            self._adjust_geometry.blockSignals(True)
            self._adjust_geometry.setChecked(False)
            self._adjust_geometry.blockSignals(False)
            if isinstance(proposal, PropostaElemento):
                self._set_combo_value(self._category, proposal.categoria.value)
                self._refresh_catalog_items()
                if proposal.tipo_catalogo_sugerido_id is not None:
                    self._set_combo_value(
                        self._catalog_item, str(proposal.tipo_catalogo_sugerido_id)
                    )
                else:
                    self._classification_correction.setChecked(True)
                self._set_combo_value(self._situation, proposal.situacao_projeto.value)
                self._set_geometry_fields(proposal.geometria)
                self._detected.setText(self._element_detection_summary(proposal))
            else:
                self._detected.setText(f"Relação proposta: {proposal.tipo_relacao}")
            self._update_editor_visibility(proposal)
        finally:
            self._syncing_selection = False

    def _project_page_number(self, page_id: UUID) -> int | None:
        session = self._session
        if session is None:
            return None
        try:
            return session.projeto.ordem_leitura_paginas.index(page_id) + 1
        except ValueError:
            return None

    def _select_tree_item(self, proposal_id: str) -> None:
        pending = [self._tree.invisibleRootItem()]
        while pending:
            parent = pending.pop()
            for index in range(parent.childCount()):
                child = parent.child(index)
                if str(child.data(0, Qt.ItemDataRole.UserRole)) == proposal_id:
                    self._tree.blockSignals(True)
                    self._tree.setCurrentItem(child)
                    self._tree.scrollToItem(child)
                    self._tree.blockSignals(False)
                    return
                pending.append(child)

    def _select_table_row(self, proposal_id: str) -> None:
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, 0)
            if cell is None or str(cell.data(Qt.ItemDataRole.UserRole)) != proposal_id:
                continue
            self._table.blockSignals(True)
            self._table.selectRow(row)
            self._table.scrollToItem(cell)
            self._table.blockSignals(False)
            return

    def _element_detection_summary(self, proposal: PropostaElemento) -> str:
        session = self._session
        item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if session is not None and proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if item is None:
            return f"{proposal.categoria.value} · item do catálogo não identificado"
        return f"{proposal.categoria.value} · {item.codigo} — {item.descricao}"

    def _editor_mode_changed(self, *_args: object) -> None:
        self._update_editor_visibility(self._selected_proposal())

    def _update_editor_visibility(
        self,
        proposal: PropostaElemento | PropostaRelacao | None,
    ) -> None:
        is_element = isinstance(proposal, PropostaElemento)
        decidable = proposal is not None and proposal.estado_revisao in {
            EstadoRevisao.PROPOSTA,
            EstadoRevisao.CONFLITANTE,
        }
        editable_element = is_element and decidable
        correcting = editable_element and self._classification_correction.isChecked()
        category = (
            CategoriaElemento(self._category.currentData())
            if is_element and self._category.currentData() is not None
            else None
        )
        self._classification_correction.setVisible(editable_element)
        self._editor_form.setRowVisible(self._category, correcting)
        self._editor_form.setRowVisible(self._catalog_item, correcting)
        self._editor_form.setRowVisible(self._situation, editable_element)
        self._editor_form.setRowVisible(
            self._pole,
            editable_element
            and category
            in {
                CategoriaElemento.ESTRUTURA_MT,
                CategoriaElemento.ESTRUTURA_BT,
                CategoriaElemento.EQUIPAMENTO,
            },
        )
        is_cable = editable_element and category is CategoriaElemento.CABO
        self._editor_form.setRowVisible(self._origin_point, is_cable)
        self._editor_form.setRowVisible(self._destination_point, is_cable)
        self._adjust_geometry.setVisible(editable_element)
        self._editor_form.setRowVisible(
            self._geometry_widget,
            editable_element and self._adjust_geometry.isChecked(),
        )
        self._accept.setEnabled(decidable)
        self._reject.setEnabled(decidable)
        if proposal is not None and not decidable:
            self._accept.setText("Decisão já registrada")
        elif isinstance(proposal, PropostaRelacao):
            self._accept.setText("Confirmar relação")
        elif correcting or (is_element and self._adjust_geometry.isChecked()):
            self._accept.setText("Salvar correções")
        else:
            self._accept.setText("Confirmar identificação")

    def _set_geometry_fields(self, geometry: GeometriaDocumento) -> None:
        left, top, width, height = _bounds(geometry)
        self._loaded_bounds = (left, top, width, height)
        for field, value in (
            (self._x, left),
            (self._y, top),
            (self._width, width),
            (self._height, height),
        ):
            field.setValue(value)

    def _refresh_catalog_items(self) -> None:
        session = self._session
        if session is None:
            return
        category = CategoriaElemento(self._category.currentData())
        selected = self._catalog_item.currentData()
        self._catalog_item.clear()
        for item in session.catalogo.itens_ativos(category):
            self._catalog_item.addItem(f"{item.codigo} — {item.descricao}", str(item.id))
        if selected is not None:
            self._set_combo_value(self._catalog_item, selected)

    def _refresh_references(self) -> None:
        session = self._session
        if session is None:
            return
        self._pole.clear()
        self._pole.addItem("Selecione", None)
        for element in session.projeto.elementos:
            if isinstance(element, Poste):
                self._pole.addItem(
                    element.identificador_operacional or str(element.id), str(element.id)
                )
        for combo in (self._origin_point, self._destination_point):
            combo.clear()
            combo.addItem("Selecione", None)
            for point in session.projeto.pontos_rede:
                combo.addItem(point.nome, str(point.id))
        references = [
            *[(item.id, _element_label(item)) for item in session.projeto.elementos],
            *[(item.id, item.nome) for item in session.projeto.pontos_rede],
            *[(item.id, item.nome) for item in session.projeto.terminais],
        ]
        for combo in (self._reference_origin, self._reference_destination):
            combo.clear()
            combo.addItem("Selecione", None)
            for reference_id, label in references:
                combo.addItem(label, str(reference_id))

    def aceitar_selecionada(self) -> None:
        proposal = self._selected_proposal()
        if proposal is None:
            return
        if isinstance(proposal, PropostaRelacao):
            result = self._run_action(
                lambda: self._service.confirmar_relacao(
                    proposal.id,
                    revisor=self._reviewer.text(),
                    motivo=self._reason.text() or None,
                )
            )
        else:
            result = self._run_action(
                lambda: self._service.confirmar_elemento(
                    proposal.id,
                    self._element_data(proposal),
                    revisor=self._reviewer.text(),
                    motivo=self._reason.text() or None,
                )
            )
        if result is not None:
            self._reload_session()

    def rejeitar_selecionada(self) -> None:
        proposal = self._selected_proposal()
        if proposal is None:
            return
        result = self._run_action(
            lambda: self._service.rejeitar(
                proposal.id,
                revisor=self._reviewer.text(),
                motivo=self._reason.text() or None,
            )
        )
        if result:
            self._reload_session()

    def criar_elemento_manual(self) -> None:
        session = self._session
        if session is None or self._page_id is None:
            return
        geometry = GeometriaDocumento.ponto(
            self._page_id,
            PontoNormalizado(Decimal(str(self._x.value())), Decimal(str(self._y.value()))),
        )
        data = self._element_data(None, default_geometry=geometry)
        result = self._run_action(
            lambda: self._service.criar_elemento_manual(
                session.projeto.id,
                data,
                revisor=self._reviewer.text(),
                motivo=self._reason.text() or None,
            )
        )
        if result:
            self._reload_session()

    def criar_relacao_manual(self) -> None:
        session = self._session
        origin = self._reference_origin.currentData()
        destination = self._reference_destination.currentData()
        if session is None or origin is None or destination is None:
            return
        result = self._run_action(
            lambda: self._service.criar_relacao_manual(
                session.projeto.id,
                tipo_relacao=self._relation_type.text(),
                origem_id=UUID(origin),
                destino_id=UUID(destination),
                revisor=self._reviewer.text(),
                motivo=self._reason.text() or None,
            )
        )
        if result:
            self._reload_session()

    def _element_data(
        self,
        proposal: PropostaElemento | None,
        *,
        default_geometry: GeometriaDocumento | None = None,
    ) -> DadosElementoRevisao:
        category = CategoriaElemento(self._category.currentData())
        catalog_item = self._catalog_item.currentData()
        if catalog_item is None:
            raise ApplicationError("Selecione um item do catálogo")
        geometry = default_geometry
        if proposal is not None:
            geometry = self._viewer.geometria_proposta(str(proposal.id)) or proposal.geometria
            current_bounds = (
                self._x.value(),
                self._y.value(),
                self._width.value(),
                self._height.value(),
            )
            if self._loaded_bounds is None or any(
                abs(current - loaded) > 0.000001
                for current, loaded in zip(current_bounds, self._loaded_bounds, strict=True)
            ):
                geometry = _resize_geometry(geometry, *current_bounds)
        if geometry is None:
            raise ApplicationError("Defina a geometria do elemento")
        return DadosElementoRevisao(
            categoria=category,
            tipo_catalogo_id=UUID(catalog_item),
            situacao=SituacaoProjeto(self._situation.currentData()),
            geometria=geometry,
            codigo_observado=(proposal.codigo_observado if proposal is not None else None),
            poste_id=_optional_uuid(self._pole.currentData()),
            ponto_origem_id=_optional_uuid(self._origin_point.currentData()),
            ponto_destino_id=_optional_uuid(self._destination_point.currentData()),
        )

    def _selected_proposal(self) -> PropostaElemento | PropostaRelacao | None:
        session = self._session
        if session is None or self._selected_proposal_id is None:
            return None
        return next(
            (item for item in session.propostas if item.id == self._selected_proposal_id),
            None,
        )

    def _reload_session(self) -> None:
        session = self._session
        if session is None:
            return
        selected = self._selected_proposal_id
        self._activate_session(self._service.carregar_sessao(session.projeto.id))
        if selected is not None:
            self._select_proposal_id(str(selected))

    def _run_action(self, action: Callable[[], T]) -> T | None:
        try:
            result = action()
        except (ApplicationError, DomainValidationError, ValueError) as error:
            QMessageBox.warning(self, "Revisão não concluída", str(error))
            self.status_changed.emit(str(error))
            return None
        self.status_changed.emit("Revisão salva")
        return result

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)


def _visibility_icon(visible: bool) -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#2f5f8f"), 1.8)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(2.0, 5.0, 16.0, 10.0))
    painter.setBrush(QColor("#2f5f8f"))
    painter.drawEllipse(QRectF(8.0, 8.0, 4.0, 4.0))
    if not visible:
        slash = QPen(QColor("#a33a3a"), 2.2)
        slash.setCosmetic(True)
        painter.setPen(slash)
        painter.drawLine(3, 3, 17, 17)
    painter.end()
    return QIcon(pixmap)


def _coordinate_spin(name: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setObjectName(name)
    spin.setRange(0, 1)
    spin.setDecimals(6)
    spin.setSingleStep(0.001)
    return spin


def _proposal_category(proposal: PropostaElemento | PropostaRelacao) -> str:
    return (
        proposal.categoria.value
        if isinstance(proposal, PropostaElemento)
        else proposal.tipo_relacao
    )


def _proposal_label(
    proposal: PropostaElemento,
    *,
    catalog: CatalogoTecnico | None = None,
) -> str:
    if proposal.categoria is CategoriaElemento.EQUIPAMENTO:
        category = _equipment_type_label(proposal, catalog)
        if dict(proposal.atributos_sugeridos).get("reconhecido_por_simbologia") is True:
            return category
        return f"{category} {proposal.codigo_observado or ''}".strip()
    category = {
        CategoriaElemento.POSTE: "Poste",
        CategoriaElemento.ESTRUTURA_MT: "Estrutura MT",
        CategoriaElemento.ESTRUTURA_BT: "Estrutura BT",
        CategoriaElemento.CABO: "Cabo",
    }[proposal.categoria]
    return f"{category} {proposal.codigo_observado or ''}".strip()


def _equipment_type_label(
    proposal: PropostaElemento,
    catalog: CatalogoTecnico | None,
) -> str:
    if catalog is not None and proposal.tipo_catalogo_sugerido_id is not None:
        catalog_item = catalog.item_por_id(proposal.tipo_catalogo_sugerido_id)
        if isinstance(catalog_item, TipoEquipamento):
            option_label = next(
                (
                    option.rotulo
                    for group in catalog.grupos_opcao
                    if group.chave == "classe_equipamento"
                    for option in group.opcoes
                    if option.id == catalog_item.classe_equipamento_opcao_id
                ),
                None,
            )
            if option_label is not None:
                return option_label.capitalize()
    suggested_class = dict(proposal.atributos_sugeridos).get("classe_equipamento")
    if isinstance(suggested_class, str) and suggested_class.strip():
        symbolic_labels = {
            "ATERRAMENTO": "Aterramento",
            "PARA_RAIOS_BT": "Para-raios BT",
            "PARA_RAIOS_MT": "Para-raios MT",
        }
        if suggested_class.strip().upper() in symbolic_labels:
            return symbolic_labels[suggested_class.strip().upper()]
        return suggested_class.replace("_", " ").strip().capitalize()
    return "Equipamento"


def _link_geometries(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> dict[UUID, GeometriaDocumento]:
    evidence_by_id = {item.id: item for item in evidence}
    geometries: dict[UUID, GeometriaDocumento] = {}
    for proposal in proposals:
        if proposal.categoria is not CategoriaElemento.CABO:
            continue
        label = _cable_label_evidence(proposal, evidence_by_id)
        if label is not None:
            geometries[proposal.id] = label.geometria
    return geometries


def _cable_label_evidence(
    proposal: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
) -> EvidenciaDocumento | None:
    attributes = dict(proposal.atributos_sugeridos)
    explicit_id = _safe_uuid(attributes.get("evidencia_rotulo_id"))
    if explicit_id is not None:
        explicit = evidence_by_id.get(explicit_id)
        if (
            explicit is not None
            and explicit.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
            and explicit.pagina_id == proposal.geometria.pagina_id
        ):
            return explicit

    excluded_ids = {
        identifier
        for key in ("evidencia_identificador_id", "evidencia_comprimento_id")
        if (identifier := _safe_uuid(attributes.get(key))) is not None
    }
    candidates = tuple(
        item
        for evidence_id in proposal.evidencia_ids
        if evidence_id not in excluded_ids
        if (item := evidence_by_id.get(evidence_id)) is not None
        and item.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
        and item.pagina_id == proposal.geometria.pagina_id
    )
    if not candidates:
        return None
    observed = (proposal.codigo_observado or "").casefold()
    return min(
        candidates,
        key=lambda item: (
            0 if observed and observed in (item.conteudo_bruto or "").casefold() else 1,
            str(item.id),
        ),
    )


def _safe_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _situation_label(situation: SituacaoProjeto) -> str:
    return {
        SituacaoProjeto.INSTALAR: "A instalar",
        SituacaoProjeto.REMOVER: "A remover",
        SituacaoProjeto.EXISTENTE: "Existente",
    }[situation]


def _coordinate_label(region: RegiaoAnalise) -> str:
    if region.coordenada is None:
        return "Sem coordenada identificada"
    return f"E {region.coordenada.leste:.0f} · N {region.coordenada.norte:.0f}"


def _region_summary(
    elements: tuple[PropostaElemento, ...],
    *,
    catalog: CatalogoTecnico | None = None,
) -> str:
    parts: list[str] = []
    for situation, verb in (
        (SituacaoProjeto.REMOVER, "Remover"),
        (SituacaoProjeto.INSTALAR, "Instalar"),
        (SituacaoProjeto.EXISTENTE, "Existente"),
    ):
        labels = tuple(
            _proposal_label(element, catalog=catalog)
            for element in elements
            if element.situacao_projeto is situation
        )
        if labels:
            parts.append(f"{verb}: {', '.join(labels)}")
    return " · ".join(parts)


def _region_action_counts(elements: tuple[PropostaElemento, ...]) -> str:
    parts: list[str] = []
    for situation, singular, plural in (
        (SituacaoProjeto.REMOVER, "remover", "remover"),
        (SituacaoProjeto.INSTALAR, "instalar", "instalar"),
        (SituacaoProjeto.EXISTENTE, "existente", "existentes"),
    ):
        count = sum(element.situacao_projeto is situation for element in elements)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    return " · ".join(parts)


def _relationship_labels(
    element: PropostaElemento,
    region: RegiaoAnalise,
    elements: dict[UUID, PropostaElemento],
    relations: dict[UUID, PropostaRelacao],
    *,
    catalog: CatalogoTecnico | None = None,
) -> tuple[str, ...]:
    labels: list[str] = []
    for relation_id in region.vinculo_ids:
        relation = relations.get(relation_id)
        if relation is None:
            continue
        if relation.origem_referencia_id == element.id:
            related_id = relation.destino_referencia_id
            direction = "→"
        elif relation.destino_referencia_id == element.id:
            related_id = relation.origem_referencia_id
            direction = "←"
        else:
            continue
        related = elements.get(related_id)
        if related is None:
            continue
        relation_label = relation.tipo_relacao.replace("_", " ").lower()
        labels.append(f"{relation_label} {direction} {_proposal_label(related, catalog=catalog)}")
    return tuple(labels)


def _bounds(geometry: GeometriaDocumento) -> tuple[float, float, float, float]:
    x_values = [float(point.x) for point in geometry.pontos]
    y_values = [float(point.y) for point in geometry.pontos]
    left, right = min(x_values), max(x_values)
    top, bottom = min(y_values), max(y_values)
    return left, top, right - left, bottom - top


def _resize_geometry(
    geometry: GeometriaDocumento,
    left: float,
    top: float,
    width: float,
    height: float,
) -> GeometriaDocumento:
    old_left, old_top, old_width, old_height = _bounds(geometry)
    if geometry.tipo is TipoGeometria.PONTO:
        points: tuple[PontoNormalizado, ...] = (
            PontoNormalizado(Decimal(str(left)), Decimal(str(top))),
        )
    else:
        points = tuple(
            PontoNormalizado(
                Decimal(str(left + _scaled(float(point.x), old_left, old_width, width))),
                Decimal(str(top + _scaled(float(point.y), old_top, old_height, height))),
            )
            for point in geometry.pontos
        )
    return GeometriaDocumento(pagina_id=geometry.pagina_id, tipo=geometry.tipo, pontos=points)


def _scaled(value: float, origin: float, old_size: float, new_size: float) -> float:
    return (value - origin) if old_size == 0 else (value - origin) * new_size / old_size


def _optional_uuid(value: object) -> UUID | None:
    return UUID(str(value)) if value is not None else None


def _element_label(element: object) -> str:
    if isinstance(element, (Poste, EstruturaMt, EstruturaBt, Cabo, Equipamento)):
        return f"{element.categoria.value}: {element.codigo_observado or element.id}"
    return str(element)


def _project_element_label(
    element: ElementoProjetoType | None,
    *,
    catalog: CatalogoTecnico | None = None,
) -> str:
    if element is None:
        return "-"
    if isinstance(element, Poste):
        reference = (
            element.identificador_operacional
            or element.referencia_desenho
            or element.codigo_observado
        )
        coordinate = element.coordenada_campo
        if coordinate is not None:
            coordinate_label = f"E {coordinate.leste:f} · N {coordinate.norte:f}"
            return f"{reference} · {coordinate_label}" if reference else coordinate_label
        return f"{reference} · {str(element.id)[:8]}" if reference else str(element.id)
    if isinstance(element, Cabo) and catalog is not None:
        item = catalog.item_por_id(element.tipo_catalogo_id)
        if item is not None:
            return f"{item.codigo} — {item.descricao}"
    return element.codigo_observado or element.identificador_operacional or str(element.id)


def _span_length_label(length: Decimal | None) -> str:
    if length is None:
        return "Não identificado"
    return f"{length.quantize(Decimal('0.01')):f} m".replace(".", ",")


def _span_length_source_label(source: OrigemComprimentoVao | None) -> str:
    if source is None:
        return "-"
    return {
        OrigemComprimentoVao.ANOTACAO_DESENHO: "Anotação do desenho",
        OrigemComprimentoVao.COORDENADAS: "Distância entre coordenadas",
        OrigemComprimentoVao.INFORMADO: "Comprimento informado",
    }[source]
