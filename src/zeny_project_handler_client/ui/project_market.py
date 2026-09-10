"""Escolha do mercado persistido; somente DTOs, apresentação e chamadas remotas."""

from functools import partial

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QComboBox, QGroupBox, QLabel, QPushButton, QVBoxLayout

from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.projects import (
    ProjectDetailDto,
    ProjectMarketResponse,
    UpdateProjectMarketRequest,
)

from .project_gateway import ProjectGateway, ProjectGatewayError
from .remote_read import RemoteRequestThread
from .responsive_row import ResponsiveRowLayout


class ProjectMarketWidget(QGroupBox):
    loaded = Signal(object)
    saved = Signal(object)
    busy_changed = Signal(bool)
    status_changed = Signal(str)
    invalidated = Signal()

    def __init__(self, gateway: ProjectGateway) -> None:
        super().__init__("Mercado do projeto")
        self.setObjectName("projectMarketGroup")
        self._gateway = gateway
        self._project: ProjectDetailDto | None = None
        self._response: ProjectMarketResponse | None = None
        self._generation = 0
        self._pending = False
        self._saving = False
        self._blocked = False
        self._connected = True
        layout = QVBoxLayout(self)
        self.provenance = QLabel()
        self.provenance.setObjectName("projectMarketProvenance")
        self.provenance.setWordWrap(True)
        layout.addWidget(self.provenance)
        label = QLabel("&Escolha do técnico")
        self.choice = QComboBox()
        self.choice.setObjectName("projectMarketCombo")
        self.choice.setAccessibleName("Escolha do técnico: mercado do projeto")
        self.choice.addItem("Rural", "RURAL")
        self.choice.addItem("Urbano", "URBANO")
        self.choice.addItem("Ambos", "AMBOS")
        label.setBuddy(self.choice)
        layout.addWidget(label)
        layout.addWidget(self.choice)
        actions = ResponsiveRowLayout()
        self.save = QPushButton("&Salvar mercado")
        self.save.setObjectName("projectMarketSave")
        self.cancel = QPushButton("Cancelar escolha")
        self.cancel.setObjectName("projectMarketCancel")
        self.refresh = QPushButton("Atualizar mercado")
        self.refresh.setObjectName("projectMarketRefresh")
        for button in (self.save, self.cancel, self.refresh):
            button.setAccessibleName(button.text().replace("&", ""))
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel()
        self.status.setObjectName("projectMarketStatus")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Estado da escolha de mercado")
        layout.addWidget(self.status)
        self.choice.currentIndexChanged.connect(self._controls)
        self.save.clicked.connect(self._save)
        self.cancel.clicked.connect(self._cancel)
        self.refresh.clicked.connect(self.reload)
        self.clear()

    def clear(self) -> None:
        self.invalidated.emit()
        self._generation += 1
        self._project = None
        self._response = None
        self._pending = self._saving = False
        self.choice.setCurrentIndex(-1)
        self.provenance.setText("Banco: — · Origem: —")
        self.status.setText("Abra um projeto para consultar o mercado.")
        self._controls()

    def open_project(self, project: ProjectDetailDto) -> None:
        if self._project is not None and (
            project.project_id != self._project.project_id
            or project.service_note != self._project.service_note
        ):
            self.clear()
        self._project = project
        self.reload()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._generation += 1
        self._pending = self._saving = False
        if connected:
            self.reload()
        else:
            self.invalidated.emit()
            self._response = None
            self.choice.setCurrentIndex(-1)
            self.provenance.setText("Banco e origem: indisponíveis")
            self.status.setText(
                "Conexão interrompida. Reconecte para conferir o valor salvo; "
                "um envio já iniciado pode ter sido concluído."
            )
        self._controls()

    def set_blocked(self, blocked: bool) -> None:
        self._blocked = blocked
        self._controls()

    @property
    def saving(self) -> bool:
        return self._saving

    def reload(self) -> None:
        project = self._project
        if project is None or not self._connected or self._saving:
            return
        self._generation += 1
        self._pending = True
        self.invalidated.emit()
        self._response = None
        self.choice.setCurrentIndex(-1)
        self.provenance.setText("Consultando banco e origem persistidos…")
        self.status.setText("Carregando mercado…")
        self._controls()
        worker = RemoteRequestThread(
            self._generation, partial(self._gateway.get_market, project.project_id.root)
        )
        worker.received.connect(self._received)
        worker.launch()

    def _save(self) -> None:
        response = self._response
        if response is None or not self.save.isEnabled():
            return
        request = UpdateProjectMarketRequest.model_validate(
            {
                "effective_market": self.choice.currentData(),
                "expected_project_version": response.project_version,
            }
        )
        self._generation += 1
        self._pending = self._saving = True
        self.status.setText("Salvando mercado… Aguarde a confirmação do servidor.")
        self._controls()
        self.busy_changed.emit(True)
        worker = RemoteRequestThread(
            self._generation,
            partial(self._gateway.update_market, response.project_id.root, request),
        )
        worker.received.connect(self._received)
        worker.launch()

    @Slot(int, object)
    def _received(self, generation: int, result: object) -> None:
        if generation != self._generation or self._project is None or not self._connected:
            return
        saving = self._saving
        self._pending = self._saving = False
        if not isinstance(result, ProjectMarketResponse) or not self._matches(result):
            self.invalidated.emit()
            self._response = None
            self.choice.setCurrentIndex(-1)
            self.provenance.setText("Banco e origem: indisponíveis até atualizar")
            message = "Não foi possível confirmar o mercado. Atualize antes de tentar salvar."
            if isinstance(result, ProjectGatewayError) and result.code in {
                ErrorCode.STALE_STATE,
                ErrorCode.OPERATION_CONFLICT,
            }:
                message = "Conflito: o projeto mudou ou está em uso. Atualize e escolha novamente."
            if isinstance(result, Exception):
                message += f" {result}"
            self.status.setText(message)
            self.status_changed.emit(message)
        else:
            self._response = result
            self._present()
            self.loaded.emit(result)
            if saving:
                self.status.setText(
                    "Mercado salvo. Execute Analisar conformidade para atualizar os resultados."
                )
                self.saved.emit(result)
        self._controls()
        if saving:
            self.busy_changed.emit(False)

    def _matches(self, result: ProjectMarketResponse) -> bool:
        project = self._project
        return (
            project is not None
            and result.project_id == project.project_id
            and (
                result.classification is None
                or result.classification.service_note == project.service_note
            )
        )

    def _present(self) -> None:
        classification = self._response.classification if self._response else None
        if classification is None:
            self.choice.setCurrentIndex(-1)
            self.provenance.setText("Banco: não inicializado · Origem: —")
            self.status.setText(
                "Mercado não inicializado. Execute a análise para consultar o cadastro. "
                "Se a consulta falhar, tente a análise novamente."
            )
            return
        self.choice.setCurrentIndex(self.choice.findData(classification.effective_market))
        source = "Escolha do técnico" if classification.source == "MANUAL" else "Cadastro do banco"
        self.provenance.setText(
            f"Banco inicial: {classification.database_market.title()}\n"
            f"Salvo: {classification.effective_market.title()} · Origem: {source}\n"
            f"Atualizado: {classification.updated_at.strftime('%d/%m/%Y %H:%M:%S UTC')}"
        )
        self.status.setText("Selecione o mercado e salve para aplicar a escolha.")

    def _cancel(self) -> None:
        if self._pending:
            return
        self._present()
        self.status.setText("Escolha cancelada. O valor salvo foi preservado.")
        self._controls()

    def _controls(self, _index: int = -1) -> None:
        ready = self._connected and not self._pending and not self._blocked
        classification = self._response.classification if self._response else None
        editable = ready and classification is not None
        dirty = classification is not None and (
            self.choice.currentData() != classification.effective_market
        )
        self.choice.setEnabled(editable)
        self.save.setEnabled(
            editable and (dirty or (classification is not None and classification.source == "SQL"))
        )
        self.cancel.setEnabled(editable and dirty)
        self.refresh.setEnabled(ready and self._project is not None)
