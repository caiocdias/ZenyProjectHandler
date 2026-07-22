"""Painel Qt para transformar propostas revisáveis em dados confirmados."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
        self.setObjectName("humanReviewPanel")
        self._service = service
        self._viewer = viewer
        self._session: SessaoRevisao | None = None
        self._page_id: UUID | None = None
        self._selected_proposal_id: UUID | None = None
        self._loaded_bounds: tuple[float, float, float, float] | None = None
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

        self._execution = QComboBox()
        self._execution.setObjectName("reviewExecutionCombo")
        self._execution.addItem("Execução mais recente", None)
        layout.addWidget(self._execution)

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

        self._table = QTableWidget(0, 4)
        self._table.setObjectName("reviewProposalTable")
        self._table.setHorizontalHeaderLabels(("Tipo", "Classe/relação", "Estado", "Confiança"))
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        editor = QGroupBox("Decisão e ajustes")
        form = QFormLayout(editor)
        self._reviewer = QLineEdit()
        self._reviewer.setObjectName("reviewAuthorEdit")
        form.addRow("Revisor", self._reviewer)
        self._reason = QLineEdit()
        self._reason.setObjectName("reviewReasonEdit")
        form.addRow("Motivo", self._reason)
        self._category = QComboBox()
        self._category.setObjectName("reviewCategoryCombo")
        for category in CategoriaElemento:
            self._category.addItem(category.value, category.value)
        form.addRow("Classe", self._category)
        self._catalog_item = QComboBox()
        self._catalog_item.setObjectName("reviewCatalogItemCombo")
        form.addRow("Catálogo", self._catalog_item)
        self._situation = QComboBox()
        self._situation.setObjectName("reviewSituationCombo")
        for situation in SituacaoProjeto:
            self._situation.addItem(situation.value, situation.value)
        form.addRow("Situação", self._situation)
        self._pole = QComboBox()
        self._pole.setObjectName("reviewPoleCombo")
        form.addRow("Poste", self._pole)
        self._origin_point = QComboBox()
        self._origin_point.setObjectName("reviewOriginPointCombo")
        form.addRow("Ponto inicial", self._origin_point)
        self._destination_point = QComboBox()
        self._destination_point.setObjectName("reviewDestinationPointCombo")
        form.addRow("Ponto final", self._destination_point)
        geometry_row = QHBoxLayout()
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
        form.addRow("Geometria", geometry_row)
        layout.addWidget(editor)

        decision_row = QHBoxLayout()
        accept = QPushButton("Aceitar / salvar ajuste")
        accept.setObjectName("reviewAcceptButton")
        accept.clicked.connect(self.aceitar_selecionada)
        decision_row.addWidget(accept)
        reject = QPushButton("Rejeitar")
        reject.setObjectName("reviewRejectButton")
        reject.clicked.connect(self.rejeitar_selecionada)
        decision_row.addWidget(reject)
        layout.addLayout(decision_row)

        manual_row = QHBoxLayout()
        manual_element = QPushButton("Criar elemento manual")
        manual_element.setObjectName("reviewCreateElementButton")
        manual_element.clicked.connect(self.criar_elemento_manual)
        manual_row.addWidget(manual_element)
        self._relation_type = QLineEdit("RELACIONADO_A")
        self._relation_type.setObjectName("reviewRelationTypeEdit")
        manual_row.addWidget(self._relation_type)
        manual_relation = QPushButton("Criar relação manual")
        manual_relation.setObjectName("reviewCreateRelationButton")
        manual_relation.clicked.connect(self.criar_relacao_manual)
        manual_row.addWidget(manual_relation)
        layout.addLayout(manual_row)

        self._reference_origin = QComboBox()
        self._reference_origin.setObjectName("reviewRelationOriginCombo")
        self._reference_destination = QComboBox()
        self._reference_destination.setObjectName("reviewRelationDestinationCombo")
        reference_row = QHBoxLayout()
        reference_row.addWidget(self._reference_origin)
        reference_row.addWidget(self._reference_destination)
        layout.addLayout(reference_row)

        self._project.currentIndexChanged.connect(self._load_selected_project)
        self._execution.currentIndexChanged.connect(self._load_selected_execution)
        self._category_filter.currentIndexChanged.connect(self._refresh_proposals)
        self._state_filter.currentIndexChanged.connect(self._refresh_proposals)
        self._table.itemSelectionChanged.connect(self._select_table_proposal)
        self._category.currentIndexChanged.connect(self._refresh_catalog_items)
        accept_shortcut = QShortcut(self)
        accept_shortcut.setKey(QKeySequence("A"))
        accept_shortcut.activated.connect(self.aceitar_selecionada)
        reject_shortcut = QShortcut(self)
        reject_shortcut.setKey(QKeySequence("R"))
        reject_shortcut.activated.connect(self.rejeitar_selecionada)

    def _connect_viewer(self) -> None:
        self._viewer.page_changed.connect(self._page_changed)
        self._viewer.proposal_selected.connect(self._select_proposal_id)

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto para revisão", None)
        for summary in self._service.listar_projetos():
            self._project.addItem(
                f"{summary.nome} ({summary.propostas_pendentes} pendentes)",
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
        self._project.addItem("Selecione um projeto para revisão", None)
        self._execution.clear()
        self._table.setRowCount(0)
        self._viewer.definir_propostas_revisao(())

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is None:
            return
        project_id = UUID(value)
        self._refresh_executions(project_id)
        self._run_action(lambda: self._activate_session(self._service.carregar_sessao(project_id)))

    def abrir_projeto(self, projeto_id: UUID, execucao_id: UUID | None = None) -> None:
        """Sincronize o painel com um projeto concluído pelo fluxo operacional."""
        self.atualizar_projetos()
        project_index = self._project.findData(str(projeto_id))
        if project_index < 0:
            self.status_changed.emit("Projeto ainda não possui propostas para revisão")
            return
        self._project.blockSignals(True)
        self._project.setCurrentIndex(project_index)
        self._project.blockSignals(False)
        self._refresh_executions(projeto_id, selected_execution=execucao_id)
        self._load_selected_execution()

    def _refresh_executions(
        self,
        project_id: UUID,
        *,
        selected_execution: UUID | None = None,
    ) -> None:
        current = str(selected_execution) if selected_execution is not None else None
        self._execution.blockSignals(True)
        self._execution.clear()
        for index, summary in enumerate(self._service.listar_execucoes(project_id), start=1):
            self._execution.addItem(
                f"Folha analisada {index} · "
                f"{summary.propostas_pendentes}/{summary.propostas} pendentes",
                str(summary.execucao_id),
            )
        if current is not None:
            selected_index = self._execution.findData(current)
            if selected_index >= 0:
                self._execution.setCurrentIndex(selected_index)
        elif self._execution.count():
            self._execution.setCurrentIndex(self._execution.count() - 1)
        self._execution.blockSignals(False)

    def _load_selected_execution(self) -> None:
        project_value = self._project.currentData()
        execution_value = self._execution.currentData()
        if project_value is None or execution_value is None:
            return
        self._run_action(
            lambda: self._activate_session(
                self._service.carregar_sessao(UUID(project_value), UUID(execution_value))
            )
        )

    def _activate_session(self, session: SessaoRevisao) -> None:
        self._session = session
        source_paths = tuple(source.caminho_canonico for source in session.fontes_pdf)
        if source_paths and not self._viewer.carregar_projeto(source_paths):
            raise ApplicationError("Não foi possível abrir todos os PDFs do projeto")
        if not source_paths:
            self.status_changed.emit(
                "Projeto sem referências locais de PDF; revisão tabular disponível"
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

    def _select_table_proposal(self) -> None:
        selected = self._table.selectedItems()
        if not selected:
            return
        proposal_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if proposal_id:
            self._select_proposal_id(str(proposal_id))

    def _select_proposal_id(self, proposal_id: str) -> None:
        session = self._session
        if session is None:
            return
        proposal = next((item for item in session.propostas if str(item.id) == proposal_id), None)
        if proposal is None:
            return
        self._selected_proposal_id = proposal.id
        self._viewer.selecionar_proposta(proposal_id)
        if isinstance(proposal, PropostaElemento):
            self._set_combo_value(self._category, proposal.categoria.value)
            self._refresh_catalog_items()
            if proposal.tipo_catalogo_sugerido_id is not None:
                self._set_combo_value(self._catalog_item, str(proposal.tipo_catalogo_sugerido_id))
            self._set_combo_value(self._situation, proposal.situacao_projeto.value)
            self._set_geometry_fields(proposal.geometria)

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
        self._activate_session(
            self._service.carregar_sessao(session.projeto.id, session.execucao.id)
        )
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
