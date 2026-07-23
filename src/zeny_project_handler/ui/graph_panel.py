"""Painel Qt para reconstruir, explorar e revisar as projeções do grafo."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.application.project_graph import ServicoGrafoProjeto, SessaoGrafoProjeto
from zeny_project_handler.domain.enums import (
    SeveridadeDiagnosticoGrafo,
    TipoNoGrafo,
    VisaoGrafo,
)
from zeny_project_handler.domain.graph import DiagnosticoGrafo, GrafoDerivado, NoGrafo

from .pdf_viewer import PdfViewerWidget

T = TypeVar("T")


class GraphCanvas(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("graphCanvas")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._items: dict[UUID, QGraphicsEllipseItem] = {}
        self._graph: GrafoDerivado | None = None

    def definir_grafo(
        self,
        graph: GrafoDerivado,
        *,
        node_type: TipoNoGrafo | None = None,
        highlighted: tuple[UUID, ...] = (),
    ) -> None:
        self._scene.clear()
        self._items.clear()
        self._graph = graph
        nodes = tuple(item for item in graph.nos if node_type is None or item.tipo is node_type)
        node_ids = {item.id for item in nodes}
        positions = _node_positions(nodes)
        parallel_indexes: dict[frozenset[UUID], int] = defaultdict(int)
        for edge in graph.arestas:
            if edge.origem_id not in node_ids or edge.destino_id not in node_ids:
                continue
            pair = frozenset((edge.origem_id, edge.destino_id))
            index = parallel_indexes[pair]
            parallel_indexes[pair] += 1
            start = positions[edge.origem_id]
            end = positions[edge.destino_id]
            path = _edge_path(start, end, index)
            pen = QPen(QColor("#f59e0b") if edge.proposta else QColor("#64748b"), 2)
            pen.setCosmetic(True)
            if edge.proposta:
                pen.setStyle(Qt.PenStyle.DashLine)
            line = self._scene.addPath(path, pen)
            line.setToolTip(f"{edge.tipo} · {edge.referencia_id}")
        highlighted_set = set(highlighted)
        for node in nodes:
            position = positions[node.id]
            radius = 11 if node.id not in highlighted_set else 15
            pen = QPen(QColor("#ef4444") if node.id in highlighted_set else QColor("#1f2937"), 3)
            pen.setCosmetic(True)
            item = self._scene.addEllipse(
                position.x() - radius,
                position.y() - radius,
                radius * 2,
                radius * 2,
                pen,
                QBrush(_node_color(node)),
            )
            item.setToolTip(f"{node.tipo.value} · {node.rotulo}")
            self._items[node.id] = item
            label = self._scene.addText(node.rotulo[:28])
            label.setDefaultTextColor(QColor("#111827"))
            label.setPos(position.x() + radius + 2, position.y() - 10)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-25, -25, 25, 25))
        if self._scene.items():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class GraphPanelWidget(QWidget):
    status_changed = Signal(str)

    def __init__(
        self,
        *,
        service: ServicoGrafoProjeto,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectGraphPanel")
        self._service = service
        self._viewer = viewer
        self._session: SessaoGrafoProjeto | None = None
        self._diagnostics: dict[UUID, DiagnosticoGrafo] = {}
        self._highlighted: tuple[UUID, ...] = ()
        self._build_ui()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("graphScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = QWidget(self._scroll)
        content.setObjectName("graphScrollContent")
        content.setMinimumHeight(760)
        layout = QVBoxLayout(content)
        project_row = QHBoxLayout()
        self._project = QComboBox()
        self._project.setObjectName("graphProjectCombo")
        project_row.addWidget(self._project, 1)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("graphRefreshProjectsButton")
        refresh.clicked.connect(self.atualizar_projetos)
        project_row.addWidget(refresh)
        rebuild = QPushButton("Reconstruir grafo")
        rebuild.setObjectName("graphRebuildButton")
        rebuild.clicked.connect(self.reconstruir)
        project_row.addWidget(rebuild)
        layout.addLayout(project_row)

        filter_row = QHBoxLayout()
        self._view = QComboBox()
        self._view.setObjectName("graphViewCombo")
        self._view.addItem("Visão física", VisaoGrafo.FISICA.value)
        self._view.addItem("Visão elétrica", VisaoGrafo.ELETRICA.value)
        self._view.currentIndexChanged.connect(self._refresh_graph)
        filter_row.addWidget(self._view)
        self._node_type = QComboBox()
        self._node_type.setObjectName("graphNodeTypeFilter")
        self._node_type.addItem("Todos os nós", None)
        for node_type in TipoNoGrafo:
            self._node_type.addItem(node_type.value.replace("_", " ").title(), node_type.value)
        self._node_type.currentIndexChanged.connect(self._refresh_graph)
        filter_row.addWidget(self._node_type)
        self._severity = QComboBox()
        self._severity.setObjectName("graphSeverityFilter")
        self._severity.addItem("Todas as severidades", None)
        for severity in SeveridadeDiagnosticoGrafo:
            self._severity.addItem(severity.value.title(), severity.value)
        self._severity.currentIndexChanged.connect(self._refresh_diagnostics)
        filter_row.addWidget(self._severity)
        layout.addLayout(filter_row)

        self._summary = QLabel("Selecione um projeto e reconstrua o grafo.")
        self._summary.setObjectName("graphSummaryLabel")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self.canvas = GraphCanvas(self)
        self.canvas.setMinimumHeight(320)
        layout.addWidget(self.canvas, 2)

        diagnostic_box = QGroupBox("Diagnósticos e conexões propostas")
        diagnostic_layout = QVBoxLayout(diagnostic_box)
        self._table = QTableWidget(0, 3)
        self._table.setObjectName("graphDiagnosticsTable")
        self._table.setHorizontalHeaderLabels(("Severidade", "Código", "Mensagem"))
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._diagnostic_selected)
        self._table.itemDoubleClicked.connect(lambda _item: self.ir_ao_pdf())
        diagnostic_layout.addWidget(self._table)
        self._table.setMinimumHeight(220)
        action_row = QHBoxLayout()
        self._reviewer = QLineEdit()
        self._reviewer.setObjectName("graphReviewerEdit")
        self._reviewer.setPlaceholderText("Responsável pela confirmação")
        action_row.addWidget(self._reviewer, 1)
        navigate = QPushButton("Ir ao PDF")
        navigate.setObjectName("graphNavigateButton")
        navigate.clicked.connect(self.ir_ao_pdf)
        action_row.addWidget(navigate)
        self._confirm = QPushButton("Confirmar conexão")
        self._confirm.setObjectName("graphConfirmConnectionButton")
        self._confirm.setEnabled(False)
        self._confirm.clicked.connect(self.confirmar_conexao)
        action_row.addWidget(self._confirm)
        diagnostic_layout.addLayout(action_row)
        layout.addWidget(diagnostic_box, 1)
        self._scroll.setWidget(content)
        outer_layout.addWidget(self._scroll)

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        result = self._run(self._service.listar_projetos)
        if result is None:
            return
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto", None)
        for item in result:
            self._project.addItem(
                f"{item.nome} · {item.elementos_confirmados} confirmado(s)",
                str(item.projeto_id),
            )
        if selected is not None:
            index = self._project.findData(selected)
            if index >= 0:
                self._project.setCurrentIndex(index)
        self._project.blockSignals(False)

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index >= 0:
            self._project.setCurrentIndex(index)
            self.reconstruir()

    def reconstruir(self) -> None:
        project_id = self._selected_project_id()
        if project_id is None:
            self._warn("Selecione um projeto para reconstruir")
            return
        session = self._run(lambda: self._service.reconstruir(project_id))
        if session is None:
            return
        self._activate(session)
        self.status_changed.emit("Grafo reconstruído a partir do conjunto confirmado")

    def _activate(self, session: SessaoGrafoProjeto) -> None:
        self._session = session
        self._highlighted = ()
        result = session.resultado
        self._summary.setText(
            f"Assinatura {result.assinatura[:12]}… · "
            f"Físico: {len(result.fisico.nos)} nós/{len(result.fisico.arestas)} arestas · "
            f"Elétrico: {len(result.eletrico.nos)} nós/{len(result.eletrico.arestas)} arestas · "
            f"{len(result.diagnosticos)} diagnóstico(s)"
        )
        self._refresh_graph()
        self._refresh_diagnostics()

    def _refresh_graph(self) -> None:
        session = self._session
        if session is None:
            return
        graph = (
            session.resultado.fisico
            if self._current_view() is VisaoGrafo.FISICA
            else session.resultado.eletrico
        )
        self.canvas.definir_grafo(
            graph,
            node_type=self._current_node_type(),
            highlighted=self._highlighted,
        )

    def _refresh_diagnostics(self) -> None:
        session = self._session
        if session is None:
            return
        severity = self._current_severity()
        diagnostics = tuple(
            item
            for item in session.resultado.diagnosticos
            if severity is None or item.severidade is severity
        )
        self._diagnostics = {item.id: item for item in diagnostics}
        self._table.setRowCount(0)
        for diagnostic in diagnostics:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = (diagnostic.severidade.value, diagnostic.codigo, diagnostic.mensagem)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(diagnostic.id))
                self._table.setItem(row, column, cell)
        self._confirm.setEnabled(False)

    def _diagnostic_selected(self) -> None:
        diagnostic = self._selected_diagnostic()
        self._highlighted = diagnostic.referencias_ids if diagnostic is not None else ()
        if diagnostic is not None:
            index = self._view.findData(diagnostic.visao.value)
            if index >= 0:
                self._view.setCurrentIndex(index)
        self._confirm.setEnabled(diagnostic is not None and diagnostic.sugestao_id is not None)
        self._refresh_graph()

    def ir_ao_pdf(self) -> None:
        session = self._session
        diagnostic = self._selected_diagnostic()
        if session is None or diagnostic is None:
            self._warn("Selecione um diagnóstico com referência ao projeto")
            return
        destination = self._service.localizar_referencia(session, diagnostic.referencias_ids)
        if destination is None:
            self._warn("O diagnóstico selecionado não possui geometria navegável no PDF")
            return
        paths = tuple(item.caminho_canonico for item in session.fontes_pdf)
        if not paths:
            self._warn("As fontes PDF deste projeto não estão disponíveis")
            return
        current_paths = tuple(
            item.caminho_origem.expanduser().resolve() for item in self._viewer.inspecoes
        )
        expected_paths = tuple(item.expanduser().resolve() for item in paths)
        if current_paths != expected_paths and not self._viewer.carregar_projeto(
            paths,
            documentos=session.projeto.documentos,
        ):
            self._warn("Não foi possível abrir as fontes PDF do projeto")
            return
        self._viewer.ir_para_folha(destination.folha_numero)
        self._viewer.definir_sobreposicoes((destination.geometria.pontos,))
        self.status_changed.emit(f"Navegação para a folha {destination.folha_numero}")

    def confirmar_conexao(self) -> None:
        session = self._session
        diagnostic = self._selected_diagnostic()
        if session is None or diagnostic is None or diagnostic.sugestao_id is None:
            self._warn("Selecione uma conexão proposta")
            return
        suggestion_id = diagnostic.sugestao_id
        updated = self._run(
            lambda: self._service.confirmar_sugestao(
                session.projeto.id,
                suggestion_id,
                assinatura_esperada=session.resultado.assinatura,
                revisor=self._reviewer.text(),
            )
        )
        if updated is not None:
            self._activate(updated)
            self.status_changed.emit("Conexão confirmada e grafo reconstruído")

    def _selected_project_id(self) -> UUID | None:
        value = self._project.currentData()
        return UUID(str(value)) if value is not None else None

    def _current_view(self) -> VisaoGrafo:
        return VisaoGrafo(str(self._view.currentData()))

    def _current_node_type(self) -> TipoNoGrafo | None:
        value = self._node_type.currentData()
        return TipoNoGrafo(str(value)) if value is not None else None

    def _current_severity(self) -> SeveridadeDiagnosticoGrafo | None:
        value = self._severity.currentData()
        return SeveridadeDiagnosticoGrafo(str(value)) if value is not None else None

    def _selected_diagnostic(self) -> DiagnosticoGrafo | None:
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        first_cell = self._table.item(row, 0)
        if first_cell is None:
            return None
        identifier = first_cell.data(Qt.ItemDataRole.UserRole)
        return self._diagnostics.get(UUID(str(identifier))) if identifier is not None else None

    def _run(self, action: Callable[[], T]) -> T | None:
        try:
            return action()
        except (ApplicationError, ValueError) as error:
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Ação não concluída", str(error))
            return None

    def _warn(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Ação necessária", message)


def _node_positions(nodes: tuple[NoGrafo, ...]) -> dict[UUID, QPointF]:
    pages = sorted(
        {item.geometria.pagina_id for item in nodes if item.geometria is not None},
        key=str,
    )
    page_index = {page_id: index for index, page_id in enumerate(pages)}
    positions: dict[UUID, QPointF] = {}
    missing: list[NoGrafo] = []
    for node in nodes:
        if node.geometria is None:
            missing.append(node)
            continue
        xs = [float(item.x) for item in node.geometria.pontos]
        ys = [float(item.y) for item in node.geometria.pontos]
        page_offset = page_index[node.geometria.pagina_id] * 520
        positions[node.id] = QPointF(
            page_offset + ((min(xs) + max(xs)) / 2) * 480,
            ((min(ys) + max(ys)) / 2) * 360,
        )
    for index, node in enumerate(missing):
        positions[node.id] = QPointF((index % 6) * 100, 400 + (index // 6) * 70)
    return positions


def _edge_path(start: QPointF, end: QPointF, parallel_index: int) -> QPainterPath:
    path = QPainterPath(start)
    if parallel_index == 0:
        path.lineTo(end)
        return path
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = max(1.0, math.hypot(dx, dy))
    offset = ((parallel_index + 1) // 2) * 18 * (1 if parallel_index % 2 else -1)
    midpoint = QPointF(
        (start.x() + end.x()) / 2 - dy / length * offset,
        (start.y() + end.y()) / 2 + dx / length * offset,
    )
    path.quadTo(midpoint, end)
    return path


def _node_color(node: NoGrafo) -> QColor:
    colors = {
        TipoNoGrafo.POSTE: "#3b82f6",
        TipoNoGrafo.EQUIPAMENTO: "#8b5cf6",
        TipoNoGrafo.PONTO_REDE: "#14b8a6",
        TipoNoGrafo.TERMINAL: "#f59e0b",
    }
    return QColor(colors[node.tipo])
