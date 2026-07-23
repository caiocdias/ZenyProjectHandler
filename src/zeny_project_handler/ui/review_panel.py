"""Painel Qt para transformar propostas revisáveis em dados confirmados."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
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
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.project import Cabo, Equipamento, EstruturaBt, EstruturaMt, Poste
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .pdf_viewer import PdfViewerWidget

T = TypeVar("T")


class ReviewPanelWidget(QWidget):
    status_changed = Signal(str)

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

        filter_row = QHBoxLayout()
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
        layout.addLayout(filter_row)

        guidance = QLabel(
            "As identificações são incorporadas automaticamente ao projeto. "
            "Expanda cada região para ver a coordenada e tudo o que acontece naquele ponto; "
            "clique em qualquer elemento para localizá-lo no PDF."
        )
        guidance.setObjectName("analysisResultsGuidance")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        self._tree = QTreeWidget()
        self._tree.setObjectName("analysisRelationshipTree")
        self._tree.setHeaderLabels(
            ("Ponto / elemento", "Ação", "Coordenada", "Catálogo", "Vínculos")
        )
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = self._tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(80)
        for column, width in enumerate((190, 105, 185, 260, 260)):
            header.resizeSection(column, width)
        header.setStretchLastSection(False)
        layout.addWidget(self._tree, 1)

        self._table = QTableWidget(0, 4)
        self._table.setObjectName("reviewProposalTable")
        self._table.setHorizontalHeaderLabels(("Tipo", "Classe/relação", "Estado", "Confiança"))
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.hide()
        layout.addWidget(self._table)

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
        self._project.clear()
        self._project.addItem("Selecione um projeto analisado", None)
        self._tree.clear()
        self._table.setRowCount(0)
        self._viewer.definir_propostas_revisao(())

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

    def _page_changed(self, page_id: str) -> None:
        self._page_id = UUID(page_id)
        self._refresh_proposals()

    def _refresh_proposals(self) -> None:
        session = self._session
        if session is None:
            return
        category = self._category_filter.currentData()
        state = self._state_filter.currentData()
        filtered = tuple(
            item
            for item in session.propostas
            if (category is None or _proposal_category(item) == category)
            and (state is None or item.estado_revisao.value == state)
        )
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
        overlays = tuple(
            item
            for item in filtered
            if isinstance(item, PropostaElemento)
            and (self._page_id is None or item.geometria.pagina_id == self._page_id)
        )
        self._viewer.definir_propostas_revisao(overlays)

    def _populate_result_tree(
        self,
        proposals: tuple[PropostaElemento | PropostaRelacao, ...],
    ) -> None:
        session = self._session
        if session is None:
            return
        self._tree.clear()
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
            if not elements:
                continue
            root = QTreeWidgetItem(
                (
                    self._region_label(region, region_number),
                    _region_action_counts(elements),
                    _coordinate_label(region),
                    f"{len(elements)} elemento(s)",
                    f"{len(region.vinculo_ids)} vínculo(s)",
                )
            )
            root.setData(0, Qt.ItemDataRole.UserRole + 1, str(region.id))
            root.setToolTip(0, self._region_location(region, region_number))
            root.setToolTip(1, _region_summary(elements))
            self._tree.addTopLevelItem(root)
            for element in elements:
                root.addChild(
                    self._result_item(
                        element,
                        relationships=_relationship_labels(
                            element,
                            region,
                            all_elements,
                            all_relations,
                        ),
                    )
                )
        if not visible_elements:
            self._tree.addTopLevelItem(
                QTreeWidgetItem(("Nenhuma identificação neste filtro", "", "", "", ""))
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
                _proposal_label(proposal),
                _situation_label(proposal.situacao_projeto),
                "",
                self._catalog_label(proposal),
                "; ".join(relationships) or "Agrupado por proximidade",
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
        self._viewer.definir_sobreposicoes((region.geometria.pontos,))
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


def _proposal_label(proposal: PropostaElemento) -> str:
    category = {
        CategoriaElemento.POSTE: "Poste",
        CategoriaElemento.ESTRUTURA_MT: "Estrutura MT",
        CategoriaElemento.ESTRUTURA_BT: "Estrutura BT",
        CategoriaElemento.CABO: "Cabo",
        CategoriaElemento.EQUIPAMENTO: "Equipamento",
    }[proposal.categoria]
    return f"{category} {proposal.codigo_observado or ''}".strip()


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


def _region_summary(elements: tuple[PropostaElemento, ...]) -> str:
    parts: list[str] = []
    for situation, verb in (
        (SituacaoProjeto.REMOVER, "Remover"),
        (SituacaoProjeto.INSTALAR, "Instalar"),
        (SituacaoProjeto.EXISTENTE, "Existente"),
    ):
        labels = tuple(
            _proposal_label(element)
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
        labels.append(f"{relation_label} {direction} {_proposal_label(related)}")
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
