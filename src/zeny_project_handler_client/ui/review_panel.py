"""Painel Qt cliente de Resultados alimentado exclusivamente por DTOs da API."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import Qt, Signal
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

from zeny_project_handler_contracts.base import CatalogItemId, ElementId, PageId
from zeny_project_handler_contracts.common import NormalizedPointDto
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewReferenceKind,
    ReviewState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.review import (
    AcceptReviewProposalRequest,
    CreateManualElementRequest,
    CreateManualRelationRequest,
    DetectedSpanDto,
    RejectReviewProposalRequest,
    ReviewElementInputDto,
    ReviewGeometryDto,
    ReviewProposalDto,
    ReviewRelationDto,
    ReviewSessionResponse,
)

from .pdf_viewer import PdfViewerWidget
from .review_gateway import ReviewGateway, ReviewGatewayError
from .table_word_wrap import TableWordWrapController
from .visibility import visibility_icon

T = TypeVar("T")
ReviewItem = ReviewProposalDto | ReviewRelationDto


class ReviewPanelWidget(QWidget):
    status_changed = Signal(str)
    session_changed = Signal(object)

    def __init__(
        self,
        *,
        gateway: ReviewGateway,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("analysisResultsPanel")
        self._gateway = gateway
        self._viewer = viewer
        self._session: ReviewSessionResponse | None = None
        self._page_id: UUID | None = None
        self._selected_proposal_id: UUID | None = None
        self._spans: tuple[DetectedSpanDto, ...] = ()
        self._hidden_region_ids: set[UUID] = set()
        self._hidden_proposal_ids: set[UUID] = set()
        self._hidden_span_ids: set[UUID] = set()
        self._visibility_buttons: dict[tuple[str, UUID], QToolButton] = {}
        self._span_visibility_buttons: dict[UUID, QToolButton] = {}
        self._loaded_bounds: tuple[float, float, float, float] | None = None
        self._syncing_selection = False
        self._build_ui()
        self._connect_viewer()
        self.atualizar_projetos(show_warning=False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
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
        for category in ElementCategory:
            self._category_filter.addItem(_category_label(category), category.value)
        filter_row.addWidget(self._category_filter)
        self._state_filter = QComboBox()
        self._state_filter.setObjectName("reviewStateFilter")
        self._state_filter.addItem("Todos os estados", None)
        for state in ReviewState:
            self._state_filter.addItem(_state_label(state), state.value)
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
        guidance.setProperty("role", "hint")
        guidance.setWordWrap(True)
        elements_layout.addWidget(guidance)

        self._tree = QTreeWidget()
        self._tree.setObjectName("analysisRelationshipTree")
        self._tree.setHeaderLabels(
            ("Ponto / elemento", "Ação", "Coordenada", "Catálogo", "Vínculos", "Exibir")
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
        self._elements_word_wrap = TableWordWrapController(
            self._tree,
            button_name="analysisElementsWordWrapButton",
        )
        filter_row.addStretch(1)
        filter_row.addWidget(self._elements_word_wrap.button)
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
        spans_guidance.setProperty("role", "hint")
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
        self._spans_word_wrap = TableWordWrapController(
            self._span_table,
            button_name="analysisSpansWordWrapButton",
        )
        span_actions = QHBoxLayout()
        span_actions.addStretch(1)
        span_actions.addWidget(self._spans_word_wrap.button)
        spans_layout.addLayout(span_actions)
        spans_layout.addWidget(self._span_table, 1)
        self._results_tabs.addTab(spans_page, "Vãos")
        layout.addWidget(self._results_tabs, 1)

        editor = QGroupBox("Revisar identificação")
        editor.setObjectName("reviewDecisionEditor")
        self._editor_form = QFormLayout(editor)
        self._detected = QLabel("Selecione uma identificação na lista ou no PDF")
        self._detected.setObjectName("reviewDetectedSummary")
        self._detected.setWordWrap(True)
        self._editor_form.addRow("Identificado", self._detected)
        self._reviewer = QLineEdit()
        self._reviewer.setObjectName("reviewAuthorEdit")
        self._reviewer.setPlaceholderText("Nome de quem está revisando")
        self._editor_form.addRow("Responsável", self._reviewer)
        self._reason = QLineEdit()
        self._reason.setObjectName("reviewReasonEdit")
        self._reason.setPlaceholderText("Opcional")
        self._editor_form.addRow("Observação", self._reason)
        self._classification_correction = QCheckBox("Corrigir classe ou item do catálogo")
        self._classification_correction.setObjectName("reviewCorrectClassificationCheck")
        self._editor_form.addRow(self._classification_correction)
        self._category = QComboBox()
        self._category.setObjectName("reviewCategoryCombo")
        for category in ElementCategory:
            self._category.addItem(_category_label(category), category.value)
        self._editor_form.addRow("Classe corrigida", self._category)
        self._catalog_item = QComboBox()
        self._catalog_item.setObjectName("reviewCatalogItemCombo")
        self._editor_form.addRow("Item corrigido", self._catalog_item)
        self._situation = QComboBox()
        self._situation.setObjectName("reviewSituationCombo")
        for situation in ElementSituation:
            self._situation.addItem(_situation_label(situation), situation.value)
        self._editor_form.addRow("Situação da obra", self._situation)
        self._pole = QComboBox()
        self._pole.setObjectName("reviewPoleCombo")
        self._editor_form.addRow("Poste associado", self._pole)
        self._origin_point = QComboBox()
        self._origin_point.setObjectName("reviewOriginPointCombo")
        self._editor_form.addRow("Origem do cabo", self._origin_point)
        self._destination_point = QComboBox()
        self._destination_point.setObjectName("reviewDestinationPointCombo")
        self._editor_form.addRow("Destino do cabo", self._destination_point)
        self._adjust_geometry = QCheckBox("Ajustar posição numericamente")
        self._adjust_geometry.setObjectName("reviewAdjustGeometryCheck")
        self._editor_form.addRow(self._adjust_geometry)
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
        self._editor_form.addRow("Posição na folha (0 a 1)", self._geometry_widget)
        editor.hide()
        layout.addWidget(editor)

        decision_row = QHBoxLayout()
        self._accept = QPushButton("Confirmar identificação")
        self._accept.setObjectName("reviewAcceptButton")
        self._accept.setProperty("role", "primary")
        self._accept.clicked.connect(self.aceitar_selecionada)
        self._accept.hide()
        decision_row.addWidget(self._accept)
        self._reject = QPushButton("Não é este elemento")
        self._reject.setObjectName("reviewRejectButton")
        self._reject.setProperty("role", "danger")
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
        self._results_tabs.currentChanged.connect(self._refresh_visible_word_wrap)
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

    def atualizar_projetos(
        self,
        _checked: bool = False,
        *,
        show_warning: bool = True,
    ) -> None:
        selected = self._project.currentData()

        def update() -> None:
            response = self._gateway.list_projects()
            self._project.blockSignals(True)
            self._project.clear()
            self._project.addItem("Selecione um projeto analisado", None)
            for summary in response.items:
                self._project.addItem(
                    f"{summary.service_note} (resultados disponíveis)",
                    str(summary.project_id.root),
                )
            if selected is not None:
                self._project.setCurrentIndex(max(0, self._project.findData(selected)))
            self._project.blockSignals(False)
            if self._project.currentData() is not None:
                self._load_selected_project()

        self._run_action(update, success_message=None, show_warning=show_warning)

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
        self._elements_word_wrap.refresh()
        self._spans_word_wrap.refresh()
        self._viewer.definir_propostas_revisao(())
        self.session_changed.emit(None)

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is not None:
            self._run_action(
                lambda: self._activate_session(self._gateway.get_session(UUID(str(value)))),
                success_message=None,
            )

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        project_index = self._project.findData(str(projeto_id))
        if project_index < 0:
            self.status_changed.emit("Projeto ainda não possui resultados de análise")
            return
        self._project.blockSignals(True)
        self._project.setCurrentIndex(project_index)
        self._project.blockSignals(False)
        self._run_action(
            lambda: self._activate_session(self._gateway.get_session(projeto_id)),
            success_message=None,
        )

    def _activate_session(self, session: ReviewSessionResponse) -> None:
        self._session = session
        self._hidden_region_ids.clear()
        self._hidden_proposal_ids.clear()
        self._hidden_span_ids.clear()
        self._visibility_buttons.clear()
        self._span_visibility_buttons.clear()
        if not self._viewer.carregar_projeto_remoto(session.project_id.root):
            raise ReviewGatewayError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Não foi possível abrir os PDFs gerenciados do projeto.",
            )
        self._refresh_references()
        self._refresh_catalog_items()
        self._refresh_proposals()
        self._refresh_spans()
        self.session_changed.emit(session)

    def _page_changed(self, page_id: str) -> None:
        self._page_id = UUID(page_id)
        self._refresh_proposals()

    def _all_items(self) -> tuple[ReviewItem, ...]:
        session = self._session
        return (*session.proposals, *session.relations) if session is not None else ()

    def _filtered_items(self, *, category: object, state: object) -> tuple[ReviewItem, ...]:
        return tuple(
            item
            for item in self._all_items()
            if (category is None or _proposal_category(item) == category)
            and (state is None or item.review_state.value == state)
        )

    def _refresh_proposals(self) -> None:
        session = self._session
        if session is None:
            return
        filtered = self._filtered_items(
            category=self._category_filter.currentData(),
            state=self._state_filter.currentData(),
        )
        if self._selected_proposal_id is not None and all(
            _proposal_id(item) != self._selected_proposal_id for item in filtered
        ):
            self._selected_proposal_id = None
            self._detected.setText("Selecione uma identificação na lista ou no PDF")
            self._update_editor_visibility(None)
        elements = tuple(item for item in filtered if isinstance(item, ReviewProposalDto))
        self._populate_result_tree(elements)
        self._table.setRowCount(0)
        for item in filtered:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = (
                "Elemento" if isinstance(item, ReviewProposalDto) else "Relação",
                _proposal_category(item),
                item.state_label,
                item.confidence or "-",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(_proposal_id(item)))
                self._table.setItem(row, column, cell)
        self._update_review_overlays(elements)
        self._elements_word_wrap.refresh()

    def _refresh_spans(self) -> None:
        session = self._session
        self._spans = session.spans if session is not None else ()
        self._span_table.setRowCount(0)
        self._span_visibility_buttons.clear()
        for span in self._spans:
            row = self._span_table.rowCount()
            self._span_table.insertRow(row)
            values = (
                span.label,
                span.situation_label,
                span.start_label,
                span.end_label,
                span.cable_label,
                span.length_label,
                span.length_source_label,
                span.page_label,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(span.span_id))
                self._span_table.setItem(row, column, cell)
            visible, enabled = self._span_visibility_state(span)
            button = self._visibility_button(
                visible=visible,
                object_name="analysisSpanVisibilityButton",
                tooltip="Ocultar este vão no PDF" if visible else "Exibir este vão no PDF",
                toggled=partial(self._set_span_visible, span.span_id),
                parent=self._span_table,
            )
            button.setEnabled(enabled)
            button.setProperty("spanId", str(span.span_id))
            button.setProperty("cableId", str(span.cable_element_id.root))
            if span.proposal_id is not None:
                button.setProperty("proposalId", str(span.proposal_id.root))
            self._span_visibility_buttons[span.span_id] = button
            self._span_table.setCellWidget(row, 8, button)
        self._spans_word_wrap.refresh()

    def _refresh_visible_word_wrap(self, index: int) -> None:
        controllers = (self._elements_word_wrap, self._spans_word_wrap)
        if 0 <= index < len(controllers):
            controllers[index].refresh()

    def _select_span(self) -> None:
        selected = self._span_table.selectedItems()
        if not selected:
            return
        identity = self._span_table.item(selected[0].row(), 0)
        if identity is None:
            return
        span = next(
            (
                item
                for item in self._spans
                if str(item.span_id) == identity.data(Qt.ItemDataRole.UserRole)
            ),
            None,
        )
        if span is None:
            return
        if span.geometry is not None:
            page_number = self._project_page_number(span.geometry.page_id.root)
            if page_number is not None:
                self._viewer.ir_para_folha(page_number)
        if span.proposal_id is not None:
            self._select_proposal_id(str(span.proposal_id.root))

    def _update_review_overlays(
        self,
        filtered: tuple[ReviewProposalDto, ...] | None = None,
    ) -> None:
        session = self._session
        if session is None:
            self._viewer.definir_propostas_revisao(())
            return
        proposals = filtered or tuple(
            item
            for item in self._filtered_items(
                category=self._category_filter.currentData(),
                state=self._state_filter.currentData(),
            )
            if isinstance(item, ReviewProposalDto)
        )
        hidden_by_region = {
            proposal_id.root
            for region in session.regions
            if region.region_id.root in self._hidden_region_ids
            for proposal_id in region.proposal_ids
        }
        overlays = tuple(
            item.overlay
            for item in proposals
            if item.proposal_id.root not in self._hidden_proposal_ids
            and item.proposal_id.root not in hidden_by_region
            and (self._page_id is None or item.overlay.geometry.page_id.root == self._page_id)
        )
        self._viewer.definir_propostas_revisao(overlays)

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
        button.setIcon(visibility_icon(visible))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.toggled.connect(toggled)
        return button

    def _set_region_visible(self, region_id: UUID, visible: bool) -> None:
        if visible:
            self._hidden_region_ids.discard(region_id)
        else:
            self._hidden_region_ids.add(region_id)
            self._viewer.definir_sobreposicoes_revisao(())
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
        span = next((item for item in self._spans if item.span_id == span_id), None)
        if span is None:
            return
        proposal_id = span.proposal_id.root if span.proposal_id is not None else None
        if proposal_id is None:
            (self._hidden_span_ids.discard if visible else self._hidden_span_ids.add)(span_id)
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
        region_by_proposal = {
            proposal_id.root: region
            for region in session.regions
            for proposal_id in region.proposal_ids
        }
        for (kind, reference_id), button in self._visibility_buttons.items():
            if kind == "region":
                visible = reference_id not in self._hidden_region_ids
                enabled = True
                tooltip = (
                    "Ocultar o ponto inteiro no PDF" if visible else "Exibir o ponto inteiro no PDF"
                )
            else:
                region = region_by_proposal.get(reference_id)
                enabled = region is None or region.region_id.root not in self._hidden_region_ids
                visible = enabled and reference_id not in self._hidden_proposal_ids
                tooltip = (
                    "Ocultar somente este elemento no PDF"
                    if visible
                    else "Exibir somente este elemento no PDF"
                )
            button.blockSignals(True)
            button.setEnabled(enabled)
            button.setChecked(visible)
            button.setIcon(visibility_icon(visible))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.blockSignals(False)
        self._sync_span_visibility_buttons()

    def _sync_span_visibility_buttons(self) -> None:
        for span_id, button in self._span_visibility_buttons.items():
            span = next((item for item in self._spans if item.span_id == span_id), None)
            if span is None:
                continue
            visible, enabled = self._span_visibility_state(span)
            tooltip = "Ocultar este vão no PDF" if visible else "Exibir este vão no PDF"
            button.blockSignals(True)
            button.setEnabled(enabled)
            button.setChecked(visible)
            button.setIcon(visibility_icon(visible))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.blockSignals(False)

    def _span_visibility_state(self, span: DetectedSpanDto) -> tuple[bool, bool]:
        if span.proposal_id is None:
            return span.span_id not in self._hidden_span_ids, True
        proposal_id = span.proposal_id.root
        session = self._session
        region = (
            next(
                (item for item in session.regions if span.proposal_id in item.proposal_ids),
                None,
            )
            if session is not None
            else None
        )
        enabled = region is None or region.region_id.root not in self._hidden_region_ids
        return enabled and proposal_id not in self._hidden_proposal_ids, enabled

    def _populate_result_tree(self, proposals: tuple[ReviewProposalDto, ...]) -> None:
        session = self._session
        if session is None:
            return
        self._tree.clear()
        self._visibility_buttons.clear()
        visible = {item.proposal_id.root: item for item in proposals}
        for region in session.regions:
            elements = tuple(
                visible[item.root] for item in region.proposal_ids if item.root in visible
            )
            if not elements and region.proposal_ids:
                continue
            root = QTreeWidgetItem(
                (
                    region.label,
                    region.action_summary,
                    region.coordinate_label,
                    f"{len(elements)} elemento(s)",
                    f"{len(region.relation_proposal_ids)} vínculo(s)",
                    "",
                )
            )
            root.setData(0, Qt.ItemDataRole.UserRole + 1, str(region.region_id.root))
            root.setToolTip(0, region.location_label)
            root.setToolTip(1, region.detail_summary)
            self._tree.addTopLevelItem(root)
            region_id = region.region_id.root
            region_visible = region_id not in self._hidden_region_ids
            region_button = self._visibility_button(
                visible=region_visible,
                object_name="analysisRegionVisibilityButton",
                tooltip="Ocultar o ponto inteiro no PDF"
                if region_visible
                else "Exibir o ponto inteiro no PDF",
                toggled=partial(self._set_region_visible, region_id),
            )
            region_button.setProperty("regionId", str(region_id))
            self._visibility_buttons[("region", region_id)] = region_button
            self._tree.setItemWidget(root, 5, region_button)
            for proposal in elements:
                child = QTreeWidgetItem(
                    (
                        proposal.label,
                        proposal.situation_label,
                        "",
                        proposal.catalog_label,
                        "; ".join(proposal.relationship_labels) or "Agrupado por proximidade",
                        "",
                    )
                )
                proposal_id = proposal.proposal_id.root
                child.setData(0, Qt.ItemDataRole.UserRole, str(proposal_id))
                root.addChild(child)
                element_visible = region_visible and proposal_id not in self._hidden_proposal_ids
                button = self._visibility_button(
                    visible=element_visible,
                    object_name="analysisElementVisibilityButton",
                    tooltip=(
                        "Ocultar somente este elemento no PDF"
                        if element_visible
                        else "Exibir somente este elemento no PDF"
                    ),
                    toggled=partial(self._set_element_visible, proposal_id),
                )
                button.setEnabled(region_visible)
                button.setProperty("proposalId", str(proposal_id))
                self._visibility_buttons[("element", proposal_id)] = button
                self._tree.setItemWidget(child, 5, button)
        if not visible:
            self._tree.addTopLevelItem(
                QTreeWidgetItem(("Nenhuma identificação neste filtro", "", "", "", "", ""))
            )
        self._tree.expandAll()

    def _select_tree_proposal(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        proposal_id = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if proposal_id:
            self._select_proposal_id(str(proposal_id))
        elif region_id := selected[0].data(0, Qt.ItemDataRole.UserRole + 1):
            self._select_region_id(str(region_id))

    def _select_region_id(self, region_id: str) -> None:
        session = self._session
        if session is None:
            return
        region = next(
            (item for item in session.regions if str(item.region_id.root) == region_id), None
        )
        if region is None:
            return
        page_number = self._project_page_number(region.page_id.root)
        if page_number is not None:
            self._viewer.ir_para_folha(page_number)
        self._viewer.definir_sobreposicoes_revisao(
            () if region.region_id.root in self._hidden_region_ids else (region.geometry,)
        )
        self._detected.setText(f"{region.location_label} · {region.coordinate_label}")

    def _select_table_proposal(self) -> None:
        selected = self._table.selectedItems()
        if selected and (proposal_id := selected[0].data(Qt.ItemDataRole.UserRole)):
            self._select_proposal_id(str(proposal_id))

    def _select_proposal_id(self, proposal_id: str) -> None:
        if self._session is None or self._syncing_selection:
            return
        proposal = next(
            (item for item in self._all_items() if str(_proposal_id(item)) == proposal_id),
            None,
        )
        if proposal is None:
            return
        self._syncing_selection = True
        try:
            self._selected_proposal_id = _proposal_id(proposal)
            if isinstance(proposal, ReviewProposalDto):
                page_number = self._project_page_number(proposal.overlay.geometry.page_id.root)
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
            if isinstance(proposal, ReviewProposalDto):
                self._set_combo_value(self._category, proposal.category.value)
                self._refresh_catalog_items()
                if proposal.catalog_item_id is not None:
                    self._set_combo_value(self._catalog_item, str(proposal.catalog_item_id.root))
                else:
                    self._classification_correction.setChecked(True)
                self._set_combo_value(self._situation, proposal.situation.value)
                self._set_geometry_fields(proposal.overlay.geometry)
                self._detected.setText(proposal.detection_summary)
            else:
                self._detected.setText(proposal.label)
            self._update_editor_visibility(proposal)
        finally:
            self._syncing_selection = False

    def _project_page_number(self, page_id: UUID) -> int | None:
        if self._session is None:
            return None
        try:
            return tuple(item.root for item in self._session.page_order).index(page_id) + 1
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
            if cell is not None and str(cell.data(Qt.ItemDataRole.UserRole)) == proposal_id:
                self._table.blockSignals(True)
                self._table.selectRow(row)
                self._table.scrollToItem(cell)
                self._table.blockSignals(False)
                return

    def _editor_mode_changed(self, *_args: object) -> None:
        self._update_editor_visibility(self._selected_proposal())

    def _update_editor_visibility(self, proposal: ReviewItem | None) -> None:
        is_element = isinstance(proposal, ReviewProposalDto)
        decidable = proposal is not None and proposal.requires_review
        editable = is_element and decidable
        correcting = editable and self._classification_correction.isChecked()
        category = (
            ElementCategory(self._category.currentData())
            if is_element and self._category.currentData() is not None
            else None
        )
        self._classification_correction.setVisible(editable)
        self._editor_form.setRowVisible(self._category, correcting)
        self._editor_form.setRowVisible(self._catalog_item, correcting)
        self._editor_form.setRowVisible(self._situation, editable)
        self._editor_form.setRowVisible(
            self._pole,
            editable
            and category
            in {
                ElementCategory.MV_STRUCTURE,
                ElementCategory.LV_STRUCTURE,
                ElementCategory.EQUIPMENT,
            },
        )
        is_cable = editable and category is ElementCategory.CABLE
        self._editor_form.setRowVisible(self._origin_point, is_cable)
        self._editor_form.setRowVisible(self._destination_point, is_cable)
        self._adjust_geometry.setVisible(editable)
        self._editor_form.setRowVisible(
            self._geometry_widget,
            editable and self._adjust_geometry.isChecked(),
        )
        self._accept.setEnabled(decidable)
        self._reject.setEnabled(decidable)
        if proposal is not None and not decidable:
            self._accept.setText("Decisão já registrada")
        elif isinstance(proposal, ReviewRelationDto):
            self._accept.setText("Confirmar relação")
        elif correcting or (is_element and self._adjust_geometry.isChecked()):
            self._accept.setText("Salvar correções")
        else:
            self._accept.setText("Confirmar identificação")

    def _set_geometry_fields(self, geometry: ReviewGeometryDto) -> None:
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
        if session is None or self._category.currentData() is None:
            return
        category = ElementCategory(self._category.currentData())
        selected = self._catalog_item.currentData()
        self._catalog_item.clear()
        for item in session.catalog_items:
            if item.category is category:
                self._catalog_item.addItem(item.label, str(item.catalog_item_id.root))
        if selected is not None:
            self._set_combo_value(self._catalog_item, selected)

    def _refresh_references(self) -> None:
        session = self._session
        if session is None:
            return
        self._pole.clear()
        self._pole.addItem("Selecione", None)
        for item in session.references:
            if item.kind is ReviewReferenceKind.ELEMENT and item.category is ElementCategory.POLE:
                self._pole.addItem(item.label, str(item.reference_id))
        for combo in (self._origin_point, self._destination_point):
            combo.clear()
            combo.addItem("Selecione", None)
            for item in session.references:
                if item.kind is ReviewReferenceKind.NETWORK_POINT:
                    combo.addItem(item.label, str(item.reference_id))
        for combo in (self._reference_origin, self._reference_destination):
            combo.clear()
            combo.addItem("Selecione", None)
            for item in session.references:
                combo.addItem(item.label, str(item.reference_id))

    def aceitar_selecionada(self) -> None:
        proposal = self._selected_proposal()
        session = self._session
        if proposal is None or session is None:
            return
        request = AcceptReviewProposalRequest(
            author=self._reviewer.text(),
            reason=self._reason.text() or None,
            adjustments=(
                self._element_data(proposal) if isinstance(proposal, ReviewProposalDto) else None
            ),
            expected_review_session_id=session.review_session_id,
        )
        result = self._run_action(lambda: self._gateway.accept(_proposal_id(proposal), request))
        if result is not None:
            self._reload_session()

    def rejeitar_selecionada(self) -> None:
        proposal = self._selected_proposal()
        session = self._session
        if proposal is None or session is None:
            return
        result = self._run_action(
            lambda: self._gateway.reject(
                _proposal_id(proposal),
                RejectReviewProposalRequest(
                    author=self._reviewer.text(),
                    reason=self._reason.text() or "Rejeitada na revisão humana",
                    expected_review_session_id=session.review_session_id,
                ),
            )
        )
        if result is not None:
            self._reload_session()

    def criar_elemento_manual(self) -> None:
        session = self._session
        if session is None or self._page_id is None:
            return
        geometry = ReviewGeometryDto(
            page_id=PageId(self._page_id),
            kind=ReviewGeometryKind.POINT,
            points=(NormalizedPointDto(x=str(self._x.value()), y=str(self._y.value())),),
        )
        result = self._run_action(
            lambda: self._gateway.create_manual_element(
                session.project_id.root,
                CreateManualElementRequest(
                    author=self._reviewer.text(),
                    reason=self._reason.text() or None,
                    element=self._element_data(None, default_geometry=geometry),
                    expected_project_version=session.project_version,
                ),
            )
        )
        if result is not None:
            self._reload_session()

    def criar_relacao_manual(self) -> None:
        session = self._session
        origin = self._reference_origin.currentData()
        destination = self._reference_destination.currentData()
        if session is None or origin is None or destination is None:
            return
        result = self._run_action(
            lambda: self._gateway.create_manual_relation(
                session.project_id.root,
                CreateManualRelationRequest(
                    author=self._reviewer.text(),
                    reason=self._reason.text() or None,
                    relation_type=self._relation_type.text(),
                    source_reference_id=UUID(str(origin)),
                    target_reference_id=UUID(str(destination)),
                    expected_project_version=session.project_version,
                ),
            )
        )
        if result is not None:
            self._reload_session()

    def _element_data(
        self,
        proposal: ReviewProposalDto | None,
        *,
        default_geometry: ReviewGeometryDto | None = None,
    ) -> ReviewElementInputDto:
        catalog_item = self._catalog_item.currentData()
        if catalog_item is None:
            raise ValueError("Selecione um item do catálogo")
        geometry = default_geometry
        if proposal is not None:
            geometry = (
                self._viewer.geometria_proposta(str(proposal.proposal_id.root))
                or proposal.overlay.geometry
            )
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
            raise ValueError("Defina a geometria do elemento")
        return ReviewElementInputDto(
            category=ElementCategory(self._category.currentData()),
            catalog_item_id=CatalogItemId(UUID(str(catalog_item))),
            situation=ElementSituation(self._situation.currentData()),
            geometry=geometry,
            observed_code=proposal.observed_code if proposal is not None else None,
            pole_id=(
                ElementId(UUID(str(self._pole.currentData())))
                if self._pole.currentData() is not None
                else None
            ),
            origin_point_id=_optional_uuid(self._origin_point.currentData()),
            target_point_id=_optional_uuid(self._destination_point.currentData()),
        )

    def _selected_proposal(self) -> ReviewItem | None:
        if self._selected_proposal_id is None:
            return None
        return next(
            (
                item
                for item in self._all_items()
                if _proposal_id(item) == self._selected_proposal_id
            ),
            None,
        )

    def _reload_session(self) -> None:
        session = self._session
        if session is None:
            return
        selected = self._selected_proposal_id
        self._activate_session(self._gateway.get_session(session.project_id.root))
        if selected is not None:
            self._select_proposal_id(str(selected))

    def _run_action(
        self,
        action: Callable[[], T],
        *,
        success_message: str | None = "Revisão salva",
        show_warning: bool = True,
    ) -> T | None:
        try:
            result = action()
        except (ReviewGatewayError, ValueError) as error:
            if show_warning:
                QMessageBox.warning(self, "Revisão não concluída", str(error))
            self.status_changed.emit(str(error))
            return None
        if success_message is not None:
            self.status_changed.emit(success_message)
        return result

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)


def _coordinate_spin(name: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setObjectName(name)
    spin.setRange(0, 1)
    spin.setDecimals(6)
    spin.setSingleStep(0.001)
    return spin


def _proposal_id(value: ReviewItem) -> UUID:
    return value.proposal_id.root


def _proposal_category(value: ReviewItem) -> str:
    return value.category.value if isinstance(value, ReviewProposalDto) else value.relation_type


def _proposal_label(value: ReviewProposalDto) -> str:
    """Rótulo já calculado pelo servidor; mantido como helper puramente visual."""
    return value.label


def _bounds(geometry: ReviewGeometryDto) -> tuple[float, float, float, float]:
    xs = [float(item.x) for item in geometry.points]
    ys = [float(item.y) for item in geometry.points]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return left, top, right - left, bottom - top


def _resize_geometry(
    geometry: ReviewGeometryDto,
    left: float,
    top: float,
    width: float,
    height: float,
) -> ReviewGeometryDto:
    old_left, old_top, old_width, old_height = _bounds(geometry)
    if geometry.kind is ReviewGeometryKind.POINT:
        points: tuple[NormalizedPointDto, ...] = (NormalizedPointDto(x=str(left), y=str(top)),)
    else:
        points = tuple(
            NormalizedPointDto(
                x=str(left + _scaled(float(item.x), old_left, old_width, width)),
                y=str(top + _scaled(float(item.y), old_top, old_height, height)),
            )
            for item in geometry.points
        )
    return geometry.model_copy(update={"points": points})


def _scaled(value: float, origin: float, old_size: float, new_size: float) -> float:
    return (value - origin) if old_size == 0 else (value - origin) * new_size / old_size


def _optional_uuid(value: object) -> UUID | None:
    return UUID(str(value)) if value is not None else None


def _category_label(value: ElementCategory) -> str:
    return {
        ElementCategory.POLE: "Poste",
        ElementCategory.MV_STRUCTURE: "Estrutura MT",
        ElementCategory.LV_STRUCTURE: "Estrutura BT",
        ElementCategory.CABLE: "Cabo",
        ElementCategory.EQUIPMENT: "Equipamento",
    }[value]


def _situation_label(value: ElementSituation) -> str:
    return {
        ElementSituation.EXISTING: "Existente",
        ElementSituation.INSTALL: "A instalar",
        ElementSituation.REMOVE: "A remover",
    }[value]


def _state_label(value: ReviewState) -> str:
    return {
        ReviewState.PENDING: "Proposta",
        ReviewState.CONFLICTING: "Conflitante",
        ReviewState.ACCEPTED: "Confirmada",
        ReviewState.ADJUSTED: "Ajustada",
        ReviewState.REJECTED: "Rejeitada",
    }[value]
